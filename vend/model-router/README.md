# Model Router

A skill that tells you which model to switch your coding assistant to, based on measured scores and cost rather than vendor claims.

It recommends and stops. It does not run your task, change a setting, or write code.

## Why it exists

Most developers pick the strongest model and leave it there. That is a defensible default and an expensive one. On the benchmark behind this skill, `claude-sonnet-5` lands within 5 points of `claude-opus-5` on **10 of 21 tasks** at **61% lower cost per task**, and matches or beats it outright on 5 of them.

Knowing which tasks those are needs measurement. This skill carries the measurements.

## Install

```bash
BASE=https://raw.githubusercontent.com/aarora79/agentic-coding-harness-benchmarks/main/vend/model-router
mkdir -p .claude/skills/model-router
for f in SKILL.md models.json model-aliases.json allowed-models.md; do
  curl -sL -o ".claude/skills/model-router/$f" "$BASE/$f"
done
```

Four files:

| File | |
|---|---|
| `SKILL.md` | the skill itself |
| `models.json` | the measurements — 16 models, scores and cost per tier |
| `model-aliases.json` | model names as different assistants spell them |
| `allowed-models.md` | which models your organisation permits. **Edit this one.** |

The path differs by assistant. The skill has no dependencies and imports nothing — a directory of files is the whole install.

### Restricting it to models your organisation allows

`allowed-models.md` ships with the skill, allowing the five models on the measured frontier. **Edit it.** As written it is a starting point, not a policy: four of those five are self-hosted, so a developer on a hosted API can reach exactly one of them and would be sent to `claude-opus-5` at $11.95 per task for everything, including a docs page. The file says so at the top and lists what to add.

Put your own copy beside the skill, at your repository root, or in `.claude/`; the one nearest the developer's repository wins. `allowed-models.example.md` shows the format: one backticked model name per bullet under an **Allowed** heading, with any note you like after it.

The list is a hard constraint. The skill intersects it with what the benchmark measured and what the assistant can select **before** it ranks anything, so it never recommends a model you are not permitted to use. When the intersection comes out empty it says which of the three tests emptied it — nothing allowed was measured, nothing allowed is selectable, or nothing selectable was measured — and tells the developer to stay put rather than inventing a recommendation.

Delete the file and every model is permitted.

Then ask it: *"which model should I use for this?"*

## What the numbers mean

`models.json` holds 16 models measured on **21 software-engineering tasks** drawn from real closed issues in one open-source repository. Each task asks the model to take a problem from description to a working patch, producing six artifacts: a GitHub issue spec, a low-level design, an expert review, a testing plan, the patch, and an implementation summary. An LLM judge with access to the repository scores each artifact.

| Field | Meaning |
|---|---|
| `score` | Mean 0-100 across the tasks the model completed. Context; the skill selects on `score_by_complexity` |
| `cost_per_task_usd` | Mean cost of one task |
| `hosting` | `Bedrock` or `self-hosted`. Reported, never used to rank |
| `tasks_completed` / `tasks_total` | Three models did not finish all 21 |
| `on_combined_frontier` | Nothing beats it on both axes across all 16 models. Context, not a selection key — it comes from overall means and can disagree with the per-tier ranking |
| `on_hosting_frontier` | The same, computed within one hosting basis, which is the apples-to-apples version |
| `score_by_complexity` | Mean score per tier — the number the floor is compared against |
| `completion_by_complexity` | How many tasks it finished per tier, where failure shows |

### Read these caveats before you trust a number

**One repository.** Every task comes from a Python/FastAPI and React service with nginx, Terraform, Helm and bash around it. Rankings travel better than absolute scores. If you write Rust game engines, treat the ordering as a starting point and the numbers as indicative.

**One run per model per task, 5 or 6 per tier.** Small differences are noise. Dropping a single task from a tier reverses the order of two models 82% of the time when they sit within 1 point of each other, 53% within 2, and 47% within 3 — but only 5% past 5 points, and never past 8. The skill treats anything under 3 points at a tier as a tie and takes the cheaper model.

