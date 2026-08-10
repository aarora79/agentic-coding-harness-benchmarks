# Results: Claude Code harness (swe2)

Benchmark results for every model run under the **Claude Code** coding agent with the **swe2** skill on `mcp-gateway-registry`, generated from the committed `run-summary.json` files. Regenerate with `uv run scripts/gen_agent_report.py --harness claude-code --skill swe2`. Companion to the cross-harness comparison [agentic-coding-swe-comparison-swe2.md](agentic-coding-swe-comparison-swe2.md).

## Results by model

| Model | Mean score | Completed | Input | Output | Cache read | Cache write | Tokens processed† | Wall-clock | Run cost | Cost basis* |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| claude-opus-4-8 | 79.12 | 5/5 | 29,721 | 743,666 | 147,727,073 | 1,463,549 | 149,964,009 | 178.1m | $135.69 | metered (Bedrock) |
| claude-sonnet-5 | 76.96 | 5/5 | 27,739 | 1,062,850 | 366,969,078 | 2,191,148 | 370,250,815 | 276.7m | $181.30 | metered (Bedrock) |
| claude-opus-5 | 76.00 | 5/5 | 47,618 | 653,865 | 82,266,236 | 1,978,386 | 84,946,105 | 241.1m | $180.73 | metered (Bedrock) |
| kimi-k2.7-code | 73.69 | 4/5 | 8,896,632 | 122,386 | 0 | 0 | 9,019,018 | 51.2m | $7.50 | hardware-derived (p5en.48xlarge) |
| glm-5.2 | 72.75 | 5/5 | 11,352,314 | 205,272 | 0 | 0 | 11,557,586 | 73.2m | $12.81 | hardware-derived (p5en.48xlarge) |
| deepseek-v3.2 | 52.20 | 5/5 | 40,665,827 | 250,576 | 0 | 0 | 40,916,403 | 80.3m | $24.05 | hardware-derived (p5en.48xlarge) |
| minimax-m2.5 | 51.35 | 5/5 | 6,194,113 | 61,230 | 0 | 0 | 6,255,343 | 10.1m | $1.07 | hardware-derived (p5en.48xlarge) |
| qwen3.6-35b | 50.32 | 5/5 | 23,331,803 | 209,391 | 0 | 0 | 23,541,194 | 88.4m | $5.13 | hardware-derived (g6e.12xlarge) |
| nemotron-ultra-550b | 50.20 | 4/5 | 32,598,732 | 204,053 | 0 | 0 | 32,802,785 | 70.2m | $14.34 | hardware-derived (p5en.48xlarge) |
| gemma-4-31b | 48.40 | 5/5 | 24,682,418 | 160,182 | 0 | 0 | 24,842,600 | 213.0m | $18.09 | hardware-derived (g6e.12xlarge) |
| claude-haiku-4-5 | 45.64 | 5/5 | 293 | 137,405 | 19,785,473 | 580,026 | 20,503,197 | 21.6m | $6.15 | metered (Bedrock) |
| qwen3-coder-480b | 44.95 | 4/5 | 66,047,338 | 186,498 | 0 | 0 | 66,233,836 | 68.2m | $35.69 | hardware-derived (p5en.48xlarge) |
| devstral-2-123b | 43.12 | 5/5 | 27,990,077 | 128,406 | 0 | 0 | 28,118,483 | 50.6m | $8.70 | hardware-derived (p5en.48xlarge) |
| qwen3-coder-30b | 30.20 | 4/5 | 50,532,008 | 193,911 | 0 | 0 | 50,725,919 | 84.2m | $7.38 | hardware-derived (g6e.12xlarge) |
| qwen3-coder-next | -- (0 scored) | 0/1 | 0 | 0 | 0 | 0 | 0 | 3.1m | -- | hardware-derived |

\* **Cost basis differs by row and the dollars are NOT directly comparable.** _hardware-derived (throughput)_ (self-hosted vLLM): a rented GPU has no per-token bill, so cost is the model's blended cost-per-token -- measured by the throughput sweep at its true instance rate (g6e.12xlarge for L40S, p5en.48xlarge for H200) and peak concurrency -- times the tokens this run processed. This prices the real work done, unlike a wall-clock estimate that would also charge idle agent-thinking time. _metered (Bedrock)_: a hosted API's real per-token bill, summed over the run. It is a metered invoice, not a hardware estimate, and (unlike the self-hosted rows) it benefits from Bedrock prompt caching. See [cost-per-task-methodology.md](cost-per-task-methodology.md).

† **Tokens processed** counts input + output + cache-read + cache-write -- all tokens the model actually processed, not just fresh input+output. On the Bedrock path a task often reports only ~2 fresh input tokens with the rest served from prompt cache, so counting input+output alone would understate the real work ~100x. (Self-hosted rows report their cache reuse via server-side Prometheus counters, folded in here where present.)

A task scoring 0 (missing/empty artifacts) is a model failure, excluded from the mean but counted in `Completed`. A model with 0 scored tasks did not complete any task under this harness.

## Charts

### Cost vs. quality (Pareto frontier)

![Cost vs quality, Claude Code harness](images/cost-quality-cc-swe2.png)

### Quality by dimension (radar)

![Quality radar, Claude Code harness](images/quality-radar-cc-swe2.png)

### Cost vs. accuracy (bubble area = tokens)

x = cost per task, y = mean score, bubble area = total tokens processed, color = hosting basis (metered Bedrock vs hardware-derived self-hosted -- NOT directly comparable as raw dollars; see the cost note above).

![Cost vs accuracy, Claude Code harness](images/cost-accuracy-bubble-cc-swe2.png)
