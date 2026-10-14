# Does a task rubric route better than today's swe-router?

Phase 0 of replacing `swe-router`'s two free-form judgments with one rubric. Tested on the 21 tasks of `mcp-gateway-registry-v2` against the benchmark results already on disk. Nothing was re-run or re-judged.

**Verdict.** The rubric routes better than today's skill for a developer on Claude Opus 5.5: it saves more and drops below the quality bar on fewer tasks. For a developer on Claude Haiku 5.5 it works when the candidates are Amazon Bedrock models, at 4% of the judging cost; with self-hosted models allowed, it once sent a hard task to a model that failed it. Two refinements I expected to help, relative buckets and a fitted line per model, did not consistently improve on plain buckets. With 21 tasks run once each, the differences between these methods are within noise; more tasks, not more methods, is the next step.

> [!NOTE]
> **Terms.**
> **Rubric pass**: a model reads a task and its repository and scores six dimensions from 0 to 2 (`benchmarks/config/swe-router/rubric.md`). It never sees any model's output.
> **Required quality**: the score a result must reach, set by blast radius and verification (`routing-policy.json`).
> **Bucket**: easy, moderate, hard or very hard, from the sum of the other four dimensions.
> **Column**: each model's mean measured score on the tasks in one bucket.
> **Leave-one-out**: each task is routed from columns built without it, so no task helps choose its own model.
> **Under floor**: the routed model's measured score fell below the task's required quality.
> **Separation**: the chance that a task which needed more than Haiku 5.5 is rated harder than one Haiku 5.5 handled. 0.5 is a coin toss, 1.0 is perfect.

## What was tested

| Step | Input | New cost |
|---|---|---|
| Rubric pass with Haiku 5.5 | 21 tasks × 3 repeats, through Claude Code 2.1.296 on Amazon Bedrock | $0.84 ($0.0135 a judgment) |
| Rubric pass with Opus 5.5 | the same | $20.23 ($0.32 a judgment) |
| Replay | every model's existing score and cost on every task | none |

Each replay routes all 21 tasks, picks the cheapest model whose column clears the required quality, looks up what that model actually scored and cost on that task, and compares the total with running `claude-opus-5` on everything. **Today's skill** is replayed the same way from its existing judgments (`swe-router-judged-inputs-omp.json`: Opus 5 under omp, $0.44 a judgment), on today's 23-model data. Its published figure of 45.4% predates the Claude 5.5 models.

Two quality measures are shown. The replay's own measure compares only tasks where both arms produced a scored run, which leaves out a task the routed model failed outright. The second counts such a failure as 0.

## Cost and quality

Against `claude-opus-5` on every task ($251.04, mean score 82.83):

| Judgment | Candidates | Cost saved | Quality change | Quality change, failure = 0 | Routed failures | Under floor |
|---|---|---:|---:|---:|---:|---:|
| Today's skill | all 23 | 70.5% | −5.06 | −5.06 | 0 | 9 |
| **Rubric, Opus 5.5** | all 23 | **75.3%** | **−3.75** | **−3.75** | 0 | **4** |
| Rubric, Haiku 5.5 | all 23 | 85.1% | −3.64 | −7.17 | 1 | 6 |
| Today's skill | Bedrock (11) | 68.0% | −3.10 | −3.10 | 0 | 7 |
| **Rubric, Opus 5.5** | Bedrock (11) | **74.7%** | −3.57 | −3.57 | 0 | **4** |
| **Rubric, Haiku 5.5** | Bedrock (11) | **78.7%** | −3.84 | −3.84 | 0 | 5 |

Source: `docs/metrics/swe-router-rubric-replays/{today,haiku-5-5-absolute,opus-5-5-absolute}-{all,bedrock}.json`.

**A developer on Opus 5.5.** The rubric beats today's skill with every model available, on cost, quality and floor breaches. With Bedrock models only it saves 6.7 points more and breaches the floor on 4 tasks instead of 7, for 0.47 points more quality loss, which is within the noise of 21 tasks.

