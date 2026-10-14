# cli/cli: does what we learned on one repository carry to another?

Issue #221 asked whether the model rankings, the score levels and the swe-router rubric from `mcp-gateway-registry-v2` (v2) hold on a codebase nobody tuned them on. This page answers it for set A: Claude Haiku 5.5, Sonnet 5.5 and Opus 5.5 on the 21 tasks of [cli-cli-v1.yaml](../benchmarks/dataset/cli-cli-v1.yaml), the GitHub CLI in Go.

> [!NOTE]
> **Terms.**
> **Score**: the judge's 0-100 grade of a task's six artifacts (`openai.gpt-5.6-sol`, high reasoning effort).
> **Failure**: a task where the model left the artifacts outside the folder the prompt named. The judge never sees it. "Failure = 0" counts it as a score of 0.
> **Rubric**: six task dimensions scored 0-2, which set a **required quality** (the score a result must reach) and a **difficulty bucket** (easy, moderate, hard, very hard). See [swe-router-rubric-design.md](swe-router-rubric-design.md).
> **Column**: a model's mean score on the benchmark tasks in one bucket. The router picks the cheapest model whose column clears the required quality.
> **Zero-shot**: routing cli/cli tasks with columns built from v2 alone.

## Short answers

| Question | Answer |
|---|---|
| Do rankings carry over? | Yes overall: Opus 5.5 > Sonnet 5.5 > Haiku 5.5 on both repositories. Within a tier the gaps shrink to a few points, and on the low tier Haiku edges out Sonnet. |
| Do score levels shift? | Yes. All three models score 3 to 8 points higher on cli/cli and cost less per task. |
| Is Haiku still the deciding question? | Yes. Where it finishes, Haiku scores within 2 points of Sonnet. It failed 2 of 21 tasks by writing to the wrong folder, and the router cannot see that risk. |
| Does the rubric work zero-shot? | The judging transfers, and v2's columns route cli/cli tasks a little more cautiously than cli/cli's own. Routing quality on cli/cli is poor for a different reason: the router sends nearly every task to Haiku and ignores its failure rate. |

## The runs

All three ran omp with the swe3 skill on Amazon Bedrock on 2026-10-14. Costs are token counts priced at Bedrock rates.

| Model | v2 score | cli/cli score | v2 failure = 0 | cli/cli failure = 0 | v2 cost (21 tasks) | cli/cli cost (21 tasks) |
|---|---:|---:|---:|---:|---:|---:|
| Haiku 5.5 | 72.69 (20/21) | 80.82 (19/21) | 69.23 | 73.12 | $3.05 | $1.99 |
| Sonnet 5.5 | 79.49 | 82.50 | 79.49 | 82.50 | $55.02 | $19.11 |
| Opus 5.5 | 81.16 | 85.62 | 81.16 | 85.62 | $93.27 | $45.88 |

Source: each model's `run-summary.json` under `benchmarks/swe-benchmark-data/<model>/omp/swe3/{mcp-gateway-registry-v2,cli-cli-v1}/`.

By the dataset's own tiers, with failures as 0:

| Tier | Haiku 5.5 | Sonnet 5.5 | Opus 5.5 |
|---|---:|---:|---:|
| trivial (5) | 79.3 | 85.3 | 90.7 |
| low (5) | 86.7 | 85.3 | 88.2 |
| medium (6) | 80.5 | 84.7 | 85.1 |
| high (5) | 44.5 | 74.4 | 78.6 |

Haiku's high-tier mean is 74.2 without its two failures. Two tasks are hard for every model: `skill-install-nested-discovery` (64.8 for Sonnet, 63.4 for Opus) and `auth-clipboard-config-default` (71.6 and 72.4). Opus scored 69.0 on `issue-view-comments-with-json`, below Haiku's 83.0; with one run per task, a single low score like that is within the noise.

### Haiku's failures

Haiku 5.5 wrote its six artifacts somewhere other than the path the prompt gave on 3 of 21 first attempts. On `auth-clipboard-config-default` it used the skill's generic layout (`claude-haiku-5-5/claude-code/cli/`) on both attempts. On `skill-install-nested-discovery` it wrote to `cli-v1/`, and on the retry it lost the path entirely and asked for one. `repo-clone-ghe-ssh-ca-url` went to `cli-ci-v1/` first and recovered on retry. It did the same once on v2, dropping the `-v2`. The repeated `cli-cli` in the path seems to make it worse. The misplaced artifacts are kept, unjudged, under [do-not-include/claude-haiku-5-5-misplaced-artifacts/](../benchmarks/swe-benchmark-data/do-not-include/README.md).

## The rubric on cli/cli

Haiku 5.5 and Opus 5.5 each scored the 21 tasks three times, reading the task and the cloned repository at its ref. They agree on the required quality for 18 tasks and on the bucket for 13. Opus gave the same bucket in all three repeats on 20 tasks; Haiku did so on 13. Both put most tasks in "hard", as on v2. Opus spreads them more: 2 easy, 7 moderate, 10 hard, 2 very hard. Source: [swe-router-rubric-cli-cli-v1-claude-opus-5-5.json](metrics/swe-router-rubric-cli-cli-v1-claude-opus-5-5.json) and the Haiku file beside it, with readable versions in [docs/](swe-router-rubric-cli-cli-v1-claude-opus-5-5.md).

The bucket tracks measured difficulty. Under Opus's buckets, each model's cli/cli column falls from easy to very hard, as it does on v2:

