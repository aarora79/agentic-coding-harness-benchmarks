# Which model for which task? Reading the v2 results as a buying decision

The [v2 dataset](../benchmarks/dataset/mcp-gateway-registry-v2.yaml) was built to answer a question a single leaderboard number cannot: **does the right model change with the difficulty of the work?**

Three models, 15 tasks across low / medium / high, pi harness, `/swe3`. (The dataset has since gained a **trivial** tier and now stands at 21 tasks; those five have not been run yet.) Raw numbers in [results-swe3-v2.md](results-swe3-v2.md). This page is the inference drawn from them.

Everything below rests on **one run per model per task**, and one task is a known anomaly, flagged where it affects a conclusion.

## First, the intuition that turns out to be mostly wrong

The natural expectation is that **easy tasks are a leveller** -- on trivial work any competent model gets it right, the models converge, so you use the cheap one and save your budget for hard problems.

That is not what the data shows.

| Tier | n | haiku-4-5 | sonnet-5 | opus-5 | **Spread (max − min)** |
|---|---:|---:|---:|---:|---:|
| low | 4 | 68.30 | 78.50 | 83.75 | **15.45** |
| medium | 6 | 56.53 | 73.57 | 77.93 | **21.40** |
| high | 5 | 52.48 | 66.20 | 73.52 | **21.04** |

**The spread narrows a little on easy work, and nothing like enough.** Opus beats haiku by 15.5 points on low-complexity tasks against ~21 on medium and high. So there is a real effect in the direction the intuition predicts — and it is far too small to act on. Haiku on the easiest tier in the set still scores 68.3 against opus's 83.75.

Why the intuition mostly fails: a "low complexity" task is small in *scope*, not forgiving of error. `default-create-in-idp-checkbox-unchecked` is a one-line default flip, and haiku still scores 72.0 against opus's 83.6 — because the score is not "did it change the line", it is the quality of the issue spec, design, review, test plan and patch. Small tasks have just as many ways to be done sloppily.

An earlier version of this page reported the spread as **perfectly flat** (19.1 / 18.9 / 21.0). That was an artifact of `build-docker-images-from-uv-lock` being mis-labelled `low`; it was the widest-spread task in the set, and it has since been re-tiered to `medium`. The corrected numbers still refute the intuition, just less absolutely — which is why the fix was worth making before publishing a rule on top of it.

Whether the gap closes on genuinely *trivial* work — a docs page, a render condition, two env passthroughs — is still open. A trivial tier was added to the dataset to answer exactly that, and has not been run yet.

So **you cannot justify a cheap model on the grounds that the task is easy** -- not on a 15-point deficit. If you use haiku on easy work, you mostly get haiku-quality output on easy work.

## What actually changes with difficulty: the price

![What a model upgrade buys, per complexity tier](images/tier-frontier-pi-swe3-mcp-gateway-registry-v2.png)

Each line walks one tier from the cheapest model to the costliest. The lines are separated in *height* by about 10 points end to end — and in *width* by a factor of three.

| Tier | haiku $/task | sonnet $/task | opus $/task | opus ÷ haiku |
|---|---:|---:|---:|---:|
| low | $0.45 | $1.02 | $3.24 | **7.2×** |
| medium | $0.63 | $2.09 | $5.11 | **8.1×** |
| high | $0.68 | $5.32 | $11.34 | **16.7×** |

Difficulty barely moves haiku's cost ($0.45 → $0.68) but more than triples sonnet's and opus's. Hard tasks are where a frontier model spends its money: more turns, more exploration, more context re-read per turn.

Which turns the decision into a marginal one — **what does the next tier of model cost per point of quality it adds?**

| Tier | haiku → sonnet | sonnet → opus |
|---|---:|---:|
| low | $0.06 / point | $0.42 / point |
| medium | $0.09 / point | $0.69 / point |
| high | $0.34 / point | $0.82 / point |

**Upgrading haiku → sonnet is cheap at every tier** — 6¢ to 34¢ per point. It is the best-value move in the entire matrix and there is no tier where it is a bad idea.

**Upgrading sonnet → opus costs 2–7× more per point**, and gets steadily worse as tasks get harder in absolute terms while staying the only route above 70 on the high tier.

One caveat on the medium column: opus scored 66.2 on `configurable-mcp-proxy-upstream-timeout` where sonnet scored 78.6, with every artifact depressed rather than one — a bad run, not a hard task. Excluding it, opus's medium mean rises and the upgrade looks cheaper still. **Do not build a rule on one task in either direction.**

## The rule that does hold: pick by quality bar, not by difficulty

Because models converge only slightly, "how hard is this task" is the wrong input on its own. The right one is **how good does the output need to be** — and difficulty then decides what that costs.

Cheapest model clearing a given mean score, per tier:

| Quality bar | low | medium | high |
|---|---|---|---|
| ≥ 55 | haiku ($0.45) | haiku ($0.63) | sonnet ($5.32) |
| ≥ 60 | haiku ($0.45) | sonnet ($2.09) | sonnet ($5.32) |
| ≥ 65 | haiku ($0.45) | sonnet ($2.09) | sonnet ($5.32) |
| **≥ 70** | **sonnet ($1.02)** | **sonnet ($2.09)** | **opus ($11.34)** |
| ≥ 75 | sonnet ($1.02) | opus ($5.11) | *none* |
| ≥ 80 | opus ($3.24) | *none* | *none* |

Read down the **≥ 70** row and the shape people expect does appear — sonnet for low and medium, opus for high — but it arrives for a different reason than the intuition supposed. It is not that low-complexity tasks let you drop to a cheaper model; it is that **sonnet already clears 70 there, and on hard work only opus does.**

Three things this table makes concrete:

- **Haiku never clears 70 at any tier.** Its ceiling is 68.3, on the easiest work — close enough to be tempting, and still short. If your bar is "mergeable with light review", haiku is not a cheaper way to get there; it is a different outcome. It *does* clear 65 on low at $0.45, which is where it belongs.
- **Sonnet is the default.** It clears 70 on low and medium at $1.02 and $2.09, and 75 on low. It is the only model that is never obviously the wrong call. Reach past it deliberately, not by habit.
- **Opus earns its price on high complexity and essentially nowhere else.** It is the only model above 70 there. On low-complexity work it costs 3.2× sonnet to add 5.25 points a human reviewer may not notice.

## Where the extra quality actually shows up

Model choice is a decision about **implementation quality specifically**. Mean per artifact across all 15 tasks:

| Model | Issue spec | LLD | Review | Testing | Implementation | Impl. low → high |
|---|---:|---:|---:|---:|---:|---:|
| `claude-haiku-4-5` | 74.9 | 60.7 | 54.8 | 54.6 | **46.7** | 71 → 23 (−48) |
| `claude-sonnet-5` | 80.9 | 75.9 | 71.7 | 68.3 | **65.2** | 82 → 54 (−28) |
| `claude-opus-5` | 83.0 | 79.6 | 80.3 | 76.7 | **70.5** | 84 → 63 (−20) |

Issue-spec scores are compressed at the top — 74.9 to 83.0, an 8-point range across a 7× price difference. **Every model can write a decent spec.** Implementation spans 46.7 to 70.5, nearly three times the range.

That gives a sharper version of the rule: **if a step's output is a document a human will read and correct, the cheap model is competitive. If its output is code that must actually work, it is not.** Haiku producing an 80-scoring issue spec and an 11-scoring implementation on the same task (`registration-admission-control-gate`) is the pattern in its purest form.

A practical consequence: for a design-only workflow, haiku at $0.60/task is genuinely viable. For anything that ends in a patch, the gap you are paying to close is the implementation gap.

## Putting it together

1. **Set a quality bar first.** Difficulty tells you what that bar costs; it does not tell you which model to use.
2. **Default to sonnet.** Best value at every tier ($0.06–$0.34 per point over haiku), and clears 70 on everything but high-complexity work.
3. **Escalate to opus for high-complexity tasks** — the only model above 70 there, and worth $0.82/point.
4. **Do not drop to haiku because a task looks easy.** It is 15 points behind even on the easiest tier. Drop to haiku when the *deliverable* tolerates it — design documents a human will review — not when the task is small.
5. **Budget for difficulty, not volume.** Opus on high-complexity work costs 16.7× haiku; two hard tasks cost more than fifteen easy ones.

## Caveats

- **n=1 per model per task.** A single task swings a small tier mean by several points. `configurable-mcp-proxy-upstream-timeout` (opus's one loss) is the live example.
- **One task has already been re-tiered on the strength of this run**, and it changed a headline number: `build-docker-images-from-uv-lock` moved `low` → `medium`, taking low's spread from 19.1 to 15.5 and making all three models monotonic. That is a reminder that the tier labels are a judgement, and a wrong one propagates straight into the guidance above.
- **The trivial tier has not been run.** The question of whether the gap closes on genuinely small work is open, not answered here.
- **One harness, one repo.** pi on `mcp-gateway-registry`. Harness effects are real and measured elsewhere in this repo — see [best-harness-selection.md](best-harness-selection.md).
- **Only three models, all Anthropic.** The self-hosted open-weight models on the v1 charts have not been run on v2, so nothing here speaks to the cross-hosting question.
- **Costs are metered Bedrock prices** and not comparable with the hardware-derived figures used for self-hosted models. See [cost-per-task-methodology.md](cost-per-task-methodology.md).