**A developer on Haiku 5.5.** With Bedrock models only, it saves the most of the three for a similar quality loss. With every model available, it sent `lifecycle-workflow-webhooks` to the self-hosted `qwen3.8-27b`, which failed that task. Counted as 0, that failure makes it the worst of the three on quality. The replay's own measure hides this; read the failure = 0 column.

## Is the judgment stable, and does it track need?

"Need" is measured from the existing runs: on the Bedrock ladder (Haiku 5.5, Sonnet 5.5, Opus 5.5) at a bar of 70, 14 tasks were handled by Haiku 5.5 and 7 needed more.

| | Rubric, Haiku 5.5 | Rubric, Opus 5.5 | Today's skill |
|---|---|---|---|
| Same required quality in all 3 repeats | 16/21 | 14/21 | floor: 14/21 |
| Same bucket in all 3 repeats | 15/21 | **19/21** | tier: 18/21 |
| Separation, difficulty sum | **0.82** | 0.78 | not measured |
| Separation, bucket | 0.68 | 0.73 | |
| Separation, required quality | 0.53 | 0.66 | |

Source: `docs/metrics/swe-router-rubric-claude-{haiku-5-5,opus-5-5}.json` and the per-task scores in each model's `run-summary.json`.

**The two judges agree.** Same bucket on 16 of 21 tasks, same required quality on 18 of 21, and never more than one bucket apart. Haiku 5.5 sorts tasks at least as well as Opus 5.5, at 4% of the cost per judgment.

Required quality separates poorly, which is expected: it measures what a mistake costs, not how demanding the work is.

## Which dimensions carry the signal

Separation of each dimension on its own:

| Dimension | Haiku 5.5 | Opus 5.5 | Feeds |
|---|---:|---:|---|
| Silent invariant | 0.72 | **0.79** | difficulty |
| Coordinated surfaces | **0.79** | 0.63 | difficulty |
| Ambiguity | 0.57 | 0.71 | difficulty |
| Hidden contract | 0.64 | 0.61 | difficulty |
| Blast radius | 0.68 | **0.79** | required quality |
| Verification | 0.36 | 0.43 | required quality |

Silent invariant is strong under both judges. Hidden contract is weaker than the judge's verdicts suggested, where "a contract established elsewhere" explained both Opus-level tasks. Verification runs backwards: the harder tasks here tend to have more tests around them. It feeds only the required quality, so it does not distort the ranking, but its +5 may raise the bar on the wrong tasks.

## What did not work: relative buckets

Almost every task landed in the top two absolute buckets: Haiku 5.5 put 13 in very hard and 7 in hard, Opus 5.5 9 and 10. Models score the dimensions generously. Relative buckets, quarters of the tasks' own difficulty sums, were meant to fix that.

They sorted tasks better and routed worse:

| | Absolute buckets | Relative buckets |
|---|---|---|
| Separation, Haiku 5.5 / Opus 5.5 | 0.68 / 0.73 | 0.80 / 0.78 |
| Quality change, Opus 5.5, all models | **−3.75** | −5.74 |
| Quality change, Haiku 5.5, Bedrock | **−3.84** | −4.70 |
| Quality change, Opus 5.5, Bedrock | **−3.57** | −4.49 |
| Quality change (failure = 0), Haiku 5.5, all models | −7.17 | **−4.84** |

Source: `docs/metrics/swe-router-rubric-replays/*-relative-*.json`.

Quarters of 21 tasks leave columns of 3 to 12 tasks, fewer again under leave-one-out, so each model's column mean rests on a handful of runs. That noise costs more than the better sorting gains. The policy keeps `absolute` as the default and offers `relative` for task sets large enough to fill four columns.

The finding pointed at a smoother approach, tested next.

## The smooth version: a line per model

Instead of bucket columns, each model's score is fitted as a straight line in the difficulty sum over the other 20 tasks (`eval_swe_router.py --column-model regression`), and the router compares the required quality against each model's predicted score at the routed task's difficulty. Every task informs every prediction, so no estimate rests on a thin column.