| Model | v2 moderate | v2 hard | v2 very hard | cli/cli easy | cli/cli moderate | cli/cli hard | cli/cli very hard |
|---|---:|---:|---:|---:|---:|---:|---:|
| Haiku 5.5 | 83.2 | 76.5 | 65.3 (8/9) | 83.8 | 82.1 | 79.7 (9/10) | 75.4 (1/2) |
| Sonnet 5.5 | 86.5 | 80.1 | 77.2 | 87.3 | 84.7 | 82.1 | 72.1 |
| Opus 5.5 | 89.7 | 80.4 | 80.2 | 92.0 | 88.7 | 84.3 | 75.3 |

v2 has no task in the easy bucket. A fraction marks a column where the model failed some of its tasks; the column mean leaves those out.

## Routing replays

Each replay routes all 21 tasks among the three Claude 5.5 models, looks up what the chosen model scored and cost on that task, and compares with Opus 5.5 on every task. "In-repo" builds the columns from the same dataset, leaving the routed task out. The v2 rows use the same three models, so they compare directly.

| Dataset | Columns from | Rubric judge | Cost saved | Quality change | Failure = 0 | Under required quality | Picks (H / S / O) |
|---|---|---|---:|---:|---:|---:|---|
| v2 | v2, in-repo | Opus 5.5 | 45.7% | −1.70 | −1.70 | 4 | 10 / 8 / 3 |
| v2 | v2, in-repo | Haiku 5.5 | 42.6% | −2.17 | −2.17 | 5 | 7 / 11 / 3 |
| cli/cli | **v2, zero-shot** | Opus 5.5 | 88.2% | −6.06 | −9.22 | 4 | 19 / 2 / 0 |
| cli/cli | **v2, zero-shot** | Haiku 5.5 | 88.7% | −6.07 | −11.96 | 3 | 17 / 4 / 0 |
| cli/cli | cli/cli, in-repo | Opus 5.5 | 95.7% | −6.66 | −12.50 | 4 | 21 / 0 / 0 |
| cli/cli | cli/cli, in-repo | Haiku 5.5 | 93.7% | −7.17 | −12.95 | 4 | 20 / 1 / 0 |

For reference, a single model on every cli/cli task: Haiku saves 95.7% for −12.50 (failure = 0); Sonnet saves 58.3% for −3.12. On v2: Haiku saves 96.7% for −11.93; Sonnet saves 41.0% for −1.67.

"Quality change" compares only tasks where the routed model produced a scored run. The two v2 rows count a task with no confident pick as staying on Opus. Two of the v2 Opus-judge picks fell into that case. Source: [swe-router-rubric-replays/](metrics/swe-router-rubric-replays/), files `cli-cli-v1-{opus-5-5,haiku-5-5}-{zero-shot,in-repo}.json` and `v2-claude-5-5-only-{opus-5-5,haiku-5-5}-in-repo.json`.

### What the replays show

**v2's columns transfer, and they err on the safe side.** v2 was harder for every model, so its columns understate cli/cli scores. Where a cli/cli column would send a very hard task to Haiku, v2's column (Haiku at 65.3) sends it to Sonnet. Counting failures as 0, zero-shot routing kept 1 to 3 more points of quality than in-repo routing and saved 5 to 7.5 points less. A customer who starts from our published columns will overpay a little on an easier repository rather than ship weaker work.

**On cli/cli the router becomes "always Haiku", and Haiku's failures cost the quality.** Haiku's columns clear the 70 bar in almost every bucket, so the router picks it for 17 to 21 tasks. Four tasks then miss the bar: Haiku's two wrong-folder failures and its two low scores (61.4 on `extension-uninstall-alias`, 62.4 on `skill-update-dir-keeps-install-path`). The two failures cost 3 to 6 points of mean quality on their own: that is the gap between the "quality change" and "failure = 0" columns.

**The router cannot see the failures.** A column mean leaves failed tasks out, and `route.py` reports `completion_by_complexity` but never uses it to choose. So a model that finishes 9 of 10 hard tasks looks as good as one that finishes 10 of 10. On v2 this did not matter much: Haiku failed once in 21 and the router sent the hard tasks to Sonnet anyway. On cli/cli it is the main source of lost quality.

## What changes for phase 1

1. **Make the router see failures.** Two options. Scoring a failed task as 0 in its column drops Haiku's cli/cli very hard column from 75.4 to 37.7, but its hard column only from 79.7 to 71.7, which still clears 70. Skipping a model whose completion in a bucket falls below a threshold set in `routing-policy.json` keeps Haiku off both buckets. These figures are arithmetic on the columns above; neither option has been replayed yet.
2. **Ship v2's columns as the default, and tell customers to rebuild them on their own tasks.** Zero-shot routing worked and erred towards caution, so the defaults are safe to ship. Columns built on the customer's repository save more.
3. **Keep Opus-class models as the recommended rubric judge.** Haiku 5.5's judgments changed bucket between repeats on 8 of 21 tasks; Opus 5.5's on 1.

The rubric, the policy file and the bucket mapping need no change.

## Limits

- One run per task per model, 21 tasks. Differences under about 3 points are noise.
- Three models. Set B (the open-weight models, about $446) would test whether a cheaper non-Claude model takes Haiku's place on the frontier here.
- The cli/cli tiers in the dataset are provisional, set from each fix's shape before any run.
