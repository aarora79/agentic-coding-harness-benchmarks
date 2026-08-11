# Agentic coding model comparison (self-hosted throughput and cost)

How self-hosted open-weight models compare when driven as **agentic coding** engines on self-hosted GPU instances. This is a **serving-economics** comparison — throughput, latency, and hardware-derived cost per token / per task — not a code-quality one. Quality is scored separately (see the README leaderboard and the per-harness [swe2](agentic-coding-swe-comparison-swe2.md) / [swe3](agentic-coding-swe-comparison-swe3.md) comparisons); this doc answers *how much agentic load each model sustains, and what a task really costs*.

All figures come from the throughput skill (`self-hosted/vllm/scripts/run-throughput-sweep.sh`), which replays agentic-coding-shaped traffic at controlled concurrency and reads throughput from vLLM's own server-side counters (DuckDB). It is a **synthetic throughput sweep that measures the server, not any one harness or skill** — the numbers here are independent of whether the model is later driven by Claude Code or pi, or by the swe2 (multi-agent) or swe3 (single-agent) skill. Cost is derived, not quoted: `instance $/hr / measured tokens/sec`. See [cost-per-task-methodology.md](cost-per-task-methodology.md) for the cost model and the two lenses, and [serving-optimization-notes.md](serving-optimization-notes.md) for the serving defaults.

**Config used (so this is reproducible):**
- **Dataset:** [`benchmarks/dataset/multi-repo-throughput.yaml`](../benchmarks/dataset/multi-repo-throughput.yaml) — **one task per repo across 25 different public repos** in six languages (10 Python, 5 Java, 3 Rust, 2 Go, 2 JS, 3 HTML/CSS), so N concurrent slots each hammer a *different* repo (realistic fleet load). This is deliberately **not** the single-repo `mcp-gateway-registry.yaml` used by the quality benchmarks — throughput is measured against the 25-repo mix, code quality against the one repo.
- **Runner:** [`benchmarks/config/runner.yaml`](../benchmarks/config/runner.yaml) (passed as `--config config/runner.yaml`).

## Comparison

Sweep: concurrency `1 2 5 7 10 15 20`, 10-minute window per level, 200K context. Cost is the **blended lens** (every processed token — prompt + generation — costs the same GPU slice; the honest primary metric for an input-heavy workload). "Cheapest $/task" is at each model's most cost-efficient concurrency level. The per-task token shape used here (`in:out`) is the sweep's synthetic definition; real agentic runs range wider (~50:1 to ~660:1 across models under the single-agent swe3 skill — see [cost-per-task-methodology.md](cost-per-task-methodology.md)), and per-token cost is a property of the model + hardware + load, so recost any real task shape with `clients/cost_for_task.py`.

> [!IMPORTANT]
> **The p5en 35% discount is a PLACEHOLDER, configurable in [`self-hosted/vllm/pricing.json`](../self-hosted/vllm/pricing.json).** g6e is priced at its **3-year Reserved Instance rate**; p5en at **on-demand with a 0.35 placeholder `discount`** (35% off = pay 65% -> $41.14/hr; stand in your own committed/negotiated discount). Every self-hosted cost below rescales linearly with that rate.

> **Two different instances.** The smaller models were served on **g6e.12xlarge (4xL40S, $4.533/hr, 3-year RI)**; the larger ones on **p5en.48xlarge (8xH200, effective $41.14/hr full box = on-demand $63.296 x (1 - 0.35 placeholder discount); TP=4 models are charged half, $20.57/hr)**. Rates come from [`self-hosted/vllm/pricing.json`](../self-hosted/vllm/pricing.json) (us-east-1; the p5en discount is configurable). Cost per token/task already accounts for each instance's hourly price, so it is comparable across rows — but peak-throughput numbers are not apples-to-apples across the instance line. Rows are grouped by instance.

### g6e.12xlarge (4xL40S, $4.533/hr, 3-year RI)

| Model | Arch | Peak gen tok/s | Cheapest $/1M (blended) | Cheapest $/task | Task ratio (in:out) | Notes |
|---|---|--:|--:|--:|--:|---|
| **qwen3-coder-30b** | 3B-active MoE | 67 @ c=7 | **$0.06** | $0.17 | ~236:1 | Cheapest per token overall; very heavy input load |
| **qwen3.6-35b** | 3B-active MoE | 145 @ c=1 | $0.10 | **$0.14** | ~50:1 | Fastest tokens on this box; cheapest per task |
| **gemma-4-31b** | dense 31B | 31 @ c=2 | $0.32 | $0.45 | ~67:1 | ~3-5x pricier; dense = slow per token |

### p5en.48xlarge (8xH200)

Cheapest $/task uses each sweep's blended task definition (~8M input : 50K output, ~160:1 for the large H200 MoEs) so the per-task column is comparable within this instance.

