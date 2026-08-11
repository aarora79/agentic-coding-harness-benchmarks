# Agentic coding: model comparison on /swe3 (quality, tokens, cost)

How every benchmarked model compares as an **agentic coding** engine on real `/swe3` tasks against `mcp-gateway-registry`, under **both harnesses** (Claude Code and pi). Unlike the serving-economics view in [agentic-coding-throughput-comparison.md](agentic-coding-throughput-comparison.md) (synthetic throughput sweep), this doc is built from the actual benchmark runs and combines the three axes a buyer trades off -- **quality, tokens, and cost** -- plus wall-clock latency.

Generated from the committed `run-summary.json` files; regenerate with `uv run scripts/gen_swe_comparison.py --skill swe3`. Numbers match the per-harness docs ([Claude Code](harness-claude-code-swe3.md), [pi](harness-pi-swe3.md)) and the charts below exactly.

## Cost basis (read this first)

Two non-comparable cost bases share the cost columns; each row states which:

- **metered (Bedrock)** -- a hosted API's real per-token bill, summed over the run. Benefits from Bedrock prompt caching.
- **hardware-derived (self-hosted)** -- a rented GPU has no per-token bill, so cost is the model's blended $/token (measured by the throughput sweep at its true instance rate -- g6e.12xlarge for L40S, p5en.48xlarge for H200) times the tokens the run processed. See [cost-per-task-methodology.md](cost-per-task-methodology.md).

`Cost/task` = run cost / scored tasks. `Cost/point` = run cost / mean score -- a value-efficiency figure (lower is more quality per dollar).

## Does the harness matter?

For every model run under both harnesses, this compares Claude Code vs pi on each metric. Each row is one model; the connector points to the better harness (higher score / lower cost, tokens, latency), and each panel title tallies how often pi wins. Comparing one model's two harnesses is fair even for cost -- its hosting basis is identical under both.

![Harness comparison, swe3](images/harness-delta-swe3.png)

### Reading the chart (author-maintained)

> The win-tallies above are mechanical. The prose below is **hand-written reasoning** about what the chart means for a model choice -- the kind of cross-metric judgement code cannot produce. It is written from the machine-readable data behind the charts: [`metrics/harness-delta-swe3.json`](metrics/harness-delta-swe3.json) (every model x harness x metric, per-metric winner, win tallies) and [`metrics/pareto-frontier-pi-swe3.json`](metrics/pareto-frontier-pi-swe3.json) (the score-vs-cost frontier, split by hosting). It is preserved across regens. **When you regenerate the charts, re-read those JSONs and update this text to match.**

<!-- MANUAL:harness-reading BEGIN -- author-maintained; preserved across regens. Update when the chart changes. -->
**How the model tiers are chosen (the criterion).** A model is only worth naming if it sits on the **Pareto frontier** of score vs cost/task -- i.e. no other model scores at least as high for the same or less money. Everything off the frontier is dominated (something is both cheaper and better) and is not worth picking. Because a metered Bedrock bill and a hardware-derived self-hosted cost are **not comparable as raw dollars** (see [cost-per-task-methodology.md](cost-per-task-methodology.md)), we take the frontier **within each hosting basis** and name tiers accordingly. All numbers below are the **pi** column (the single-agent shape a developer drives at the terminal); the frontiers are in the JSON linked above.

For the **harness**, the rule is simpler: pick it per model, but pi is the default -- across the 12 models run under both, pi wins wall-clock 10/12 and ties or wins cost and quality, because its single-agent loop skips the sub-agent fan-out that inflates Claude Code's tokens, dollars, and time.

Tiers, by what the task needs:

- **Frontier / business-critical -- `claude-opus-5` (Bedrock), on pi.** Top of the Bedrock frontier at **75.7/100, $8.28/task**. Reach for it when a wrong design is expensive (security, cross-cutting, get-it-right-first-time). pi is not close here: it beats Claude Code on *every* axis -- quality (75.7 vs 70.8), cost ($8.28 vs $24.05), wall-clock (94m vs 199m), tokens (50M vs 175M). Fan-out buys opus-5 nothing and costs 3x.

