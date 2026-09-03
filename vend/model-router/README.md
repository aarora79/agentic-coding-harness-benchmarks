# Model Router

A skill that tells you which model to switch your coding assistant to, based on measured scores and cost rather than vendor claims.

It recommends and stops. It does not run your task, change a setting, or write code.

## Why it exists

Most developers pick the strongest model and leave it there. That is a defensible default and an expensive one. On the benchmark behind this skill, `claude-sonnet-5` lands within 5 points of `claude-opus-5` on **10 of 21 tasks** at **61% lower cost per task**, and matches or beats it outright on 5 of them.

Knowing which tasks those are needs measurement. This skill carries the measurements.

## Install

Copy the four files into your assistant's skills directory:

```bash
mkdir -p .claude/skills/model-router
curl -sL -o .claude/skills/model-router/SKILL.md \
  https://raw.githubusercontent.com/aarora79/agentic-coding-harness-benchmarks/main/vend/model-router/SKILL.md
curl -sL -o .claude/skills/model-router/models.json \
  https://raw.githubusercontent.com/aarora79/agentic-coding-harness-benchmarks/main/vend/model-router/models.json
curl -sL -o .claude/skills/model-router/model-aliases.json \
  https://raw.githubusercontent.com/aarora79/agentic-coding-harness-benchmarks/main/vend/model-router/model-aliases.json
```

The path differs by assistant. The skill has no dependencies and imports nothing — four files in a directory is the whole install.

Then ask it: *"which model should I use for this?"*

## What the numbers mean

`models.json` holds 16 models measured on **21 software-engineering tasks** drawn from real closed issues in one open-source repository. Each task asks the model to take a problem from description to a working patch, producing six artifacts: a GitHub issue spec, a low-level design, an expert review, a testing plan, the patch, and an implementation summary. An LLM judge with access to the repository scores each artifact.

| Field | Meaning |
|---|---|
| `score` | Mean 0-100 across the tasks the model completed |
| `cost_per_task_usd` | Mean cost of one task |
| `hosting` | `Bedrock` (metered bill) or `self-hosted` (derived from GPU cost) |
| `tasks_completed` / `tasks_total` | Three models did not finish all 21 |
| `on_combined_frontier` | Nothing beats it on both axes across all 16 models. Context, not a selection key — it comes from overall means and can disagree with the per-tier ranking |
| `on_hosting_frontier` | The same, computed within one hosting basis, which is the apples-to-apples version |
| `score_by_complexity` | Mean score per tier — the number the floor is compared against |
| `completion_by_complexity` | How many tasks it finished per tier, where failure shows |

### Read these caveats before you trust a number

**One repository.** Every task comes from a Python/FastAPI and React service with nginx, Terraform, Helm and bash around it. Rankings travel better than absolute scores. If you write Rust game engines, treat the ordering as a starting point and the numbers as indicative.

**One run per model per task.** A 2-point difference between two models is not a reliable measurement. A 10-point one is. The skill is told not to recommend a downgrade on a thin margin.

**Self-hosted costs assume a busy server.** Hosted figures come from a metered bill. Self-hosted figures come from GPU-hour price divided by measured throughput, which holds at high utilisation and understates the cost of an idle box. The skill ranks on cost either way and says so when it recommends a self-hosted model.

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
            +5 if it turns              │  picks the column
            on one exact fact           │
                 │                      │
                 ▼                      ▼
              FLOOR  ◀── compared against ── SCORE AT THAT TIER
                              │
                              ▼
                    your assistant's model list
                              │
                    ┌─────────┴─────────┐
                    ▼                   ▼
              in models.json      not measured
                    │              (named, excluded)
                    ▼
        cheapest at or above the floor
        ties break on the higher score
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

### Why difficulty picks the column

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