**Self-hosted costs are measured under load.** Hosted figures come from a metered bill. Self-hosted figures come from the server's hourly price divided by throughput measured at a stated concurrency — a platform team serving a group of developers, not one person with an idle GPU. Both are a cost per task, and the skill ranks them together.

**These numbers move.** A fix to token accounting once changed `claude-opus-5` from $7.63 to $11.95 per task while every score stayed identical. Check `provenance.measured_on` and refetch if it looks old.

## How it decides

Two questions, asked separately, because they answer different things.

**How good does this have to be?** That is about consequence. A one-line change to an auth path can ruin someone's week; a fifty-line change to a scratch script cannot. Consequence sets a **floor** — the score a model has to reach before it is worth considering.

**How hard is this?** That is about the work itself. It does not change the floor. It changes **which measured score** gets compared against the floor, because models fall off at very different rates as tasks get harder.

Keeping them apart is the whole trick. Collapsing them — treating a big task as a high-stakes one — is how you end up paying for the top model to write a docs page.

```
   AGENTS.md ──▶ read the repo's own map
   CLAUDE.md         (fall back: README.md, CONTRIBUTING.md)
       │
       ▼
   the task ─────┬──────────────────────┐
                 │                      │
                 ▼                      ▼
      what happens if           how hard is it?
      this is wrong?                    │
                 │                      │
                 ▼                      ▼
        ┌────────────────┐    ┌──────────────────┐
        │ prototype   55 │    │ trivial          │
        │ internal    65 │    │ low              │
        │ production  70 │    │ medium           │
        │ security    75 │    │ high             │
        └────────────────┘    │ beyond range ──▶ strongest available,
                 │            └──────────────────┘  say so, stop
                 │                      │
            +5 if it turns              │  picks WHICH TABLE
            on one exact fact           │
                 │                      │
                 ▼                      ▼
              FLOOR  ◀── read against ──  that tier's table
                              │
                              ▼
         allowed-models.md ── if present, a hard filter
                    │
                    ▼
         your assistant's model list
                    │
          ┌─────────┴─────────┐
          ▼                   ▼
    in models.json      not measured
          │              (named, excluded)
          │
          ├── empty? say which of the three
          │   tests emptied it, then stop
          ▼
        cheapest at or above the floor
        gaps under 3 pts count as ties
                    │
         ┌──────────┼──────────────┐
         ▼          ▼              ▼
     switch to   already        nothing
      model X    on it          clears it
         │          │              │
      say what   stay put      stay put, and
      it costs                 name the shortfall
```

### Why the floor comes from consequence, not size

The natural instinct is to reach for a stronger model when a task looks big. The measurements do not support it.

On the benchmark, five tasks all classed as `trivial` — every one a single-file change — ranged from a **0.4-point** gap between the best and second-best model to a **13.8-point** gap. Three were mechanical: write a docs index, add two config passthroughs, narrow a render condition. On those, the expensive model bought nothing. Two turned on knowing one exact thing — that BSD `sed -i` swallows its next argument, that a version check has to compare rather than test for existence. On those it was worth 10 to 14 points.

Same size. Opposite answers. What separated them was whether the task hinged on getting one specific thing right, which is why that gets a +5 on the floor and size gets nothing.

### Why difficulty picks the table

Models do not degrade in parallel. Comparing a floor against a whole-dataset average hides that, and the hiding is not small:

| Model | overall | on `low` | on `high` | finished `high` |
|---|---:|---:|---:|:-:|
| `claude-opus-5` | 82.83 | 86.2 | 79.8 | 5/5 |
| `claude-sonnet-5` | 76.97 | 80.5 | 73.7 | 5/5 |
| `qwen3.8-27b` | 78.48 | 80.9 | 71.5 | **4/5** |
| `kimi-k2.7-code` | 69.98 | 74.9 | 63.1 | **4/5** |
| `gemma-4-31b` | 59.74 | 63.3 | 50.0 | 5/5 |