- **Frontier open-weight -- `glm-5.2` (self-hosted), on pi.** Top of the self-hosted frontier at **70.8/100, $6.42/task**; the model to standardize on if you self-host your quality tier. pi wins quality (70.8 vs 65.6) *and* cost ($6.42 vs $6.73), for ~9 extra minutes (105m vs 96m) -- a trivial trade for +5 points.

- **Value open-weight -- `deepseek-v3.2` (self-hosted), on pi.** A mid-frontier self-hosted point at **54.4/100, $1.83/task** -- roughly three-quarters of glm-5.2's quality for under a third of its cost, and it completes 5/5. This is the workhorse for the bulk of day-to-day self-hosted coding where you do not need the top of the frontier. (Below it on the self-hosted frontier sit `minimax-m2.5` at 45.1/$0.50 and `qwen3.6-35b` at 52.3/$0.87 -- both cheaper and genuinely non-dominated, but **note reliability**: qwen3.6-35b completed only **4/5** tasks under pi, so it is a frontier point with an asterisk, not a set-and-forget workhorse. Do not route unattended work to a model that does not reliably finish.)

- **Most cost-effective, just-get-it-done -- `claude-haiku-4-5` (Bedrock), on pi.** Bottom of the Bedrock frontier at **47.1/100, $0.64/task**, for boilerplate, small fixes, and scaffolding you will review anyway. The easy case: pi is both higher quality (47.1 vs 41.1) *and* cheaper ($0.64 vs $0.80) than Claude Code, at equal 5/5 reliability.

**If you insist on ONE combined frontier (both cost bases together).** Some readers will want a single ranking regardless of hosting. Doing that is *directional only* -- it puts a metered Bedrock bill (prompt-cache-discounted) next to a hardware-derived self-hosted cost (committed-capacity GPU rate), which are not comparable as raw dollars -- but it is revealing. On the combined pi swe3 frontier ([`metrics/pareto-frontier-pi-swe3.json`](metrics/pareto-frontier-pi-swe3.json), `combined_frontier_cross_hosting_directional`), the self-hosted open-weight models now hold most of it: **qwen3-coder-30b ($0.31, but only 2/5) -> minimax-m2.5 ($0.50) -> claude-haiku-4-5 ($0.64) -> devstral-2-123b ($0.81) -> qwen3.6-35b ($0.87) -> deepseek-v3.2 ($1.83) -> claude-sonnet-5 ($3.81) -> glm-5.2 ($6.42) -> claude-opus-5 ($8.28)**. Only three Bedrock points survive (haiku, sonnet-5, opus-5); the rest of the Anthropic middle is dominated by cheaper open-weight models at equal-or-higher score.

**At committed-capacity GPU pricing the open-weight case is strong across the whole curve, not just the cheap end.** `glm-5.2` (70.8/$6.42) is now non-dominated -- it sits just under `claude-opus-5` (75.7/$8.28) and offers the best open-weight quality for a third of glm's old cost; `deepseek-v3.2` (54.4/$1.83) is the reliable 5/5 workhorse; `qwen3.6-35b` (52.3/$0.87) holds the gap below sonnet-5 (with a **4/5** reliability asterisk). The frontier shifted markedly after repricing self-hosted GPUs to committed-capacity rates (p5en base x 0.35 discount multiplier; g6e at its 3-year RI rate) -- see [cost-per-task-methodology.md](cost-per-task-methodology.md). This is exactly why the default view keeps the frontiers split by hosting: the cross-hosting ranking swings hard with the GPU rate basis.

**The through-line:** choose the model by where your task lands on the quality/cost frontier for your hosting basis; run it on pi, which wins or ties on the axes that matter and is fastest on wall-clock almost every time. A model that is merely cheap but *dominated* (off the frontier) -- or that does not reliably finish -- is not a bargain.
<!-- MANUAL:harness-reading END -->