| Model | Arch | $/hr | Peak gen tok/s | Cheapest $/1M (blended) | Cheapest $/task | Task ratio (in:out) | Notes |
|---|---|--:|--:|--:|--:|--:|---|
| **minimax-m2.5** | small-active MoE | $20.57 | **300 @ c=15** | **$0.11** | **$0.13** | ~101:1 | TP=4 (half the box); highest peak throughput and cheapest per token/task on this instance |
| **devstral-2-123b** | dense 123B | $20.57 | 128 @ c=5 | $0.20 | $1.13 | ~218:1 | TP=4 (half the box); cheap per task despite dense arch |
| **nemotron-ultra-550b** | dense 550B | $41.14 | 244 @ c=10 | $0.28 | $1.13 | ~103:1 | Full box; strong aggregate throughput keeps per-task cost low |
| **qwen3-coder-480b** | very large MoE | $20.57 | 49 @ c=2 | $0.35 | $1.50 | ~377:1 | 480B weights; no c=1 baseline in this run (see caveat) |
| **deepseek-v3.2** | large MoE | $41.14 | 173 @ c=5 | $0.39 | $3.08 | ~160:1 | Cheapest of the full-box H200 models per token and per task |
| **kimi-k2.7-code** | large MoE | $41.14 | 274 @ c=5 | $0.54 | $4.35 | ~160:1 | Fast; the H200 box's hourly price dominates |
| **glm-5.2** | large MoE | $41.14 | 190 @ c=10 | $0.72 | $5.79 | ~160:1 | Most expensive per task on this box |

## Takeaways

- **3B-active MoE economics dominate on a fixed-cost box.** On the same g6e.12xlarge, the dense gemma-4-31b activates all parameters per token, so it is **2-5x slower per token and 3-5x more expensive** than the qwen MoEs that activate only ~3B params per token. Per-token compute tracks the *active*-parameter count, not the total — which is exactly why the self-hosting strategy favors sparse MoEs.

- **Cheapest per *token* is not cheapest per *task*.** qwen3-coder-30b has the lowest per-token cost ($0.06/1M) but qwen3.6-35b is cheapest per *task* ($0.14). The reason is task shape: coder-30b's agentic tasks carry a far heavier input load (~2.75M input : 12K output, ~236:1) than qwen3.6-35b (~50:1), so even at a lower per-token rate the sheer token count per task adds up. **Always compare per-task when choosing a model for a workload** — per-token rates mislead when input:output ratios differ this much.

- **Bigger box, bigger peak — but the hourly price can swamp the cost gain, unless the model is a small-active MoE that only needs half the box.** The full-box H200 models hit solid peak throughput (kimi at 274 tok/s, nemotron at 244, glm-5.2 at 190, deepseek at 173), but at effective $41.14/hr their per-task cost is generally several times the g6e models'. glm-5.2's $5.79/task is driven by both the $41.14/hr rate and its very heavy input load. The full-box exception is **nemotron-ultra-550b** at just **$1.13/task**: strong aggregate throughput (244 gen tok/s @ c=10) plus a lighter task ratio (~103:1) mean far fewer tokens per task, so even at full-box price it undercuts deepseek-v3.2 ($3.08) and the other large MoEs — a reminder that per-task cost tracks throughput x task-shape, not just the hourly rate. The standout exception is **minimax-m2.5**: a small-active MoE that fits at TP=4 (half the H200 box, so $20.57/hr) yet posts the **highest peak throughput here (300 tok/s @ c=15) and the cheapest cost of any p5en model ($0.11/1M, $0.13/task)** — competitive with the g6e MoEs on cost while serving from the big box. Active-parameter count and the half-instance footprint, not total size or instance tier, drive the economics: minimax-m2.5 and qwen3-coder-480b both run TP=4 at $20.57/hr, but minimax is ~6x faster and ~10x cheaper per task because its per-token compute (and KV pressure) is far lower. The big boxes still matter when you need a model that only fits there (e.g. 480B weights) or raw aggregate throughput.

- **All are prefill-heavy but healthy, each with its own concurrency knee.** Agentic coding is input-heavy (large read-heavy prompts, small outputs), so the server spends most of its time on prompt prefill, not generation. On a healthy instance TTFT stays low (0-2s) until the model's concurrency knee, then rises: gemma saturates earliest (~c=2), qwen3-coder-30b holds to ~c=10, qwen3.6-35b stays healthy past c=20. minimax-m2.5 holds sub-second TTFT all the way to c=15 (its peak) then falls off a cliff at c=20 (throughput 300->127 tok/s, TTFT ~8.5s) as KV finally saturates — a sharp, well-defined knee. Beyond the knee, add replicas (horizontal scaling), not concurrency — blended per-task cost is flat across replicas, so the per-task figures above are the fleet-scale figures too.

## Caveats on the source runs

