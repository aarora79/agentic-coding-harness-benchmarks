# Agentic coding: model comparison on /swe2 (quality, tokens, cost)

How every benchmarked model compares as an **agentic coding** engine on real `/swe2` tasks against `mcp-gateway-registry`, under **both harnesses** (Claude Code and pi). Unlike the serving-economics view in [agentic-coding-throughput-comparison.md](agentic-coding-throughput-comparison.md) (synthetic throughput sweep), this doc is built from the actual benchmark runs and combines the three axes a buyer trades off -- **quality, tokens, and cost** -- plus wall-clock latency.

Generated from the committed `run-summary.json` files; regenerate with `uv run scripts/gen_swe_comparison.py --skill swe2`. Numbers match the per-harness docs ([Claude Code](harness-claude-code-swe2.md), [pi](harness-pi-swe2.md)) and the charts below exactly.

## Cost basis (read this first)

Two non-comparable cost bases share the cost columns; each row states which:

- **metered (Bedrock)** -- a hosted API's real per-token bill, summed over the run. Benefits from Bedrock prompt caching.
- **hardware-derived (self-hosted)** -- a rented GPU has no per-token bill, so cost is the model's blended $/token (measured by the throughput sweep at its true instance rate -- g6e.12xlarge for L40S, p5en.48xlarge for H200) times the tokens the run processed. See [cost-per-task-methodology.md](cost-per-task-methodology.md).

`Cost/task` = run cost / scored tasks. `Cost/point` = run cost / mean score -- a value-efficiency figure (lower is more quality per dollar).

## Does the harness matter?

For every model run under both harnesses, this compares Claude Code vs pi on each metric. Each row is one model; the connector points to the better harness (higher score / lower cost, tokens, latency), and each panel title tallies how often pi wins. Comparing one model's two harnesses is fair even for cost -- its hosting basis is identical under both.

![Harness comparison, swe2](images/harness-delta-swe2.png)

### Reading the chart (author-maintained)

> The win-tallies above are mechanical. The prose below is **hand-written reasoning** about what the chart means for a model choice -- the kind of cross-metric judgement code cannot produce. It is written from the machine-readable data behind the charts: [`metrics/harness-delta-swe2.json`](metrics/harness-delta-swe2.json) (every model x harness x metric, per-metric winner, win tallies) and [`metrics/pareto-frontier-pi-swe2.json`](metrics/pareto-frontier-pi-swe2.json) (the score-vs-cost frontier, split by hosting). It is preserved across regens. **When you regenerate the charts, re-read those JSONs and update this text to match.**

<!-- MANUAL:harness-reading BEGIN -- author-maintained; preserved across regens. Update when the chart changes. -->
Read the chart across metrics, not one panel at a time. Claude Code winning the **cost** panel for a model rarely settles the choice: on the models where it is cheaper, either the absolute gap is a few cents, or the model's accuracy is too low to pick regardless of price. What decides a model is **quality first, then cost among the models that clear your quality bar.**

The one metric where the harness choice is lopsided is **wall-clock**: pi's single-agent loop finishes faster on nearly every model (no sub-agent fan-out), so unless a model scores clearly higher under Claude Code and the task is worth the extra time and tokens, pi is the default at the terminal.
<!-- MANUAL:harness-reading END -->

## Results by harness

For each harness: a results table (quality, tokens, run cost + the two normalized cost lenses, wall-clock; sorted by score) followed by a cost-vs-accuracy bubble chart -- x = cost/task, y = mean score, bubble area = tokens processed, color = hosting basis.

### Claude Code

| Model | Hosting | Mean score | Completed | Tokens processed | Run cost | Cost/task | Cost/point | Wall-clock |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| claude-opus-4-8 | Bedrock | 79.12 | 5/5 | 150.0M | $135.69 | $27.14 | $1.71 | 178m |
| claude-sonnet-5 | Bedrock | 76.96 | 5/5 | 370.3M | $181.30 | $36.26 | $2.36 | 277m |
| claude-opus-5 | Bedrock | 76.00 | 5/5 | 84.9M | $180.73 | $36.15 | $2.38 | 241m |
| kimi-k2.7-code | self-hosted | 73.69 | 4/5 | 9.0M | $4.88 | $1.22 | $0.07 | 51m |
| glm-5.2 | self-hosted | 72.75 | 5/5 | 11.6M | $8.32 | $1.66 | $0.11 | 73m |
| deepseek-v3.2 | self-hosted | 52.20 | 5/5 | 40.9M | $15.63 | $3.13 | $0.30 | 80m |
| minimax-m2.5 | self-hosted | 51.35 | 5/5 | 6.3M | $0.69 | $0.14 | $0.01 | 10m |
| qwen3.6-35b | self-hosted | 50.32 | 5/5 | 23.5M | $2.22 | $0.44 | $0.04 | 88m |
| nemotron-ultra-550b | self-hosted | 50.20 | 4/5 | 32.8M | $9.32 | $2.33 | $0.19 | 70m |
| gemma-4-31b | self-hosted | 48.40 | 5/5 | 24.8M | $7.81 | $1.56 | $0.16 | 213m |
| claude-haiku-4-5 | Bedrock | 45.64 | 5/5 | 20.5M | $6.15 | $1.23 | $0.13 | 22m |
| qwen3-coder-480b | self-hosted | 44.95 | 4/5 | 66.2M | $23.20 | $5.80 | $0.52 | 68m |
| devstral-2-123b | self-hosted | 43.12 | 5/5 | 28.1M | $5.66 | $1.13 | $0.13 | 51m |
| qwen3-coder-30b | self-hosted | 30.20 | 4/5 | 50.7M | $3.19 | $0.80 | $0.11 | 84m |
| qwen3-coder-next | self-hosted | -- (0 scored) | 0/1 | 0 | -- | -- | -- | 3m |