## Results by harness

For each harness: a results table (quality, tokens, run cost + the two normalized cost lenses, wall-clock; sorted by score) followed by a cost-vs-accuracy bubble chart -- x = cost/task, y = mean score, bubble area = tokens processed, color = hosting basis.

### Claude Code

| Model | Hosting | Mean score | Completed | Tokens processed | Run cost | Cost/task | Cost/point | Wall-clock |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| claude-opus-5 | Bedrock | 70.76 | 5/5 | 175.1M | $120.25 | $24.05 | $1.70 | 199m |
| claude-opus-4-8 | Bedrock | 69.24 | 5/5 | 57.0M | $49.51 | $9.90 | $0.72 | 113m |
| claude-sonnet-5 | Bedrock | 68.04 | 5/5 | 341.6M | $123.20 | $24.64 | $1.81 | 191m |
| glm-5.2 | self-hosted | 65.60 | 5/5 | 86.8M | $33.66 | $6.73 | $0.51 | 96m |
| kimi-k2.7-code | self-hosted | 55.44 | 5/5 | 57.9M | $16.84 | $3.37 | $0.30 | 79m |
| deepseek-v3.2 | self-hosted | 53.72 | 5/5 | 68.9M | $14.17 | $2.83 | $0.26 | 103m |
| nemotron-ultra-550b | self-hosted | 53.68 | 5/5 | 95.6M | $14.63 | $2.93 | $0.27 | 82m |
| devstral-2-123b | self-hosted | 49.52 | 5/5 | 28.2M | $3.06 | $0.61 | $0.06 | 55m |
| minimax-m2.5 | self-hosted | 48.36 | 5/5 | 39.0M | $2.33 | $0.47 | $0.05 | 22m |
| qwen3.6-35b | self-hosted | 48.16 | 5/5 | 37.8M | $3.56 | $0.71 | $0.07 | 47m |
| qwen3-coder-480b | self-hosted | 46.32 | 5/5 | 57.5M | $10.85 | $2.17 | $0.23 | 54m |
| claude-haiku-4-5 | Bedrock | 41.08 | 5/5 | 25.4M | $3.99 | $0.80 | $0.10 | 23m |

Cost vs. accuracy (Claude Code) -- bubble area = tokens processed, color = hosting (Bedrock vs self-hosted):

![Claude Code cost vs accuracy](images/cost-accuracy-bubble-cc-swe3.png)

### pi

| Model | Hosting | Mean score | Completed | Tokens processed | Run cost | Cost/task | Cost/point | Wall-clock |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| claude-opus-5 | Bedrock | 75.72 | 5/5 | 50.0M | $41.42 | $8.28 | $0.55 | 94m |
| glm-5.2 | self-hosted | 70.76 | 5/5 | 82.7M | $32.08 | $6.42 | $0.45 | 105m |
| claude-sonnet-5 | Bedrock | 66.52 | 5/5 | 67.0M | $19.07 | $3.81 | $0.29 | 74m |
| claude-opus-4-8 | Bedrock | 60.68 | 5/5 | 22.5M | $22.99 | $4.60 | $0.38 | 63m |
| kimi-k2.7-code | self-hosted | 60.68 | 5/5 | 102.1M | $29.71 | $5.94 | $0.49 | 57m |
| nemotron-ultra-550b | self-hosted | 55.20 | 5/5 | 137.3M | $21.02 | $4.20 | $0.38 | 34m |
| deepseek-v3.2 | self-hosted | 54.44 | 5/5 | 44.5M | $9.16 | $1.83 | $0.17 | 33m |
| qwen3.6-35b | self-hosted | 52.30 | 4/5 | 37.9M | $3.57 | $0.89 | $0.07 | 29m |
| devstral-2-123b | self-hosted | 47.64 | 5/5 | 37.5M | $4.06 | $0.81 | $0.09 | 30m |
| claude-haiku-4-5 | Bedrock | 47.12 | 5/5 | 18.1M | $3.21 | $0.64 | $0.07 | 29m |
| minimax-m2.5 | self-hosted | 45.08 | 5/5 | 42.3M | $2.52 | $0.50 | $0.06 | 13m |
| qwen3-coder-480b | self-hosted | 43.96 | 5/5 | 88.7M | $16.73 | $3.35 | $0.38 | 28m |
| gemma-4-31b | self-hosted | 42.96 | 5/5 | 32.9M | $10.34 | $2.07 | $0.24 | 58m |
| qwen3-coder-30b | self-hosted | 26.90 | 2/5 | 19.6M | $1.23 | $0.61 | $0.05 | 18m |

