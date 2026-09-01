# Agentic coding model comparison (self-hosted throughput and cost)

How self-hosted open-weight models compare when driven as **agentic coding** engines on self-hosted GPU instances. This is a **serving-economics** comparison — throughput, latency, and hardware-derived cost per token / per task — not a code-quality one. Quality is scored separately (see the README leaderboard and the per-harness [swe2](agentic-coding-swe-comparison-swe2.md) / [swe3](agentic-coding-swe-comparison-swe3.md) comparisons); this doc answers *how much agentic load each model sustains, and what a task really costs*.

All figures come from the throughput skill (`self-hosted/vllm/scripts/run-throughput-sweep.sh`), which replays agentic-coding-shaped traffic at controlled concurrency and reads throughput from vLLM's own server-side counters (DuckDB). It is a **synthetic throughput sweep that measures the server, not any one harness or skill** — the numbers here are independent of whether the model is later driven by Claude Code or pi, or by the swe2 (multi-agent) or swe3 (single-agent) skill. Cost is derived, not quoted: `instance $/hr / measured tokens/sec`. See [cost-per-task-methodology.md](cost-per-task-methodology.md) for the cost model and the two lenses, and [serving-optimization-notes.md](serving-optimization-notes.md) for the serving defaults.

**Config used (so this is reproducible):**
- **Dataset:** [`benchmarks/dataset/multi-repo-throughput.yaml`](../benchmarks/dataset/multi-repo-throughput.yaml) — **one task per repo across 25 different public repos** in six languages (10 Python, 5 Java, 3 Rust, 2 Go, 2 JS, 3 HTML/CSS), so N concurrent slots each hammer a *different* repo (realistic fleet load). This is deliberately **not** the single-repo `mcp-gateway-registry.yaml` used by the quality benchmarks — throughput is measured against the 25-repo mix, code quality against the one repo.
- **Runner:** [`benchmarks/config/runner.yaml`](../benchmarks/config/runner.yaml) (passed as `--config config/runner.yaml`).

## Comparison

Sweep: concurrency `1 2 5 7 10 15 20`, 10-minute window per level, 200K context. Cost is the **blended lens** (every processed token — prompt + generation — costs the same GPU slice; the honest primary metric for an input-heavy workload). "Cheapest $/task" is at each model's most cost-efficient concurrency level. The per-task token shape used here (`in:out`) is the sweep's synthetic definition; real agentic runs range wider (~50:1 to ~660:1 across models under the single-agent swe3 skill — see [cost-per-task-methodology.md](cost-per-task-methodology.md)), and per-token cost is a property of the model + hardware + load, so recost any real task shape with `clients/cost_for_task.py`.

> [!IMPORTANT]
> **Both instance families are priced at their 3-year commitment rate**, from [`self-hosted/vllm/pricing.json`](../self-hosted/vllm/pricing.json): g6e.12xlarge **$4.533/hr**, p5en.48xlarge **$27.72/hr** (the 3-year EC2 Instance Savings Plan rate). One commitment term across the fleet, so the cost columns are comparable across the instance line. Each entry's `rates` map also records on-demand and 1-year (p5en: $63.296 and $40.43) for reference. Every self-hosted cost below rescales linearly with the rate, so a different term is one multiplication away.

> **One canonical instance, one alternative basis.** Every model's headline row is a **p5en.48xlarge (8xH200)** sweep, charged at the footprint it actually used: $27.72/hr for the full box, $13.86/hr at TP=4, $3.465/hr for a single H200. That is deliberate -- one instance family and one commitment term means the cost columns are comparable fleet-wide, and peak-throughput numbers only need the GPU count read alongside them. Three small models were *also* swept on a whole **g6e.12xlarge (4xL40S, $4.533/hr)**; those rows are kept below as the alternative basis. Rates come from [`self-hosted/vllm/pricing.json`](../self-hosted/vllm/pricing.json) (us-east-1).

### p5en.48xlarge (8xH200)

