# How the swe-router rubric picks a model

`swe-router` recommends which model a developer should use for the coding task in front of them. This page explains the rubric design tested in phase 0. The shipped skill in `vend/swe-router/` still uses the older design, a consequence floor and a complexity tier; tag `swe-router-floor-tier` marks that version. Results for the rubric live in [swe-router-rubric-evaluation.md](swe-router-rubric-evaluation.md).

> [!NOTE]
> **Terms.**
> **Required quality** (the bar): the score a result must reach, from 0 to 100, on the artifact judge's scale.
> **Bucket**: easy, moderate, hard or very hard.
> **Column**: each model's mean measured score on the benchmark tasks in one bucket.
> **Artifact judge**: `codex_judge.py`, which scored every model's work in the benchmark. The rubric never re-runs it.

## The idea in one paragraph

The developer's own model reads the task and the repository and scores six properties of the task, from 0 to 2, citing evidence for each. Code turns two of the scores into a bar and the other four into a bucket. The router then recommends the cheapest allowed model whose measured score in that bucket's column reaches the bar. The model describes the task; it never sees a price, a model name or a threshold.

```text
 task + repository map
        │
        ▼
 the developer's model scores six dimensions, 0-2, with evidence   (rubric.md)
        │
        ├── hidden contract, silent invariant, coordinated surfaces, ambiguity
        │        sum 0-8  ──▶  BUCKET  easy 0-1 · moderate 2-3 · hard 4-5 · very hard 6-8
        │
        └── blast radius, verification
                 ──▶  BAR  60 · 70 · 75  (+5 when nothing would catch a mistake)
                                   (routing-policy.json holds every number)
        │
        ▼
 models.json: each model's measured score on benchmark tasks in that bucket
        │
        ▼
 the cheapest allowed model whose score in that column reaches the bar
```

## Step 1: read the repository, then the task

The model reads `AGENTS.md` at the repository root, else `CLAUDE.md`, else `README.md`, and follows the documents that file links to. It also reads `SECURITY.md` when one exists, because that file says what the project treats as security-sensitive. Then it reads the task and the parts of the repository the task touches: the files it names or implies, the tests around them, and their callers.

Size counts for nothing. The rubric tells the model that line count, file count and task length move no score: a one-line change to an authorisation check can score 2, and a twenty-file mechanical change can score 0.

## Step 2: score six dimensions

| Dimension | The question | Feeds |
|---|---|---|
| Hidden contract | Does something outside the task, such as an earlier issue, a design or another service, define the right behaviour? | bucket |
| Silent invariant | Could a wrong change look like it works, because it breaks a security, data or concurrency guarantee without an error? | bucket |
| Coordinated surfaces | How many separate places (API, command line, user interface, deployment config) must change and agree? | bucket |
| Ambiguity | Does a narrower fix look complete but miss the real problem? | bucket |
| Verification | Would the repository's tests catch a wrong change? | bar |
| Blast radius | What does a mistake cost once shipped, and can a revert undo it? | bar |

`vend/swe-router/rubric.md` defines each dimension: where to look, what 0, 1 and 2 mean, and a common mistake. Every score needs evidence: a file, a document, a test or a sentence of the task. The model also reports its confidence as high, medium or low.

## Step 3: turn scores into a bar and a bucket

`routing-policy.json` holds the numbers, and code applies them.

**The bar** comes from what a mistake would cost:

| Blast radius | Bar | What that score means on the judge's scale |
|---|---:|---|
| 0: throwaway or internal | 60 | bottom of "strong": usable; review will fix real gaps |
| 1: users notice; a revert fixes it | 70 | middle of "strong": ready to implement, with limited gaps |
| 2: security, money or data; hard to undo | 75 | top of "strong": few gaps |

Verification at 2, meaning nothing would catch a mistake, adds 5. The judge gives each of 20 criteria up to 25 points, and its anchors say 16 to 20 per criterion means "implementation-ready in most respects with limited gaps"; a task score of 64 to 80 corresponds to that band.

**The bucket** comes from how demanding the task is: the sum of the four difficulty scores, from 0 to 8.

The bar and the bucket stay separate on purpose. A hard task does not need a better result; it makes every model's result worse, by different amounts. The bucket picks which measured scores to compare, and the bar says how high they must reach.

## Step 4: pick the model

`route.py` reads each allowed model's mean score in the task's bucket from `models.json` and recommends the cheapest model whose score reaches the bar. It treats scores within 3 points of each other as equal. When nothing reaches the bar, it says so and names the shortfall.

Two parts of this step exist only in the evaluation so far. `route.py` knows four tier names rather than bucket names, so the phase-0 replay files the buckets under those names. And `routing-policy.json` sets `when_unsure` to stay on the current model when the judging model reports low confidence; phase 1 implements that in the skill.

`models.json` builds each column from benchmark tasks scored with the same rubric. The skill and its data therefore share one definition of "hard".

## Which file holds what

| File | Read by | Owned by | Changes per customer? |
|---|---|---|---|
| `rubric.md` | the model | this repository | no |
| `routing-policy.json` | code | the customer's platform team | yes: their bar levels and bucket edges |
| `models.json` | code | generated from the customer's benchmark | yes: their measured scores per bucket |
| `allowed-models.txt` | code | the customer's platform team | yes: the models their developers can select |
| `SKILL.md` | the model | this repository | no |

Phase 1 moved `rubric.md` and `routing-policy.json` from `benchmarks/config/swe-router/` into `vend/swe-router/`. The installer keeps a customer's edited `routing-policy.json` on upgrade, as it keeps `allowed-models.txt`.

## How a customer adapts it

1. Benchmark their allowed models on their own repositories (`onboard-benchmark`, then `benchmark`).
2. Score their benchmark tasks with the rubric: `run-swe-router-headless.py --mode rubric --dataset <theirs>`. This reads task descriptions only and re-runs no model.
3. Rebuild `models.json` from their results, grouped by bucket.
4. Optionally edit `routing-policy.json` and `allowed-models.txt`.

The rubric and `SKILL.md` stay the same for every customer.

## What phase 0 found

On the 21 tasks of `mcp-gateway-registry-v2`, with Opus 5.5 judging and every model available, the rubric saved 75.3% of the cost of running `claude-opus-5` on every task, for 3.75 points of lost quality, against 70.5% and 5.06 points for the current skill. Haiku 5.5 judged as well as Opus 5.5 at $0.0135 a judgment, about 4% of Opus 5.5's cost.

Two refinements, relative buckets and a fitted line per model, did no better than plain buckets: 21 tasks run once each cannot tell them apart. Haiku 5.5 lost about 4 points per step of rubric difficulty; the other models lost 1 to 2. Full numbers and caveats: [swe-router-rubric-evaluation.md](swe-router-rubric-evaluation.md).

## What remains before it ships

1. The cli/cli run: 21 tasks on a Go repository, the zero-shot check on a second codebase.
2. Phase 1: move `rubric.md` and `routing-policy.json` into `vend/swe-router/`, rewrite `SKILL.md` around the rubric, teach `route.py` the bucket names and the `when_unsure` fallback, add bucket columns to `models.json`, and update the installer.
