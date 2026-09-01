# Agentic coding: model comparison on /swe3 (quality, tokens, cost)

> **Not the headline result.** The reported run is the **omp** harness with `/swe3` on the **v2** dataset -- 16 models, 21 tasks -- in [harness-omp-swe3.md](harness-omp-swe3.md). This page covers Claude Code against pi on the v1 dataset. Different task sets and harnesses, so the scores here do not compare with it.

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

- **Frontier open-weight -- `glm-5.2` (self-hosted), on pi.** Top of the self-hosted frontier at **70.8/100, $5.98/task**; the model to standardize on if you self-host your quality tier. pi wins quality (70.8 vs 65.6) *and* cost ($5.98 vs $12.50), for ~9 extra minutes (105m vs 96m) -- a trivial trade for +5 points.

- **Value open-weight -- `deepseek-v3.2` (self-hosted), on pi.** A mid-frontier self-hosted point at **54.4/100, $1.15/task** -- roughly three-quarters of glm-5.2's quality for under a third of its cost, and it completes 5/5. This is the workhorse for the bulk of day-to-day self-hosted coding where you do not need the top of the frontier. (Below it on the self-hosted frontier sits `qwen3.6-35b` at 52.3/$0.16 -- but **note reliability**: it completed only **4/5** tasks under pi, so it is a frontier point with an asterisk, not a set-and-forget workhorse. `qwen3-coder-30b` is cheaper per hour but no longer a frontier point at all: 26.9/$0.18 and only 2/5. Do not route unattended work to a model that does not reliably finish.)

- **Most cost-effective, just-get-it-done -- `claude-haiku-4-5` (Bedrock), on pi.** Bottom of the Bedrock frontier at **47.1/100, $0.64/task**, for boilerplate, small fixes, and scaffolding you will review anyway. The easy case: pi is both higher quality (47.1 vs 41.1) *and* cheaper ($0.64 vs $0.80) than Claude Code, at equal 5/5 reliability.

**If you insist on ONE combined frontier (both cost bases together).** Some readers will want a single ranking regardless of hosting. Doing that is *directional only* -- it puts a metered Bedrock bill (prompt-cache-discounted) next to a hardware-derived self-hosted cost (committed-capacity GPU rate), which are not comparable as raw dollars -- but it is revealing. On the combined pi swe3 frontier ([`metrics/pareto-frontier-pi-swe3.json`](metrics/pareto-frontier-pi-swe3.json), `combined_frontier_cross_hosting_directional`): **qwen3.6-35b ($0.16) -> deepseek-v3.2 ($1.15) -> qwen3.8-27b ($2.12) -> claude-sonnet-5 ($3.81) -> glm-5.2 ($4.03) -> claude-opus-5 ($8.28)**. Open-weight models hold everything below the top: five of the six frontier points are self-hosted, and only `claude-opus-5` sits above `glm-5.2`. `glm-5.2` (70.8/$4.03) is **not dominated** by `claude-opus-5`: opus-5 scores higher (75.7) but costs more than twice as much, so glm-5.2 is a legitimate cheaper, lower-scoring frontier point. Two models dropped off: `claude-haiku-4-5`, because qwen3.6-35b clears its quality for a quarter of the price, and `qwen3-coder-30b` ($0.18/26.9, and only 2/5), because qwen3.6-35b is now both cheaper *and* far better.

**`deepseek-v3.2` (54.4/$1.15) is the standout self-hosted workhorse** -- non-dominated, reliable 5/5, and a third of sonnet-5's cost while scoring in the mid-50s; `qwen3.6-35b` (52.3/$0.16) holds the gap below it (with a **4/5** reliability asterisk). **This cross-hosting picture is sensitive to the GPU rate basis** -- these self-hosted costs use the **3-year commitment rate for both instance families** (p5en.48xlarge $27.72/hr, g6e.12xlarge $4.533/hr) from [`self-hosted/vllm/pricing.json`](../self-hosted/vllm/pricing.json). Pricing at on-demand instead (p5en $63.296/hr) multiplies every self-hosted dollar by ~2.3 and pushes the p5en models (glm-5.2, kimi, nemotron) back off the frontier; see [cost-per-task-methodology.md](cost-per-task-methodology.md). This is exactly why the default view keeps the frontiers split by hosting.

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
| glm-5.2 | self-hosted | 65.60 | 5/5 | 86.8M | $42.11 | $8.42 | $0.64 | 96m |
| kimi-k2.7-code | self-hosted | 55.44 | 5/5 | 57.9M | $21.08 | $4.22 | $0.38 | 79m |
| deepseek-v3.2 | self-hosted | 53.72 | 5/5 | 68.9M | $17.73 | $3.55 | $0.33 | 103m |
| nemotron-ultra-550b | self-hosted | 53.68 | 5/5 | 95.6M | $18.31 | $3.66 | $0.34 | 82m |
| devstral-2-123b | self-hosted | 49.52 | 5/5 | 28.2M | $3.82 | $0.76 | $0.08 | 55m |
| minimax-m2.5 | self-hosted | 48.36 | 5/5 | 39.0M | $2.91 | $0.58 | $0.06 | 22m |
| qwen3.6-35b | self-hosted | 48.16 | 5/5 | 37.8M | $1.28 | $0.26 | $0.03 | 47m |
| qwen3-coder-480b | self-hosted | 46.32 | 5/5 | 57.5M | $13.57 | $2.71 | $0.29 | 54m |
| claude-haiku-4-5 | Bedrock | 41.08 | 5/5 | 25.4M | $3.99 | $0.80 | $0.10 | 23m |

