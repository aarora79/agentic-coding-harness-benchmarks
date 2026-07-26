# Agentic coding model comparison (self-hosted throughput and cost)

How self-hosted open-weight models compare when driven as **agentic coding** engines (Claude Code `/swe2`) on self-hosted GPU instances. This is a **serving-economics** comparison — throughput, latency, and hardware-derived cost per token / per task — not a code-quality one. Quality is scored separately (see the README leaderboard); this doc answers *how much agentic load each model sustains, and what a task really costs*.

All figures come from the throughput skill (`self-hosted/vllm/scripts/run-throughput-sweep.sh`), which drives real `/swe2` sessions at controlled concurrency against the 25-repo multi-repo dataset and reads throughput from vLLM's own server-side counters (DuckDB). Cost is derived, not quoted: `instance $/hr / measured tokens/sec`. See [cost-per-task-methodology.md](cost-per-task-methodology.md) for the cost model and the two lenses, and [serving-optimization-notes.md](serving-optimization-notes.md) for the serving defaults.

## Comparison

Sweep: concurrency `1 2 5 7 10 15 20`, 10-minute window per level, 200K context. Cost is the **blended lens** (every processed token — prompt + generation — costs the same GPU slice; the honest primary metric for an input-heavy workload). "Cheapest $/task" is at each model's most cost-efficient concurrency level.

> **Two different instances.** The smaller models were served on **g6e.12xlarge (4xL40S, $10.49/hr)**; the larger ones on **p5en.48xlarge (8xH200, $42.5-85/hr)**. Cost per token/task already accounts for each instance's hourly price, so it is comparable across rows — but peak-throughput numbers are not apples-to-apples across the instance line. Rows are grouped by instance.

### g6e.12xlarge (4xL40S, $10.49/hr)

| Model | Arch | Peak gen tok/s | Cheapest $/1M (blended) | Cheapest $/task | Task ratio (in:out) | Notes |
|---|---|--:|--:|--:|--:|---|
| **qwen3-coder-30b** | 3B-active MoE | 67 @ c=7 | **$0.15** | $0.40 | ~236:1 | Cheapest per token overall; very heavy input load |
| **qwen3.6-35b** | 3B-active MoE | 145 @ c=1 | $0.22 | **$0.34** | ~50:1 | Fastest tokens on this box; cheapest per task |
| **gemma-4-31b** | dense 31B | 31 @ c=2 | $0.73 | $1.04 | ~67:1 | ~3-5x pricier; dense = slow per token |

### p5en.48xlarge (8xH200)

| Model | Arch | $/hr | Peak gen tok/s | Cheapest $/1M (blended) | Cheapest $/task | Task ratio (in:out) | Notes |
|---|---|--:|--:|--:|--:|--:|---|
| **kimi-k2.7-code** | large MoE | $85.0 | 191 @ c=2 | $1.14 | $2.06 | ~73:1 | Fast, but the H200 box's hourly price dominates |
| **glm-5.2** | large MoE | $85.0 | 212 @ c=15 | $1.51 | $12.51 | ~175:1 | Highest peak throughput; most expensive per task |
| **qwen3-coder-480b** | very large MoE | $42.5 | 49 @ c=2 | $0.72 | $3.10 | ~377:1 | 480B weights; no c=1 baseline in this run (see caveat) |

## Takeaways

- **3B-active MoE economics dominate on a fixed-cost box.** On the same g6e.12xlarge, the dense gemma-4-31b activates all parameters per token, so it is **2-5x slower per token and 3-5x more expensive** than the qwen MoEs that activate only ~3B params per token. Per-token compute tracks the *active*-parameter count, not the total — which is exactly why the self-hosting strategy favors sparse MoEs.

- **Cheapest per *token* is not cheapest per *task*.** qwen3-coder-30b has the lowest per-token cost ($0.15/1M) but qwen3.6-35b is cheapest per *task* ($0.34). The reason is task shape: coder-30b's agentic tasks carry a far heavier input load (~2.75M input : 12K output, ~236:1) than qwen3.6-35b (~50:1), so even at a lower per-token rate the sheer token count per task adds up. **Always compare per-task when choosing a model for a workload** — per-token rates mislead when input:output ratios differ this much.

- **Bigger box, bigger peak — but the hourly price can swamp the cost gain.** The H200 models hit higher peak throughput (glm-5.2 at 212 tok/s, kimi at 191), but at $42.5-85/hr the per-task cost is 5-35x the g6e models'. glm-5.2's $12.51/task is driven by both the $85/hr rate and its very heavy input load. For most agentic-coding serving, the cheaper 4xL40S box with a 3B-active MoE wins on cost per task; the big boxes matter when you need a model that only fits there (e.g. 480B weights) or raw aggregate throughput.

- **All are prefill-heavy but healthy, each with its own concurrency knee.** Agentic coding is input-heavy (large read-heavy prompts, small outputs), so the server spends most of its time on prompt prefill, not generation. On a healthy instance TTFT stays low (0-2s) until the model's concurrency knee, then rises: gemma saturates earliest (~c=2), qwen3-coder-30b holds to ~c=10, qwen3.6-35b stays healthy past c=20. Beyond the knee, add replicas (horizontal scaling), not concurrency — blended per-task cost is flat across replicas, so the per-task figures above are the fleet-scale figures too.

## Caveats on the source runs

- **qwen3-coder-480b has no c=1 baseline** (its sweep started at c=2), so it lacks the uncontended health-check reference the other runs have. Treat its numbers as indicative; a re-run with c=1 would confirm the server was clean. All other runs passed the c=1 check (uncontended TTFT p50 <= 0.5s except qwen3.6-35b at 2.5s, which is still healthy for a dense-prompt cold start).
- **Instance prices are us-east-1 on-demand** as recorded in each run's `dollars_per_hour`. Spot/reserved/negotiated rates would shift the cost columns proportionally (cost scales linearly with $/hr).

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
| kimi-k2.7-code | [json](../self-hosted/vllm/benchmark-output/throughput/kimi-k2.7-code/performance-summary.json) | [html](../self-hosted/vllm/benchmark-output/throughput/kimi-k2.7-code/performance-dashboard.html) |
| glm-5.2 | [json](../self-hosted/vllm/benchmark-output/throughput/glm-5.2/performance-summary.json) | [html](../self-hosted/vllm/benchmark-output/throughput/glm-5.2/performance-dashboard.html) |
| qwen3-coder-480b | [json](../self-hosted/vllm/benchmark-output/throughput/qwen3-coder-480b/performance-summary.json) | [html](../self-hosted/vllm/benchmark-output/throughput/qwen3-coder-480b/performance-dashboard.html) |

> Figures captured 2026-07-26, vLLM 0.25.1, 200K context. Re-running a sweep regenerates that model's summary + dashboard; update the tables here when the underlying runs change.