The whole self-hosted fleet is now swept on this one instance family, at three footprints: the **full box** ($27.72/hr), **half a box** (TP=4, $13.86/hr), and **a single H200** (TP=1, $3.465/hr). Rows are ordered by cheapest $/1M. The `$/task` column uses **each sweep's own blended task definition**, so it is comparable across the rows that share a shape (~8M input : 50K output, ~160:1 for the large MoEs) but *not* against the small models, which carry their real measured shapes -- compare `$/1M` for a shape-free read.

| Model | Arch | GPUs | $/hr | Peak gen tok/s | Cheapest $/1M (blended) | Cheapest $/task | Task ratio (in:out) | Notes |
|---|---|--:|--:|--:|--:|--:|--:|---|
| **qwen3.6-35b** | 3B-active MoE | 1 | $3.465 | 330 @ c=10 | **$0.03** | $0.05 | ~50:1 | Cheapest per token in the fleet; a single H200 beats 4x L40S 2.3x on throughput and 3x on cost |
| **minimax-m2.5** | small-active MoE | 4 | $13.86 | 300 @ c=15 | $0.07 | $0.09 | ~101:1 | TP=4 (half the box); cheapest per task on this instance |
| **qwen3-coder-30b** | 3B-active MoE | 1 | $3.465 | 43 @ c=5 | $0.07 | $0.20 | ~236:1 | The one model the L40S box serves *more* cheaply ($0.06/1M on 4x L40S) -- it scales on GPU count, not GPU class |
| **devstral-2-123b** | dense 123B | 4 | $13.86 | 128 @ c=5 | $0.13 | $0.76 | ~218:1 | TP=4 (half the box); cheap per task despite dense arch |
| **qwen3.8-27b** | dense 27B | 1 | $3.465 | **357 @ c=30** | $0.14 | $1.13 | ~160:1 | Highest peak throughput in the fleet, from one GPU; measured at 65K context (see caveat) |
| **nemotron-ultra-550b** | dense 550B | 8 | $27.72 | 244 @ c=10 | $0.19 | $0.76 | ~103:1 | Full box; strong aggregate throughput keeps per-task cost low |
| **gemma-4-31b** | dense 31B | 1 | $3.465 | 43 @ c=20 | $0.20 | $0.28 | ~67:1 | Dense = slow per token, but 1.4x the L40S box's throughput at 0.6x its per-token cost |
| **qwen3-coder-480b** | very large MoE | 4 | $13.86 | 49 @ c=2 | $0.24 | $1.01 | ~377:1 | 480B weights; no c=1 baseline in this run (see caveat) |
| **deepseek-v3.2** | large MoE | 8 | $27.72 | 173 @ c=5 | $0.26 | $2.08 | ~160:1 | Cheapest of the full-box H200 models per token and per task |
| **kimi-k2.7-code** | large MoE | 8 | $27.72 | 274 @ c=5 | $0.36 | $2.93 | ~160:1 | Fast; the H200 box's hourly price dominates |
| **glm-5.2** | large MoE | 8 | $27.72 | 190 @ c=10 | $0.49 | $3.90 | ~160:1 | The quality anchor; expensive per task on this box |
| **glm-5.3** | 39B-active MoE (743B) | 8 | $27.72 | 152 @ c=10 | $0.59 | $4.71 | ~160:1 | Most expensive per task here: 39B active per token, 4x glm-5.2's active count |

### g6e.12xlarge (4xL40S, $4.533/hr, 3-year commitment) -- the alternative basis

Three of the small models were first swept here, on a whole 4-GPU L40S box. Those sweeps are kept as `-g6e` siblings (`throughput/qwen3.6-35b-g6e/` and so on) because the bare model directory now names the **canonical** p5en arm; see [gpu-selection-h200-vs-l40s.md](gpu-selection-h200-vs-l40s.md) for the head-to-head. Rows here are that L40S basis, not the fleet basis.

