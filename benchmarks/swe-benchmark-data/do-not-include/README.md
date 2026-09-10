# do-not-include

Benchmark runs kept as data points but held off the frontier, the charts and the vended `swe-router` model list.

## How the exclusion works

Every chart and frontier generator discovers models with a **shallow** scan of `swe-benchmark-data/`:

```python
for model_dir in sorted(p for p in data_dir.iterdir() if p.is_dir()):
    repo_dir = model_dir / harness / skill / repo
    if not repo_dir.is_dir():
        continue
```

A run nested one level deeper is invisible to that scan. `do-not-include` is itself seen as a directory, but `do-not-include/<harness>/<skill>/<repo>` never exists, so it is skipped and nothing downstream sees the runs beneath it. [build_vended_models.py](../../scripts/build_vended_models.py) globs `*/{harness}/{skill}/{dataset}/run-summary.json`, whose single `*` sits at the model level, so a nested path does not match there either.

Moving a model directory in or out of here is therefore the whole mechanism. There is no denylist in code to keep in sync.

**Do not "fix" this by deleting a model's `performance-summary.json` instead.** [plot_cost_quality.py](../../scripts/plot_cost_quality.py) falls back to the run-summary cost estimate when no performance summary exists, and to `0.0` when that is missing too -- so a model with no cost data plots as free and dominates the frontier. Nesting the run is the safe removal; deleting its cost is not.

## What is in here, and why

### qwen3.6-35b-fp8

Qwen3.6-35B-A3B in FP8 on a single L40S (`g6e.4xlarge`), driven by omp on `/swe3` over `mcp-gateway-registry-v2`. Run 2026-09-10. All 21 tasks scored, no failures, mean **59.23** against the BF16 4x L40S run's **59.24** -- the same model at a different precision on a twelfth of the GPUs, and statistically indistinguishable on quality (mean per-task delta -0.01, sd 7.81, 95% CI -3.35 to +3.33).

It is excluded on **cost basis**, not on quality. Two reasons, either of which alone is disqualifying:

1. **Its throughput sweep is on a different hardware basis from the fleet.** Every self-hosted point on the published frontier is priced on the canonical `p5en.48xlarge` arm so the whole fleet shares one basis. This model was swept on `g6e.4xlarge` at $1.298/hr, and there is no p5en sweep for it. Charting it would put two hardware bases on one cost axis, which [plot_cost_quality.py](../../scripts/plot_cost_quality.py) explicitly warns against.
2. **Its token counts are confounded with context window.** It ran at `MAX_MODEL_LEN=262144` against the BF16 run's 200000. A larger window means less auto-compaction and a bigger transcript replayed per turn, and it used roughly double the tokens per task (10.1M input vs 5.2M) for the same score. Whether that is the quantisation or the window is unresolved, and separating them needs an FP8 run at 200000 that is not planned.

On its own g6e basis it costs **$0.556 per task** at concurrency 10, against **$0.493** for BF16 on 4x L40S recomputed on the same task tokens. The cheaper hardware does not win, because the box sustains a quarter of the throughput (67 tok/s peak against 145) and the model spends twice the tokens.

The serving guide is [qwen3.6-35b-a3b-fp8.md](../../../self-hosted/vllm/models/qwen3.6-35b-a3b-fp8.md); the throughput measurement stays at `self-hosted/vllm/benchmark-output/throughput/qwen3.6-35b-fp8/`, where it is a valid record of what one L40S sustains and is unreachable from the charts while this run is nested here.

**What it is good for.** It shows the model runs at full 256K context on a $1.298/hr single-GPU box at the same quality as its BF16 parent. That is a useful answer for anyone sizing a single-developer or small-team deployment, where the hourly rate matters more than throughput-normalised cost per task.
