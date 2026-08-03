# Results: Claude Code harness

Benchmark results for every model run under the **Claude Code** coding agent on `mcp-gateway-registry`, generated from the committed `run-summary.json` files. Regenerate with `uv run scripts/gen_agent_report.py --harness claude-code`. Companion to the cross-agent [harness comparison](harness-comparison.md).

## Results by model

| Model | Mean score | Completed | Tokens processed† | Wall-clock | Run cost | Cost basis* |
|---|---:|---:|---:|---:|---:|---|
| claude-opus-5 | 76.00 | 5/5 | 84,946,105 | 241.1m | $180.73 | metered (Bedrock) |
| claude-opus-4-8 | 75.32 | 5/5 | 507,617 | 127.9m | $87.12 | metered (Bedrock) |
| claude-sonnet-5 | 73.32 | 5/5 | 185,990,651 | 203.7m | $110.26 | metered (Bedrock) |
| glm-5.2 | 61.96 | 5/5 | 50,051,636 | 65.0m | $11.37 | hardware-derived |
| kimi-k2.7-code | 58.68 | 5/5 | 47,675,538 | 130.3m | $22.79 | hardware-derived |
| deepseek-v3.2 | 52.20 | 5/5 | 40,916,403 | 80.3m | $14.04 | hardware-derived |
| minimax-m2.5 | 51.56 | 5/5 | 33,957,716 | 22.7m | $3.97 | hardware-derived |
| qwen3.6-35b | 50.32 | 5/5 | 23,541,194 | 88.4m | $15.46 | hardware-derived |
| nemotron-ultra-550b | 50.20 | 4/5 | 32,802,785 | 70.2m | $12.27 | hardware-derived |
| gemma-4-31b | 48.40 | 5/5 | 24,842,600 | 213.0m | $37.24 | hardware-derived |
| claude-haiku-4-5-20251001-v1:0 | 47.92 | 5/5 | 166,140 | 28.4m | $6.54 | metered (Bedrock) |
| qwen3-coder-480b | 44.95 | 4/5 | 66,233,836 | 68.2m | $11.93 | hardware-derived |
| devstral-2-123b | 43.12 | 5/5 | 28,118,483 | 50.6m | $8.84 | hardware-derived |
| qwen3-coder-30b | 30.20 | 4/5 | 50,725,919 | 84.2m | $14.71 | hardware-derived |

\* **Cost basis differs by row and the dollars are NOT directly comparable.** _hardware-derived_ (self-hosted vLLM): a rented GPU has no per-token bill, so cost is `($/hr / 3600) x wall-clock seconds` at g6e.12xlarge on-demand ($10.49/hr). _metered (Bedrock)_: a hosted API's real per-token bill, summed over the run. It is a metered invoice, not a hardware estimate, and (unlike the self-hosted rows) it benefits from Bedrock prompt caching. See [cost-per-task-methodology.md](cost-per-task-methodology.md).

† **Tokens processed** counts input + output + cache-read + cache-write -- all tokens the model actually processed, not just fresh input+output. On the Bedrock path a task often reports only ~2 fresh input tokens with the rest served from prompt cache, so counting input+output alone would understate the real work ~100x. (Self-hosted rows report their cache reuse via server-side Prometheus counters, folded in here where present.)

A task scoring 0 (missing/empty artifacts) is a model failure, excluded from the mean but counted in `Completed`. A model with 0 scored tasks did not complete any task under this harness.

## Charts

### Cost vs. quality (Pareto frontier)

![Cost vs quality, Claude Code harness](images/cost-quality-cc.png)

### Quality by dimension (radar)

![Quality radar, Claude Code harness](images/quality-radar-cc.png)