| Judge, candidates | Today's skill | Absolute buckets | Line per model |
|---|---:|---:|---:|
| Haiku 5.5, all models (failure = 0) | −5.06 | −7.17 | **−3.40** |
| Haiku 5.5, Bedrock | −3.10 | −3.84 | −4.06 |
| Opus 5.5, all models | −5.06 | **−3.75** | −5.72 |
| Opus 5.5, Bedrock | −3.10 | **−3.57** | −5.02 |

Quality change against `claude-opus-5`. Cost saved with the line: 78.3% and 73.6% (Haiku 5.5 judging), 71.1% and 71.3% (Opus 5.5). Source: `docs/metrics/swe-router-rubric-replays/*-regression-*.json`.

It helps in one cell and hurts in the others. The fitted lines show why:

| Model | Points lost per step of difficulty, Haiku 5.5 judging | Opus 5.5 judging | Spread of single-task scores around the line |
|---|---:|---:|---:|
| claude-haiku-5-5 | **4.2 ± 1.5** | **3.6 ± 1.4** | about 11 |
| claude-sonnet-5-5 | 1.3 ± 1.3 | 1.9 ± 1.1 | about 9 |
| claude-opus-5-5 | 1.0 ± 1.2 | 1.7 ± 1.0 | about 8 |
| claude-opus-5 | 1.0 ± 0.7 | 1.8 ± 0.5 | about 4-5 |

± is one standard error. Spread is the residual standard deviation, in score points.

Two conclusions:

- **Haiku 5.5 is the only model that loses a lot as the rubric's difficulty rises**: about 4 points per step, more than two standard errors from zero under both judges. The others lose 1 to 2 points per step; for Sonnet 5.5 and Opus 5.5 that is within two standard errors of zero, and for Opus 5 it is small but clear. On this data, the routing decision that matters most is whether a task is easy enough for Haiku 5.5.
- **The 21 tasks cannot tell the column methods apart.** A single task's score varies by about 8-11 points around its line for most models, and the methods differ by 1 to 2 points of mean quality. Further tuning on these tasks would fit noise. The policy keeps absolute buckets, the simplest; the line is kept as an option.

## Caveats

- **21 tasks, one repository, one run per model per task.** Differences of a point or two in quality are within noise.
- **Today's skill was judged by a different model and harness** (Opus 5 under omp) from the rubric passes (Claude Code). The comparison is between the two procedures as each was run, not between judges.
- **The defaults were set before the run and not tuned on it.** Bucket edges, required-quality levels and the +5 are as drafted in `routing-policy.json`.

## Next

1. Run the rubric unchanged on the cli/cli tasks (`plan-cli-cli-cross-repo-benchmark.md`): 21 independent tasks, the zero-shot check on a second repository, and twice the data for estimating columns.
2. Check whether "is this easy enough for Haiku 5.5?" holds there too, since only Haiku 5.5's score moved with difficulty here.
3. Decide on phase 1, moving the rubric into the shipped skill, with absolute buckets as the default.

## Reproduce

From `benchmarks/`:

```bash
# Rubric passes (Claude Code on Amazon Bedrock)
uv run scripts/run-swe-router-headless.py --mode rubric --agent claude --provider bedrock \
    --model us.anthropic.claude-haiku-5-5 --aws-region us-east-1 --repeats 3 \
    --out ../docs/metrics/swe-router-rubric-claude-haiku-5-5.json \
    --out-md ../docs/swe-router-rubric-claude-haiku-5-5.md

# Replay, leave-one-out, every model available
uv run scripts/eval_swe_router.py --holdout --no-allow-list \
    --rubric-inputs ../docs/metrics/swe-router-rubric-claude-haiku-5-5.json --bucketing absolute

# Today's skill, the same way
uv run scripts/eval_swe_router.py --holdout --no-allow-list \
    --judged-inputs ../docs/metrics/swe-router-judged-inputs-omp.json
```

Add `--available <comma-separated Bedrock models>` for the Bedrock-only rows.
