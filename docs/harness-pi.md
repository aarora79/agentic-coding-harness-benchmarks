# Results: pi harness

Benchmark results for every model run under the **pi** coding agent on `mcp-gateway-registry`, generated from the committed `run-summary.json` files. Regenerate with `uv run scripts/gen_agent_report.py --harness pi`. Companion to the cross-agent [harness comparison](harness-comparison.md).

## Results by model

| Model | Mean score | Completed | Input | Output | Cache read | Cache write | Tokens processed† | Wall-clock | Run cost | Cost basis* |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| claude-opus-5 | 71.40 | 5/5 | 10 | 6,272 | 896,737 | 3,550 | 906,569 | 88.1m | $0.63 | metered (Bedrock) |
| qwen3.6-35b | 47.15 | 4/5 | 609,647 | 17,757 | 26,707,296 | 672,843 | 28,007,543 | 29.4m | $5.14 | hardware-derived |
| gemma-4-31b | 43.52 | 5/5 | 597,747 | 2,920 | 18,498,976 | 525,688 | 19,625,331 | 60.8m | $10.63 | hardware-derived |
| qwen3-coder-30b | -- (0 scored) | 0/5 | 407,989 | 2,061 | 12,508,624 | 313,139 | 13,231,813 | 17.0m | $2.98 | hardware-derived |

\* **Cost basis differs by row and the dollars are NOT directly comparable.** _hardware-derived_ (self-hosted vLLM): a rented GPU has no per-token bill, so cost is `($/hr / 3600) x wall-clock seconds` at g6e.12xlarge on-demand ($10.49/hr). _metered (Bedrock)_: a hosted API's real per-token bill, summed over the run. It is a metered invoice, not a hardware estimate, and (unlike the self-hosted rows) it benefits from Bedrock prompt caching. See [cost-per-task-methodology.md](cost-per-task-methodology.md).

† **Tokens processed** counts input + output + cache-read + cache-write -- all tokens the model actually processed, not just fresh input+output. On the Bedrock path a task often reports only ~2 fresh input tokens with the rest served from prompt cache, so counting input+output alone would understate the real work ~100x. (Self-hosted rows report their cache reuse via server-side Prometheus counters, folded in here where present.)

A task scoring 0 (missing/empty artifacts) is a model failure, excluded from the mean but counted in `Completed`. A model with 0 scored tasks did not complete any task under this harness.

## Charts

### Cost vs. quality (Pareto frontier)

![Cost vs quality, pi harness](images/cost-quality-pi.png)

### Quality by dimension (radar)

![Quality radar, pi harness](images/quality-radar-pi.png)