Cost vs. accuracy (pi) -- bubble area = tokens processed, color = hosting (Bedrock vs self-hosted):

![pi cost vs accuracy](images/cost-accuracy-bubble-pi-swe3.png)

## Guidance: which model for which task, and what it costs

A practical way to read the tables: pick the cheapest model whose quality clears the bar your task needs. Costs below are **per task** (one real `/swe3` problem; a run is 5 tasks). Numbers are from the **pi** column -- the single-agent shape a developer drives at the terminal. Remember the two cost bases are not comparable as raw dollars (Bedrock is a metered bill; self-hosted is hardware-derived) -- see the methodology doc.

- **Top-quality tier (hard / high-stakes changes): `claude-opus-5`** -- highest score (76/100) at $8.28/task. Reach for it on security-sensitive, cross-cutting, or get-it-right-the-first-time work where a wrong design is expensive. You pay the most, but accuracy is the most.
- **Open-weight workhorse (bulk of day-to-day coding): `glm-5.2`** -- best self-hosted quality (71/100) at $6.42/task. Strong on real refactors and features; the model to standardize on if you self-host and route most tickets to one engine.
- **Best value (most quality per dollar): `claude-sonnet-5`** -- clears ~61/100 (80% of the top score) at just $3.81/task. The sweet spot for well-scoped tasks: most of the quality, a fraction of the cost.
- **Budget tier (routine / high-volume edits): `minimax-m2.5`** -- cheapest full 5/5 run at $0.50/task (score 45/100). Good for boilerplate, small fixes, and throwaway scaffolding where you will review the output anyway.
- **Reliability flag:** `qwen3.6-35b` (4/5), `qwen3-coder-30b` (2/5) did **not** finish every task under pi -- cheap per task, but a non-completion is a failure, not a discount. Do not route unattended work to a model that does not reliably finish.

## Does the harness change the answer? (pi vs Claude Code)

For the models run under both harnesses, tallying each metric with the chart's 2%-tie rule (a model's hosting basis is identical under both, so even cost is a fair within-model comparison):

- **Quality (mean score):** pi wins 6/12, Claude Code wins 5/12, 1 tie.
- **Cost per task:** pi wins 6/12, Claude Code wins 6/12.
- **Total tokens processed:** pi wins 6/12, Claude Code wins 5/12, 1 tie.
- **Wall-clock latency:** pi wins 10/12, Claude Code wins 2/12.

- **Practical read:** pi's single-agent loop is consistently **faster in wall-clock** (no sub-agent fan-out to coordinate) and often cheaper, while Claude Code's multi-agent orchestration can lift quality on some models at the price of more tokens, dollars, and time. For a developer at the terminal, pi is the better default on latency and cost; switch to Claude Code when a specific model scores meaningfully higher there and the task justifies the extra spend. Pick the harness per model, not globally -- the same model can sit very differently under the two (compare its row across the tables and its bubble in each chart).

## How to reproduce

```bash
cd benchmarks
uv run python scripts/gen_swe_comparison.py --skill swe3
# charts:
uv run python scripts/plot_cost_accuracy_bubble.py --harness pi --skill swe3
uv run python scripts/plot_cost_accuracy_bubble.py --harness claude-code --skill swe3
```