Cost vs. accuracy (Claude Code) -- bubble area = tokens processed, color = hosting (Bedrock vs self-hosted):

![Claude Code cost vs accuracy](images/cost-accuracy-bubble-cc-swe3.png)

### pi

| Model | Hosting | Mean score | Completed | Tokens processed | Run cost | Cost/task | Cost/point | Wall-clock |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| claude-opus-5 | Bedrock | 75.72 | 5/5 | 50.0M | $41.42 | $8.28 | $0.55 | 94m |
| glm-5.2 | self-hosted | 70.76 | 5/5 | 41.5M | $20.15 | $4.03 | $0.28 | 105m |
| claude-sonnet-5 | Bedrock | 66.52 | 5/5 | 67.0M | $19.07 | $3.81 | $0.29 | 74m |
| qwen3.8-27b | self-hosted | 66.40 | 5/5 | 96.7M | $13.55 | $2.71 | $0.20 | 710m |
| claude-opus-4-8 | Bedrock | 60.68 | 5/5 | 22.5M | $22.99 | $4.60 | $0.38 | 63m |
| kimi-k2.7-code | self-hosted | 60.68 | 5/5 | 51.0M | $18.58 | $3.72 | $0.31 | 57m |
| grok-4.6 | Bedrock | 56.28 | 5/5 | 13.1M | $66.71 | $13.34 | $1.19 | 70m |
| nemotron-ultra-550b | self-hosted | 55.20 | 5/5 | 68.7M | $13.16 | $2.63 | $0.24 | 34m |
| deepseek-v3.2 | self-hosted | 54.44 | 5/5 | 22.3M | $5.75 | $1.15 | $0.11 | 33m |
| qwen3.6-35b | self-hosted | 52.30 | 4/5 | 19.1M | $0.64 | $0.16 | $0.01 | 29m |
| devstral-2-123b | self-hosted | 47.64 | 5/5 | 18.8M | $2.55 | $0.51 | $0.05 | 30m |
| claude-haiku-4-5 | Bedrock | 47.12 | 5/5 | 18.1M | $3.21 | $0.64 | $0.07 | 29m |
| minimax-m2.5 | self-hosted | 45.08 | 5/5 | 21.2M | $1.58 | $0.32 | $0.04 | 13m |
| qwen3-coder-480b | self-hosted | 43.96 | 5/5 | 44.4M | $10.48 | $2.10 | $0.24 | 28m |
| gemma-4-31b | self-hosted | 42.96 | 5/5 | 16.5M | $3.24 | $0.65 | $0.08 | 58m |
| qwen3-coder-30b | self-hosted | 26.90 | 2/5 | 9.8M | $0.70 | $0.35 | $0.03 | 18m |

Cost vs. accuracy (pi) -- bubble area = tokens processed, color = hosting (Bedrock vs self-hosted):

![pi cost vs accuracy](images/cost-accuracy-bubble-pi-swe3.png)

## Guidance: which model for which task, and what it costs

A practical way to read the tables: pick the cheapest model whose quality clears the bar your task needs. Costs below are **per task** (one real `/swe3` problem; a run is 5 tasks). Numbers are from the **pi** column -- the single-agent shape a developer drives at the terminal. Remember the two cost bases are not comparable as raw dollars (Bedrock is a metered bill; self-hosted is hardware-derived) -- see the methodology doc.

- **Top-quality tier (hard / high-stakes changes): `claude-opus-5`** -- highest score (76/100) at $8.28/task. Reach for it on security-sensitive, cross-cutting, or get-it-right-the-first-time work where a wrong design is expensive. You pay the most, but accuracy is the most.
- **Open-weight workhorse (bulk of day-to-day coding): `glm-5.2`** -- best self-hosted quality (71/100) at $4.03/task. Strong on real refactors and features; the model to standardize on if you self-host and route most tickets to one engine.
- **Best value (most quality per dollar): `qwen3.8-27b`** -- clears ~61/100 (80% of the top score) at just $2.71/task. The sweet spot for well-scoped tasks: most of the quality, a fraction of the cost.
- **Budget tier (routine / high-volume edits): `minimax-m2.5`** -- cheapest full 5/5 run at $0.32/task (score 45/100). Good for boilerplate, small fixes, and throwaway scaffolding where you will review the output anyway.
- **Reliability flag:** `qwen3.6-35b` (4/5), `qwen3-coder-30b` (2/5) did **not** finish every task under pi -- cheap per task, but a non-completion is a failure, not a discount. Do not route unattended work to a model that does not reliably finish.

## Does the harness change the answer? (pi vs Claude Code)

For the models run under both harnesses, tallying each metric with the chart's 2%-tie rule (a model's hosting basis is identical under both, so even cost is a fair within-model comparison):

- **Quality (mean score):** pi wins 6/12, Claude Code wins 5/12, 1 tie.
- **Cost per task:** pi wins 12/12, Claude Code wins 0/12.
- **Total tokens processed:** pi wins 12/12, Claude Code wins 0/12.
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
