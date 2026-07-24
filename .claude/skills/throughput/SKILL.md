---
name: throughput
description: "Measure the sustainable agentic-coding throughput of a self-hosted model on a specific EC2 GPU instance, and derive a realistic cost-per-token and cost-per-task from the instance's hourly price. Sweeps /swe concurrency (2,5,7,10,15,20 by default), driving real agentic sessions while a DuckDB collector captures vLLM's server-side token counters; then builds a PERFORMANCE-SUMMARY.json and a self-contained HTML dashboard (throughput / latency / KV-cache saturation / cost curves). Use when the user wants tokens/sec at concurrency, a saturation curve, or a hardware-derived cost per token / per task for a self-hosted (vLLM) model. Separate from the /benchmark quality skill. Wraps self-hosted/vllm/scripts/run-throughput-sweep.sh."
license: Apache-2.0
metadata:
  author: Amit Arora
  version: "1.0"
---

# Throughput & Cost Skill

Use this skill to answer a **serving-economics** question, not a quality one: *how much agentic-coding load can this model sustain on this exact EC2 instance, and therefore what does a task really cost?* It sweeps concurrency, measures throughput from vLLM's own counters, and turns the fixed instance $/hr into a defensible **cost per token** and **cost per task** — replacing the fictional `total_cost_usd` the quality harness records for self-hosted models (which has no per-token bill).

This is deliberately **separate from the `/benchmark` (quality) skill**. Quality runs one agentic session per task and scores the artifacts; throughput holds *N* sessions in flight and measures the server. They share the same building blocks but answer different questions, so they are different scripts.

## The cost model

```
cost_per_output_token = ($/hr ÷ 3600) ÷ sustained_output_tokens_per_second
cost_per_task         = cost_per_output_token × output_tokens_per_task
```

`sustained_output_tokens_per_second` comes from vLLM's `generation_tokens_total` counter delta over each concurrency level's window (server-measured — a session need not finish to have generated its tokens). `output_tokens_per_task` comes from the model's real `/swe` runs (`metrics.json`).

## Why it works this way (read before changing it)

- **Real agentic load, server-side measurement.** Each in-flight unit is a genuine `/swe` session against a real cloned repo (large read-heavy prompts, short outputs — the true workload). But throughput is read from vLLM's DuckDB counters, **not** from completed sessions: an agentic session can take ~30 min, far longer than a throughput window, so sessions are **cut off at the window** (their `claude -p` timeout is bounded to the remaining window). The tokens they generated while running are already in the counter delta.
- **Concurrency is the controlled variable.** The harness holds exactly `N` sessions in flight, refilling a slot as soon as one is cut off/finishes, for a fixed wall-clock window per level.
- **One named DuckDB session per level** (`{model}_c{N}`) so each level is sliceable.

## The three inputs

1. **model** — the served-model-name already running on the local vLLM server (e.g. `gemma-4-31b`). This skill does **not** start the server; serve it first (use the `/vllm-setup` or `/benchmark` flow, or `vllm-serve.sh`).
2. **instance + $/hr** — the EC2 instance type (for provenance) and its on-demand hourly price. Default reference: `g6e.12xlarge` at **$10.49/hr** (us-east-1 on-demand). Use the user's actual spot/reserved/negotiated rate if they give one.
3. **concurrency levels + window** — default sweep `2 5 7 10 15 20`, `--duration-seconds 300` (5 min) per level (~30-40 min total). Fewer/shorter for a quick look.

## Workflow

### Step 1 — Confirm the server and inputs

```bash
curl -s http://127.0.0.1:8000/v1/models | python3 -c "import sys,json;print([m['id'] for m in json.load(sys.stdin).get('data',[])])"
```

Confirm it serves `{model}`. If not, stop and tell the user to serve it first. Restate the plan (model, instance $/hr, levels, window) and where results land, then proceed.

### Step 2 — Derive the per-task output-token figure (for cost-per-task)

If the model has quality-run artifacts, use its mean output tokens per task so cost-per-task reflects real agentic sessions:

```bash
cd benchmarks
python3 - <<'PY'
import json, glob
tot=n=0
for f in glob.glob("swe-benchmark-data/{model-slug}/*/*/metrics.json"):
    ot=json.load(open(f)).get("metrics_that_matter",{}).get("output_tokens")
    if ot: tot+=ot; n+=1
print("mean output tokens/task:", round(tot/n) if n else "unknown (pass a value)")
PY
```

Pass that as `--output-tokens-per-task` in Step 4. If unknown, skip it (cost-per-1M-tokens is still produced).

### Step 3 — Run the sweep

The sweep drives real `/swe` load at each concurrency level and captures the vLLM server metrics into one shared DuckDB (one named session per level). It does not score anything.

```bash
cd self-hosted/vllm
./scripts/run-throughput-sweep.sh --model {model} \
  --concurrencies "2 5 7 10 15 20" --duration-seconds 300 [--context-window N] [--endpoint URL]
```

Tell the user, before it runs:
- It holds N real agentic sessions in flight per level for the window; sessions still running at window close are cut off (expected — throughput is server-measured, not per-completed-session).
- Watch the collector + a level in flight:
  ```bash
  tail -f self-hosted/vllm/benchmark-output/throughput/{model}/collector-c*.log
  tail -f self-hosted/vllm/logs/vllm-serve.log
  ```
- A slow/dense model at high concurrency may saturate KV cache — which is itself the finding.

### Step 4 — Build the performance summary + dashboard

```bash
cd self-hosted/vllm
DB=benchmark-output/throughput/{model}/throughput-metrics.duckdb
uv run python -m clients.build_performance_summary \
  --model {model} --db "$DB" --instance-type g6e.12xlarge \
  --dollars-per-hour 10.49 --output-tokens-per-task {N-from-step-2}
uv run python -m clients.build_performance_dashboard \
  --summary benchmark-output/throughput/{model}/PERFORMANCE-SUMMARY.json
```

This writes `PERFORMANCE-SUMMARY.json` (machine-readable: per-level throughput, TTFT/TPOT, KV-cache/running/waiting, cost/token, cost/task; plus peak throughput and cheapest $/1M) and `performance-dashboard.html` (self-contained, offline).

### Step 5 — Report

- Headline: peak sustained output tokens/s and the concurrency it occurs at; cheapest $/1M output tokens; cost per task.
- The saturation story: where KV-cache % and waiting-requests climb (the practical concurrency ceiling), and how TTFT/TPOT degrade with load — the "acceptable latency" knee that anchors the cost figure.
- Point the user at the dashboard HTML and the JSON.

## Notes

- **This skill does not manage the vLLM server.** Serve the model first; the sweep only checks it is up and fails loudly if not.
- **Cost is hardware-derived, not a bill.** The number is `instance $/hr ÷ measured tokens/hr` — real and defensible, unlike the token-priced estimate quality runs record for self-hosted models.
- Every script takes `--help`.