| Model | Arch | Peak gen tok/s | Cheapest $/1M (blended) | Cheapest $/task | Task ratio (in:out) | Notes |
|---|---|--:|--:|--:|--:|---|
| **qwen3-coder-30b** | 3B-active MoE | 67 @ c=7 | **$0.06** | $0.17 | ~236:1 | Cheapest per token overall; very heavy input load |
| **qwen3.6-35b** | 3B-active MoE | 145 @ c=1 | $0.10 | **$0.14** | ~50:1 | Fastest tokens on this box; cheapest per task |
| **gemma-4-31b** | dense 31B | 31 @ c=2 | $0.32 | $0.45 | ~67:1 | ~3-5x pricier; dense = slow per token |

## Takeaways

- **3B-active MoE economics dominate on a fixed-cost box.** On the same box -- whether that is the g6e.12xlarge or a single H200 -- the dense gemma-4-31b activates all parameters per token, so it is **2-5x slower per token and 3-6x more expensive** than the qwen MoEs that activate only ~3B params per token (on one H200: gemma $0.20/1M against qwen3.6-35b's $0.03). Per-token compute tracks the *active*-parameter count, not the total — which is exactly why the self-hosting strategy favors sparse MoEs.

- **Cheapest per *token* is not cheapest per *task*.** On the L40S box qwen3-coder-30b has the lowest per-token cost ($0.06/1M) yet qwen3.6-35b is cheapest per *task* ($0.14); on the canonical single-H200 basis qwen3.6-35b wins both ($0.03/1M, $0.05/task) and coder-30b's per-task cost is 4x higher ($0.20) off a near-identical $/1M. The reason is task shape: coder-30b's agentic tasks carry a far heavier input load (~2.75M input : 12K output, ~236:1) than qwen3.6-35b (~50:1), so even at a lower per-token rate the sheer token count per task adds up. **Always compare per-task when choosing a model for a workload** — per-token rates mislead when input:output ratios differ this much.

- **Bigger box, bigger peak — but the hourly price can swamp the cost gain, unless the model is a small-active MoE that only needs half the box.** The full-box H200 models hit solid peak throughput (kimi at 274 tok/s, nemotron at 244, glm-5.2 at 190, deepseek at 173), but at $27.72/hr their per-task cost is generally several times the g6e models'. glm-5.2's $3.90/task is driven by both the $27.72/hr rate and its very heavy input load. The full-box exception is **nemotron-ultra-550b** at just **$0.76/task**: strong aggregate throughput (244 gen tok/s @ c=10) plus a lighter task ratio (~103:1) mean far fewer tokens per task, so even at full-box price it undercuts deepseek-v3.2 ($2.08) and the other large MoEs — a reminder that per-task cost tracks throughput x task-shape, not just the hourly rate. The standout exception is **minimax-m2.5**: a small-active MoE that fits at TP=4 (half the H200 box, so $13.86/hr) yet posts the **highest peak throughput here (300 tok/s @ c=15) and the cheapest cost of any p5en model ($0.07/1M, $0.09/task)** — beating the g6e MoEs on cost while serving from the big box. Active-parameter count and the half-instance footprint, not total size or instance tier, drive the economics: minimax-m2.5 and qwen3-coder-480b both run TP=4 at $13.86/hr, but minimax is ~6x faster and ~11x cheaper per task because its per-token compute (and KV pressure) is far lower. The big boxes still matter when you need a model that only fits there (e.g. 480B weights) or raw aggregate throughput.

- **The cheapest way to buy an H200 is one eighth of a p5en.** A single H200 at $3.465/hr serves every model under ~35B, and it beats a whole 4-GPU L40S box on both axes for two of the three: qwen3.6-35b runs **2.3x faster** (330 vs 145 gen tok/s) at **a third the per-token cost**, and gemma-4-31b 1.4x faster at 0.6x the cost -- one better GPU against four worse ones, for a third of the hourly price. qwen3-coder-30b is the counter-example: it is slower on one H200 (43 vs 67 tok/s) and slightly pricier per token, because its very heavy prefill scales with aggregate GPU count rather than per-GPU class. The full head-to-head is [gpu-selection-h200-vs-l40s.md](gpu-selection-h200-vs-l40s.md).

- **All are prefill-heavy but healthy, each with its own concurrency knee.** Agentic coding is input-heavy (large read-heavy prompts, small outputs), so the server spends most of its time on prompt prefill, not generation. On a healthy instance TTFT stays low (0-2s) until the model's concurrency knee, then rises: gemma saturates earliest (~c=2), qwen3-coder-30b holds to ~c=10, qwen3.6-35b stays healthy past c=20. minimax-m2.5 holds sub-second TTFT all the way to c=15 (its peak) then falls off a cliff at c=20 (throughput 300->127 tok/s, TTFT ~8.5s) as KV finally saturates — a sharp, well-defined knee. Beyond the knee, add replicas (horizontal scaling), not concurrency — blended per-task cost is flat across replicas, so the per-task figures above are the fleet-scale figures too.

## Caveats on the source runs

- **qwen3-coder-480b has no c=1 baseline** (its sweep started at c=2), so it lacks the uncontended health-check reference the other runs have. Treat its numbers as indicative; a re-run with c=1 would confirm the server was clean. All other runs passed the c=1 check (uncontended TTFT p50 <= 0.5s except qwen3.6-35b at 2.5s, which is still healthy for a dense-prompt cold start).
- **The four small models' headline rows are 2026-08-31 re-sweeps on a single H200**, not the original g6e runs; the bare `throughput/{model}` directory is that canonical p5en arm and the L40S sweep is its `-g6e` sibling. Each side carries its own per-task token shape, so `$/task` is comparable arm to arm for one model but not model to model.
- **qwen3.8-27b was swept at a 65,536-token context window**, not 200K: one GPU cannot hold a long window and useful concurrency at once. Its peak (357 gen tok/s @ c=30) is therefore not directly comparable with the 200K rows above.
- **Instance prices are the 3-year commitment rates** (p5en.48xlarge $27.72/hr, g6e.12xlarge $4.533/hr) as recorded in each run's `dollars_per_hour`. On-demand, 1-year, spot, or your own negotiated rate shifts the cost columns proportionally (cost is linear in $/hr), which is what [`clients/reprice_performance_summary.py`](../self-hosted/vllm/clients/reprice_performance_summary.py) does to a committed summary.
- **The p5en costs were repriced on 2026-09-01**, from an earlier basis of on-demand $63.296/hr times a `0.35` **placeholder** discount ($41.1424/hr effective). That placeholder was a guess presented in the same field as a measured price; it is gone, and `pricing.py` now rejects a leftover `discount` key. Repriced figures are exactly what a rebuild at the new rate would produce (cost is linear in $/hr and nothing measured changed), and each affected summary records the factor under `_repriced`.

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
| qwen3-coder-30b (p5en, TP=1) | [json](../self-hosted/vllm/benchmark-output/throughput/qwen3-coder-30b/performance-summary.json) | [html](../self-hosted/vllm/benchmark-output/throughput/qwen3-coder-30b/performance-dashboard.html) |
| qwen3-coder-30b (g6e) | [json](../self-hosted/vllm/benchmark-output/throughput/qwen3-coder-30b-g6e/performance-summary.json) | [html](../self-hosted/vllm/benchmark-output/throughput/qwen3-coder-30b-g6e/performance-dashboard.html) |
| qwen3.6-35b (p5en, TP=1) | [json](../self-hosted/vllm/benchmark-output/throughput/qwen3.6-35b/performance-summary.json) | [html](../self-hosted/vllm/benchmark-output/throughput/qwen3.6-35b/performance-dashboard.html) |
| qwen3.6-35b (g6e) | [json](../self-hosted/vllm/benchmark-output/throughput/qwen3.6-35b-g6e/performance-summary.json) | [html](../self-hosted/vllm/benchmark-output/throughput/qwen3.6-35b-g6e/performance-dashboard.html) |
| gemma-4-31b (p5en, TP=1) | [json](../self-hosted/vllm/benchmark-output/throughput/gemma-4-31b/performance-summary.json) | [html](../self-hosted/vllm/benchmark-output/throughput/gemma-4-31b/performance-dashboard.html) |
| gemma-4-31b (g6e) | [json](../self-hosted/vllm/benchmark-output/throughput/gemma-4-31b-g6e/performance-summary.json) | [html](../self-hosted/vllm/benchmark-output/throughput/gemma-4-31b-g6e/performance-dashboard.html) |
| qwen3.8-27b (p5en, TP=1) | [json](../self-hosted/vllm/benchmark-output/throughput/qwen3.8-27b/performance-summary.json) | [html](../self-hosted/vllm/benchmark-output/throughput/qwen3.8-27b/performance-dashboard.html) |
| qwen3.8-27b (g6e.4xlarge) | [json](../self-hosted/vllm/benchmark-output/throughput/qwen3.8-27b-g6e/performance-summary.json) | [html](../self-hosted/vllm/benchmark-output/throughput/qwen3.8-27b-g6e/performance-dashboard.html) |
| minimax-m2.5 | [json](../self-hosted/vllm/benchmark-output/throughput/minimax-m2.5/performance-summary.json) | [html](../self-hosted/vllm/benchmark-output/throughput/minimax-m2.5/performance-dashboard.html) |
| deepseek-v3.2 | [json](../self-hosted/vllm/benchmark-output/throughput/deepseek-v3.2/performance-summary.json) | [html](../self-hosted/vllm/benchmark-output/throughput/deepseek-v3.2/performance-dashboard.html) |
| kimi-k2.7-code | [json](../self-hosted/vllm/benchmark-output/throughput/kimi-k2.7-code/performance-summary.json) | [html](../self-hosted/vllm/benchmark-output/throughput/kimi-k2.7-code/performance-dashboard.html) |
| glm-5.2 | [json](../self-hosted/vllm/benchmark-output/throughput/glm-5.2/performance-summary.json) | [html](../self-hosted/vllm/benchmark-output/throughput/glm-5.2/performance-dashboard.html) |
| glm-5.3 | [json](../self-hosted/vllm/benchmark-output/throughput/glm-5.3/performance-summary.json) | [html](../self-hosted/vllm/benchmark-output/throughput/glm-5.3/performance-dashboard.html) |
| qwen3-coder-480b | [json](../self-hosted/vllm/benchmark-output/throughput/qwen3-coder-480b/performance-summary.json) | [html](../self-hosted/vllm/benchmark-output/throughput/qwen3-coder-480b/performance-dashboard.html) |
| devstral-2-123b | [json](../self-hosted/vllm/benchmark-output/throughput/devstral-2-123b/performance-summary.json) | [html](../self-hosted/vllm/benchmark-output/throughput/devstral-2-123b/performance-dashboard.html) |
| nemotron-ultra-550b | [json](../self-hosted/vllm/benchmark-output/throughput/nemotron-ultra-550b/performance-summary.json) | [html](../self-hosted/vllm/benchmark-output/throughput/nemotron-ultra-550b/performance-dashboard.html) |

> Figures captured 2026-07-26, vLLM 0.25.1, 200K context; deepseek-v3.2, kimi-k2.7-code, and glm-5.2 re-swept 2026-07-30; devstral-2-123b (TP=4) and nemotron-ultra-550b (full box) added from their p5en sweeps; qwen3.6-35b, gemma-4-31b, qwen3-coder-30b, and qwen3.8-27b re-swept 2026-08-31 on a single H200 (TP=1), which is now their canonical arm; glm-5.3 (full box, TP=8) added 2026-08-31. Costs repriced 2026-09-01 to the 3-year commitment rates in pricing.json (p5en.48xlarge $27.72/hr, g6e.12xlarge $4.533/hr), replacing an earlier p5en basis of on-demand x a 0.35 placeholder discount. Re-running a sweep regenerates that model's summary + dashboard; update the tables here when the underlying runs change.