`qwen3.8-27b` outscores `claude-sonnet-5` overall, 78.48 against 76.97. On hard work it trails by 2.2 points. **The ranking between them flips with the tier**, so a recommendation built on the overall column is wrong for half the tasks it covers.

It also failed one hard task outright. That never appears in a mean, because a failure is excluded rather than averaged in — which is what `completion_by_complexity` is for. A model finishing 4 of 5 hard tasks fails one in five, and the skill says so instead of quoting the average of the four that worked.

How much difficulty matters depends on the pair. Between `claude-opus-5` and `claude-sonnet-5` it explains 4% of the gap; between `claude-opus-5` and `gemma-4-31b`, 43%. Two frontier models degrade together. A frontier model and a small one do not.

### The four tables

`score_by_complexity` is one table per tier, and this is what they look like. Each is sorted cheapest first, which is the order the skill reads them in: **scan down until the score clears your floor, and stop.** That first hit is the recommendation.

A bold completion count means the model failed at least one task at that tier, which no score can show — a failure is excluded from the mean rather than averaged into it.

**`trivial`** — scan down until the score clears your floor.

| $/task | Model | Score | Finished |
|---:|---|---:|:-:|
| $0.26 | `qwen3.6-35b` | 58.4 | 5/5 |
| $0.47 | `qwen3-coder-30b` | 45.6 | 5/5 |
| $0.48 | `minimax-m2.5` | 50.2 | 5/5 |
| $0.76 | `claude-haiku-4-5` | 55.4 | 5/5 |
| $0.82 | `devstral-2-123b` | 46.9 | 5/5 |
| $0.87 | `gemma-4-31b` | 66.5 | 5/5 |
| $1.47 | `qwen3.8-27b` | 81.4 | 5/5 |
| $2.61 | `deepseek-v3.2` | 64.9 | 5/5 |
| $3.13 | `kimi-k2.7-code` | 70.7 | 5/5 |
| $4.18 | `claude-opus-4-5` | 68.8 | 5/5 |
| $4.67 | `claude-sonnet-5` | 76.1 | 5/5 |
| $4.95 | `claude-opus-4-6-v1` | 74.2 | 5/5 |
| $5.32 | `claude-opus-4-8` | 73.8 | 5/5 |
| $7.35 | `claude-opus-4-7` | 77.8 | 5/5 |
| $8.09 | `glm-5.3` | 81.5 | 5/5 |
| $11.95 | `claude-opus-5` | 83.8 | 5/5 |

**`low`** — scan down until the score clears your floor.

| $/task | Model | Score | Finished |
|---:|---|---:|:-:|
| $0.26 | `qwen3.6-35b` | 62.5 | 5/5 |
| $0.47 | `qwen3-coder-30b` | 48.4 | 5/5 |
| $0.48 | `minimax-m2.5` | 52.0 | 5/5 |
| $0.76 | `claude-haiku-4-5` | 57.8 | 5/5 |
| $0.82 | `devstral-2-123b` | 58.1 | **4/5** |
| $0.87 | `gemma-4-31b` | 63.3 | 5/5 |
| $1.47 | `qwen3.8-27b` | 80.9 | 5/5 |
| $2.61 | `deepseek-v3.2` | 65.2 | 5/5 |
| $3.13 | `kimi-k2.7-code` | 74.9 | 5/5 |
| $4.18 | `claude-opus-4-5` | 66.2 | 5/5 |
| $4.67 | `claude-sonnet-5` | 80.5 | 5/5 |
| $4.95 | `claude-opus-4-6-v1` | 75.4 | 5/5 |
| $5.32 | `claude-opus-4-8` | 81.1 | 5/5 |
| $7.35 | `claude-opus-4-7` | 77.0 | 5/5 |
| $8.09 | `glm-5.3` | 84.4 | 5/5 |
| $11.95 | `claude-opus-5` | 86.2 | 5/5 |

