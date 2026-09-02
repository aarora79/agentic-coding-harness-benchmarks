# Results: oh-my-pi (omp) harness (swe3)

Benchmark results for every model run under the **oh-my-pi (omp)** coding agent with the **swe3** skill on `mcp-gateway-registry-v2`, generated from the committed `run-summary.json` files. Regenerate with `uv run scripts/gen_agent_report.py --harness omp --skill swe3 --repo mcp-gateway-registry-v2`. See [omp setup](omp-setup.md) for install and configuration. Companion to the cross-harness comparison [agentic-coding-swe-comparison-swe3.md](agentic-coding-swe-comparison-swe3.md).

## Results by model

| Model | Mean score | Completed | Input | Output | Cache read | Cache write | Tokens processed† | Wall-clock | Run cost | Cost basis* |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| claude-opus-5 | 82.83 | 21/21 | 236,155 | 2,025,265 | 339,409,698 | 4,723,756 | 346,394,874 | 448.9m | $251.04 | metered (Bedrock) |
| glm-5.3 | 81.27 | 21/21 | 240,735,711 | 1,604,163 | 242,521,152 | 1,962,956 | 290,134,921 | 150.1m | $169.85 | hardware-derived (p5en.48xlarge) |
| qwen3.8-27b | 78.48 | 20/21 | 232,722,117 | 2,599,816 | 226,013,088 | 7,299,679 | 235,321,933 | 1292.2m | $32.97 | hardware-derived (p5en.48xlarge) |
| claude-sonnet-5 | 76.97 | 21/21 | 120,391 | 1,624,550 | 351,043,732 | 4,562,581 | 357,351,254 | 356.3m | $98.10 | metered (Bedrock) |
| claude-opus-4-7 | 75.60 | 21/21 | 99,273 | 1,140,717 | 212,153,969 | 3,085,952 | 216,479,911 | 226.8m | $154.38 | metered (Bedrock) |
| claude-opus-4-8 | 74.69 | 21/21 | 117,490 | 1,047,405 | 136,713,205 | 2,660,506 | 140,538,606 | 237.2m | $111.76 | metered (Bedrock) |
| claude-opus-4-6-v1 | 70.64 | 21/21 | 113,365 | 643,572 | 148,125,825 | 2,119,578 | 151,002,340 | 206.3m | $103.97 | metered (Bedrock) |
| kimi-k2.7-code | 69.98 | 20/21 | 188,020,732 | 1,054,756 | 184,381,920 | 3,696,196 | 189,075,488 | 200.0m | $68.86 | hardware-derived (p5en.48xlarge) |
| claude-opus-4-5 | 66.32 | 21/21 | 111,338 | 584,372 | 115,999,199 | 2,322,946 | 119,017,855 | 176.6m | $87.68 | metered (Bedrock) |
| deepseek-v3.2 | 60.99 | 21/21 | 171,793,144 | 785,814 | 175,922,048 | 4,580,477 | 212,903,776 | 187.7m | $54.81 | hardware-derived (p5en.48xlarge) |
| gemma-4-31b | 59.74 | 21/21 | 92,628,162 | 506,823 | 89,401,728 | 3,242,130 | 93,134,985 | 344.5m | $18.29 | hardware-derived (p5en.48xlarge) |
| qwen3.6-35b | 59.24 | 21/21 | 160,005,299 | 1,093,921 | 158,821,872 | 3,652,281 | 161,099,220 | 162.5m | $5.45 | hardware-derived (p5en.48xlarge) |
| claude-haiku-4-5 | 56.18 | 21/21 | 33,146 | 610,885 | 96,245,172 | 2,679,349 | 99,568,552 | 110.1m | $16.06 | metered (Bedrock) |
| minimax-m2.5 | 53.29 | 21/21 | 134,127,554 | 432,721 | 132,496,896 | 1,848,978 | 134,560,275 | 65.8m | $10.03 | hardware-derived (p5en.48xlarge) |
| devstral-2-123b | 47.64 | 17/21 | 98,162,838 | 584,442 | 98,849,840 | 955,671 | 102,690,974 | 163.6m | $13.92 | hardware-derived (p5en.48xlarge) |
| qwen3-coder-30b | 42.58 | 21/21 | 138,288,705 | 556,264 | 138,029,360 | 1,455,218 | 138,844,969 | 109.1m | $9.94 | hardware-derived (p5en.48xlarge) |

\* **Cost basis differs by row and the dollars are NOT directly comparable.** _hardware-derived (throughput)_ (self-hosted vLLM): a rented GPU has no per-token bill, so cost is the model's blended cost-per-token -- measured by the p5en.48xlarge throughput sweep at peak concurrency -- times the tokens this run processed. EVERY self-hosted row is priced on that one sweep, including models served on a smaller g6e.12xlarge box, so the fleet shares a single basis and the dollars compare with each other. A row is therefore the cost of that model's work on p5en, not a quote for the box it happened to run on. This prices the real work done, unlike a wall-clock estimate that would also charge idle agent-thinking time. _metered (Bedrock)_: a hosted API's real per-token bill, summed over the run. It is a metered invoice, not a hardware estimate, and (unlike the self-hosted rows) it benefits from Bedrock prompt caching. See [cost-per-task-methodology.md](cost-per-task-methodology.md).

† **Tokens processed** counts input + output + cache-read + cache-write -- all tokens the model actually processed, not just fresh input+output. On the Bedrock path a task often reports only ~2 fresh input tokens with the rest served from prompt cache, so counting input+output alone would understate the real work ~100x. (Self-hosted rows report their cache reuse via server-side Prometheus counters, folded in here where present.)

A task scoring 0 (missing/empty artifacts) is a model failure, excluded from the mean but counted in `Completed`. A model with 0 scored tasks did not complete any task under this harness.

## Charts

### Cost vs. quality (Pareto frontier)

![Cost vs quality, oh-my-pi (omp) harness](images/cost-quality-omp-swe3.png)

### Quality by dimension (radar)

![Quality radar, oh-my-pi (omp) harness](images/quality-radar-omp-swe3.png)

### Cost vs. accuracy (bubble area = tokens)

x = cost per task, y = mean score, bubble area = total tokens processed, color = hosting basis (metered Bedrock vs hardware-derived self-hosted -- NOT directly comparable as raw dollars; see the cost note above).

![Cost vs accuracy, oh-my-pi (omp) harness](images/cost-accuracy-bubble-omp-swe3.png)
