# Results: omp harness (swe3)

Benchmark results for every model run under the **omp** coding agent with the **swe3** skill on `mcp-gateway-registry`, generated from the committed `run-summary.json` files. Regenerate with `uv run scripts/gen_agent_report.py --harness omp --skill swe3`. Companion to the cross-harness comparison [agentic-coding-swe-comparison-swe3.md](agentic-coding-swe-comparison-swe3.md).

## Results by model

| Model | Mean score | Completed | Input | Output | Cache read | Cache write | Tokens processed† | Wall-clock | Run cost | Cost basis* |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| qwen3.8-27b | 70.32 | 5/5 | 29,642,484 | 334,172 | 68,896,352 | 2,840,251 | 101,713,259 | 870.6m | $23.70 | hardware-derived (g6e.4xlarge) |

\* **Cost basis differs by row and the dollars are NOT directly comparable.** _hardware-derived (throughput)_ (self-hosted vLLM): a rented GPU has no per-token bill, so cost is the model's blended cost-per-token -- measured by the throughput sweep at its true instance rate (g6e.12xlarge for L40S, p5en.48xlarge for H200) and peak concurrency -- times the tokens this run processed. This prices the real work done, unlike a wall-clock estimate that would also charge idle agent-thinking time. See [cost-per-task-methodology.md](cost-per-task-methodology.md).

† **Tokens processed** counts input + output + cache-read + cache-write -- all tokens the model actually processed, not just fresh input+output. On the Bedrock path a task often reports only ~2 fresh input tokens with the rest served from prompt cache, so counting input+output alone would understate the real work ~100x. (Self-hosted rows report their cache reuse via server-side Prometheus counters, folded in here where present.)

A task scoring 0 (missing/empty artifacts) is a model failure, excluded from the mean but counted in `Completed`. A model with 0 scored tasks did not complete any task under this harness.

## Charts

### Cost vs. quality (Pareto frontier)

![Cost vs quality, omp harness](images/cost-quality-omp-swe3.png)

### Quality by dimension (radar)

![Quality radar, omp harness](images/quality-radar-omp-swe3.png)

### Cost vs. accuracy (bubble area = tokens)

x = cost per task, y = mean score, bubble area = total tokens processed, color = hosting basis (metered Bedrock vs hardware-derived self-hosted -- NOT directly comparable as raw dollars; see the cost note above).

![Cost vs accuracy, omp harness](images/cost-accuracy-bubble-omp-swe3.png)