Cost vs. accuracy (Claude Code) -- bubble area = tokens processed, color = hosting (Bedrock vs self-hosted):

![Claude Code cost vs accuracy](images/cost-accuracy-bubble-cc-swe2.png)

### pi

| Model | Hosting | Mean score | Completed | Tokens processed | Run cost | Cost/task | Cost/point | Wall-clock |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| claude-opus-5 | Bedrock | 77.00 | 5/5 | 58.6M | $46.56 | $9.31 | $0.60 | 98m |
| qwen3.6-35b | self-hosted | 47.15 | 4/5 | 28.0M | $2.64 | $0.66 | $0.06 | 29m |
| gemma-4-31b | self-hosted | 43.52 | 5/5 | 19.6M | $6.17 | $1.23 | $0.14 | 61m |
| qwen3-coder-30b | self-hosted | -- (0 scored) | 0/5 | 13.2M | $0.83 | -- | -- | 17m |

Cost vs. accuracy (pi) -- bubble area = tokens processed, color = hosting (Bedrock vs self-hosted):

![pi cost vs accuracy](images/cost-accuracy-bubble-pi-swe2.png)

## Guidance: which model for which task, and what it costs

A practical way to read the tables: pick the cheapest model whose quality clears the bar your task needs. Costs below are **per task** (one real `/swe2` problem; a run is 5 tasks). Numbers are from the **pi** column -- the single-agent shape a developer drives at the terminal. Remember the two cost bases are not comparable as raw dollars (Bedrock is a metered bill; self-hosted is hardware-derived) -- see the methodology doc.

- **Top-quality tier (hard / high-stakes changes): `claude-opus-5`** -- highest score (77/100) at $9.31/task. Reach for it on security-sensitive, cross-cutting, or get-it-right-the-first-time work where a wrong design is expensive. You pay the most, but accuracy is the most.
- **Open-weight workhorse (bulk of day-to-day coding): `qwen3.6-35b`** -- best self-hosted quality (47/100) at $0.66/task. Strong on real refactors and features; the model to standardize on if you self-host and route most tickets to one engine.
- **Budget tier (routine / high-volume edits): `gemma-4-31b`** -- cheapest full 5/5 run at $1.23/task (score 44/100). Good for boilerplate, small fixes, and throwaway scaffolding where you will review the output anyway.
- **Reliability flag:** `qwen3.6-35b` (4/5), `qwen3-coder-30b` (0/5) did **not** finish every task under pi -- cheap per task, but a non-completion is a failure, not a discount. Do not route unattended work to a model that does not reliably finish.

## Does the harness change the answer? (pi vs Claude Code)

For the models run under both harnesses, tallying each metric with the chart's 2%-tie rule (a model's hosting basis is identical under both, so even cost is a fair within-model comparison):

- **Quality (mean score):** pi wins 0/3, Claude Code wins 2/3, 1 tie.
- **Cost per task:** pi wins 2/3, Claude Code wins 1/3.
- **Total tokens processed:** pi wins 3/4, Claude Code wins 1/4.
- **Wall-clock latency:** pi wins 4/4, Claude Code wins 0/4.

- **Practical read:** pi's single-agent loop is consistently **faster in wall-clock** (no sub-agent fan-out to coordinate) and often cheaper, while Claude Code's multi-agent orchestration can lift quality on some models at the price of more tokens, dollars, and time. For a developer at the terminal, pi is the better default on latency and cost; switch to Claude Code when a specific model scores meaningfully higher there and the task justifies the extra spend. Pick the harness per model, not globally -- the same model can sit very differently under the two (compare its row across the tables and its bubble in each chart).

## How to reproduce

```bash
cd benchmarks
uv run python scripts/gen_swe_comparison.py --skill swe2
# charts:
uv run python scripts/plot_cost_accuracy_bubble.py --harness pi --skill swe2
uv run python scripts/plot_cost_accuracy_bubble.py --harness claude-code --skill swe2
```