**`medium`** — scan down until the score clears your floor.

| $/task | Model | Score | Finished |
|---:|---|---:|:-:|
| $0.26 | `qwen3.6-35b` | 59.9 | 6/6 |
| $0.47 | `qwen3-coder-30b` | 40.8 | 6/6 |
| $0.48 | `minimax-m2.5` | 55.3 | 6/6 |
| $0.76 | `claude-haiku-4-5` | 57.8 | 6/6 |
| $0.82 | `devstral-2-123b` | 43.1 | **3/6** |
| $0.87 | `gemma-4-31b` | 59.3 | 6/6 |
| $1.47 | `qwen3.8-27b` | 78.7 | 6/6 |
| $2.61 | `deepseek-v3.2` | 60.9 | 6/6 |
| $3.13 | `kimi-k2.7-code` | 69.8 | 6/6 |
| $4.18 | `claude-opus-4-5` | 67.9 | 6/6 |
| $4.67 | `claude-sonnet-5` | 77.5 | 6/6 |
| $4.95 | `claude-opus-4-6-v1` | 68.3 | 6/6 |
| $5.32 | `claude-opus-4-8` | 73.3 | 6/6 |
| $7.35 | `claude-opus-4-7` | 73.6 | 6/6 |
| $8.09 | `glm-5.3` | 81.8 | 6/6 |
| $11.95 | `claude-opus-5` | 81.8 | 6/6 |

**`high`** — scan down until the score clears your floor.

| $/task | Model | Score | Finished |
|---:|---|---:|:-:|
| $0.26 | `qwen3.6-35b` | 56.0 | 5/5 |
| $0.47 | `qwen3-coder-30b` | 35.8 | 5/5 |
| $0.48 | `minimax-m2.5` | 55.2 | 5/5 |
| $0.76 | `claude-haiku-4-5` | 53.4 | 5/5 |
| $0.82 | `devstral-2-123b` | 42.7 | 5/5 |
| $0.87 | `gemma-4-31b` | 50.0 | 5/5 |
| $1.47 | `qwen3.8-27b` | 71.5 | **4/5** |
| $2.61 | `deepseek-v3.2` | 53.0 | 5/5 |
| $3.13 | `kimi-k2.7-code` | 63.1 | **4/5** |
| $4.18 | `claude-opus-4-5` | 62.0 | 5/5 |
| $4.67 | `claude-sonnet-5` | 73.7 | 5/5 |
| $4.95 | `claude-opus-4-6-v1` | 65.1 | 5/5 |
| $5.32 | `claude-opus-4-8` | 70.8 | 5/5 |
| $7.35 | `claude-opus-4-7` | 74.4 | 5/5 |
| $8.09 | `glm-5.3` | 77.2 | 5/5 |
| $11.95 | `claude-opus-5` | 79.8 | 5/5 |

### Where the numbers stop

The hardest tasks measured are bounded changes inside one repository — a rate-limiting subsystem, server-side OAuth token storage. Nothing here is a rewrite, a language port, or a change spanning several services.

Asked about work beyond that range, the skill recommends the strongest model available and tells you the measurements do not reach that far. Extrapolating a cheap model onto a job three orders of magnitude larger than anything tested is not a saving.

## Regenerating the data

Inside the benchmark repository:

```bash
cd benchmarks
uv run scripts/build_vended_models.py           # rewrite models.json
uv run scripts/build_vended_models.py --check   # CI: fail if out of date
```

`models.json` is generated from `docs/metrics/pareto-frontier-omp-swe3.json` and never edited by hand.

## Source

Measurements, harness and methodology: [aarora79/agentic-coding-harness-benchmarks](https://github.com/aarora79/agentic-coding-harness-benchmarks). Design notes and open questions: issue #161.
