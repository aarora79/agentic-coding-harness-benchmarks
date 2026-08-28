# Which model for which task? Reading the v2 results as a buying decision

The [v2 dataset](../benchmarks/dataset/mcp-gateway-registry-v2.yaml) was built to answer a question a single leaderboard number cannot: **does the right model change with the difficulty of the work?**

Three models, 15 tasks balanced 5 low / 5 medium / 5 high, pi harness, `/swe3`. Raw numbers in [results-swe3-v2.md](results-swe3-v2.md). This page is the inference drawn from them.

Everything below rests on **one run per model per task**. Two of the fifteen tasks are known anomalies, and both are flagged where they affect a conclusion.

## First, the intuition that turns out to be wrong

The natural expectation is that **easy tasks are a leveller** -- on trivial work any competent model gets it right, the models converge, so you use the cheap one and save your budget for hard problems.

That is not what the data shows.

| Tier | haiku-4-5 | sonnet-5 | opus-5 | **Spread (max − min)** |
|---|---:|---:|---:|---:|
| low | 63.20 | 74.92 | 82.32 | **19.12** |
| medium | 59.28 | 76.16 | 78.20 | **18.92** |
| high | 52.48 | 66.20 | 73.52 | **21.04** |

**The spread is flat.** Opus beats haiku by 19.1 points on low-complexity tasks, 18.9 on medium and 21.0 on high. Models are just as far apart on the easy work as on the hard work — haiku never catches up, not even on a checkbox default.

Why the intuition fails: a "low complexity" task is small in *scope*, not forgiving of error. `default-create-in-idp-checkbox-unchecked` is a one-line default flip, and haiku still scores 72.0 against opus's 83.6 — because the score is not "did it change the line", it is the quality of the issue spec, design, review, test plan and patch. Small tasks have just as many ways to be done sloppily.

So **you cannot justify a cheap model on the grounds that the task is easy.** If you use haiku on trivial work, you get haiku-quality output on trivial work.

## What actually changes with difficulty: the price

![What a model upgrade buys, per complexity tier](images/tier-frontier-pi-swe3-mcp-gateway-registry-v2.png)

Each line walks one tier from the cheapest model to the costliest. The lines barely differ in *height* — they differ enormously in *width*.

| Tier | haiku $/task | sonnet $/task | opus $/task | opus ÷ haiku |
|---|---:|---:|---:|---:|
| low | $0.45 | $1.11 | $3.41 | **7.6×** |
| medium | $0.67 | $2.21 | $5.32 | **8.0×** |
| high | $0.68 | $5.32 | $11.34 | **16.7×** |

Difficulty barely moves haiku's cost ($0.45 → $0.68) but nearly triples sonnet's and opus's. Hard tasks are where a frontier model spends its money: more turns, more exploration, more context re-read per turn.

Which turns the decision into a marginal one — **what does the next tier of model cost per point of quality it adds?**

| Tier | haiku → sonnet | sonnet → opus |
|---|---:|---:|
| low | $0.06 / point | $0.31 / point |
| medium | $0.09 / point | **$1.52 / point** |
| high | $0.34 / point | $0.82 / point |

**Upgrading haiku → sonnet is cheap at every tier** — 6¢ to 34¢ per point. It is the best-value move in the entire matrix and there is no tier where it is a bad idea.

**Upgrading sonnet → opus costs 3–17× more per point**, and is worst on medium at $1.52/point. But that medium figure is distorted by the one anomaly: opus scored 66.2 on `configurable-mcp-proxy-upstream-timeout` where sonnet scored 78.6, and every artifact was depressed rather than one — a bad run, not a hard task. Excluding it, opus's medium mean is **81.20** rather than 78.20, and the upgrade cost falls to roughly $0.55/point. **Do not build a "never use opus on medium" rule on one task.**

## The rule that does hold: pick by quality bar, not by difficulty

Because models do not converge, "how hard is this task" is the wrong input. The right one is **how good does the output need to be** — and difficulty then decides what that costs.

Cheapest model clearing a given mean score, per tier:

| Quality bar | low | medium | high |
|---|---|---|---|
| ≥ 55 | haiku ($0.45) | haiku ($0.67) | sonnet ($5.32) |
| ≥ 60 | haiku ($0.45) | sonnet ($2.21) | sonnet ($5.32) |
| ≥ 65 | sonnet ($1.11) | sonnet ($2.21) | sonnet ($5.32) |
| **≥ 70** | **sonnet ($1.11)** | **sonnet ($2.21)** | **opus ($11.34)** |
| ≥ 75 | opus ($3.41) | sonnet ($2.21) | *none* |
| ≥ 80 | opus ($3.41) | *none* | *none* |

Read down the **≥ 70** row and the shape people expect does appear — sonnet for low and medium, opus for high — but it arrives for a different reason than the intuition supposed. It is not that low-complexity tasks let you drop to a cheaper model; it is that **sonnet already clears 70 there, and on hard work only opus does.**

Three things this table makes concrete:

- **Haiku never clears 70 at any tier.** Its ceiling is 63.2, on the easiest work. If your bar is "mergeable with light review", haiku is not a cheaper way to get there — it is a different outcome.
- **Sonnet is the default.** It clears 70 on low and medium at $1.11 and $2.21, and it is the only model that is never obviously the wrong call. Reach past it deliberately, not by habit.
- **Opus earns its price on high complexity and essentially nowhere else.** It is the only model above 70 there. On low-complexity work it costs 3.1× sonnet to add 7.4 points that a human reviewer may not even notice.

## Where the extra quality actually shows up

Model choice is a decision about **implementation quality specifically**. Mean per artifact across all 15 tasks:

| Model | Issue spec | LLD | Review | Testing | Implementation |
|---|---:|---:|---:|---:|---:|
| `claude-haiku-4-5` | 74.9 | 60.7 | 54.8 | 54.6 | **46.7** |
| `claude-sonnet-5` | 80.9 | 75.9 | 71.7 | 68.3 | **65.2** |
| `claude-opus-5` | 83.0 | 79.6 | 80.3 | 76.7 | **70.5** |

Issue-spec scores are compressed at the top — 74.9 to 83.0, an 8-point range across a 7× price difference. **Every model can write a decent spec.** Implementation spans 46.7 to 70.5, nearly three times the range.

That gives a sharper version of the rule: **if a step's output is a document a human will read and correct, the cheap model is competitive. If its output is code that must actually work, it is not.** Haiku producing an 80-scoring issue spec and an 11-scoring implementation on the same task (`registration-admission-control-gate`) is the pattern in its purest form.

A practical consequence: for a design-only workflow, haiku at $0.60/task is genuinely viable. For anything that ends in a patch, the gap you are paying to close is the implementation gap.

## Putting it together

1. **Set a quality bar first.** Difficulty tells you what that bar costs; it does not tell you which model to use.
2. **Default to sonnet.** Best value at every tier ($0.06–$0.34 per point over haiku), and clears 70 on everything but high-complexity work.
3. **Escalate to opus for high-complexity tasks** — the only model above 70 there, and worth $0.82/point.
4. **Do not drop to haiku because a task looks easy.** It is 19 points behind on easy tasks too. Drop to haiku when the *deliverable* tolerates it — design documents a human will review — not when the task is small.
5. **Budget for difficulty, not volume.** Opus on high-complexity work costs 16.7× haiku; two hard tasks cost more than fifteen easy ones.

## Caveats

- **n=1 per model per task.** A single task swings a 5-task tier mean by 2–4 points. `configurable-mcp-proxy-upstream-timeout` (opus's one loss) is the live example, and it is the reason the medium-tier upgrade cost is not trustworthy.
- **`build-docker-images-from-uv-lock` is mis-tiered.** All three models score it worst-in-tier at `low`. It inflates the apparent difficulty of the low tier for every model equally, so comparisons between models hold, but the low-tier absolute means are pessimistic by roughly 2–4 points.
- **One harness, one repo.** pi on `mcp-gateway-registry`. Harness effects are real and measured elsewhere in this repo — see [best-harness-selection.md](best-harness-selection.md).
- **Only three models, all Anthropic.** The self-hosted open-weight models on the v1 charts have not been run on v2, so nothing here speaks to the cross-hosting question.
- **Costs are metered Bedrock prices** and not comparable with the hardware-derived figures used for self-hosted models. See [cost-per-task-methodology.md](cost-per-task-methodology.md).