- **qwen3-coder-480b has no c=1 baseline** (its sweep started at c=2), so it lacks the uncontended health-check reference the other runs have. Treat its numbers as indicative; a re-run with c=1 would confirm the server was clean. All other runs passed the c=1 check (uncontended TTFT p50 <= 0.5s except qwen3.6-35b at 2.5s, which is still healthy for a dense-prompt cold start).
- **Instance prices are configurable** (p5en on-demand $63.296 with a 0.35 placeholder `discount` = pay 65% -> $41.14/hr; g6e 3-year Reserved Instance $4.533/hr) as recorded in each run's effective `dollars_per_hour`. Your own committed/negotiated discount, on-demand, or spot would shift the cost columns proportionally (cost scales linearly with $/hr).

## How to reproduce

```bash
# Serve the model (see self-hosted/vllm/models/<model>.md for exact flags), then:
cd self-hosted/vllm
./scripts/run-throughput-sweep.sh --model <served-name> --duration-seconds 600
uv run python -m clients.build_performance_summary --model <served-name> \
  --db benchmark-output/throughput/<served-name>/throughput-metrics.duckdb \
  --instance-type <instance> --dollars-per-hour <rate> \
  --output-tokens-per-task <M> --input-tokens-per-task <N>
uv run python -m clients.build_performance_dashboard \
  --summary benchmark-output/throughput/<served-name>/performance-summary.json
```

To cost an arbitrary task on any of these models from its token counts, use `clients/cost_for_task.py`.

## Source data

Per-model dashboards and machine-readable summaries under `self-hosted/vllm/benchmark-output/throughput/<model>/`:

| Model | Summary | Dashboard |
|---|---|---|
| qwen3-coder-30b | [json](../self-hosted/vllm/benchmark-output/throughput/qwen3-coder-30b/performance-summary.json) | [html](../self-hosted/vllm/benchmark-output/throughput/qwen3-coder-30b/performance-dashboard.html) |
| qwen3.6-35b | [json](../self-hosted/vllm/benchmark-output/throughput/qwen3.6-35b/performance-summary.json) | [html](../self-hosted/vllm/benchmark-output/throughput/qwen3.6-35b/performance-dashboard.html) |
| gemma-4-31b | [json](../self-hosted/vllm/benchmark-output/throughput/gemma-4-31b/performance-summary.json) | [html](../self-hosted/vllm/benchmark-output/throughput/gemma-4-31b/performance-dashboard.html) |
| minimax-m2.5 | [json](../self-hosted/vllm/benchmark-output/throughput/minimax-m2.5/performance-summary.json) | [html](../self-hosted/vllm/benchmark-output/throughput/minimax-m2.5/performance-dashboard.html) |
| deepseek-v3.2 | [json](../self-hosted/vllm/benchmark-output/throughput/deepseek-v3.2/performance-summary.json) | [html](../self-hosted/vllm/benchmark-output/throughput/deepseek-v3.2/performance-dashboard.html) |
| kimi-k2.7-code | [json](../self-hosted/vllm/benchmark-output/throughput/kimi-k2.7-code/performance-summary.json) | [html](../self-hosted/vllm/benchmark-output/throughput/kimi-k2.7-code/performance-dashboard.html) |
| glm-5.2 | [json](../self-hosted/vllm/benchmark-output/throughput/glm-5.2/performance-summary.json) | [html](../self-hosted/vllm/benchmark-output/throughput/glm-5.2/performance-dashboard.html) |
| qwen3-coder-480b | [json](../self-hosted/vllm/benchmark-output/throughput/qwen3-coder-480b/performance-summary.json) | [html](../self-hosted/vllm/benchmark-output/throughput/qwen3-coder-480b/performance-dashboard.html) |
| devstral-2-123b | [json](../self-hosted/vllm/benchmark-output/throughput/devstral-2-123b/performance-summary.json) | [html](../self-hosted/vllm/benchmark-output/throughput/devstral-2-123b/performance-dashboard.html) |
| nemotron-ultra-550b | [json](../self-hosted/vllm/benchmark-output/throughput/nemotron-ultra-550b/performance-summary.json) | [html](../self-hosted/vllm/benchmark-output/throughput/nemotron-ultra-550b/performance-dashboard.html) |

> Figures captured 2026-07-26, vLLM 0.25.1, 200K context; deepseek-v3.2, kimi-k2.7-code, and glm-5.2 re-swept 2026-07-30; devstral-2-123b (TP=4) and nemotron-ultra-550b (full box) added from their p5en sweeps. Costs repriced 2026-08-11 (p5en effective $41.14/hr = on-demand $63.296 x (1 - 0.35 placeholder discount); g6e 3-year RI $4.533/hr) from pricing.json. Re-running a sweep regenerates that model's summary + dashboard; update the tables here when the underlying runs change.
