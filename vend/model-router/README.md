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
| `on_combined_frontier` | Annotation only — the skill recomputes this over your models |

### Read these caveats before you trust a number

**One repository.** Every task comes from a Python/FastAPI and React service with nginx, Terraform, Helm and bash around it. Rankings travel better than absolute scores. If you write Rust game engines, treat the ordering as a starting point and the numbers as indicative.

**One run per model per task.** A 2-point difference between two models is not a reliable measurement. A 10-point one is. The skill is told not to recommend a downgrade on a thin margin.

**Two cost bases that do not compare.** Hosted figures come from a metered bill. Self-hosted figures come from GPU-hour price divided by measured throughput, assuming the server stays busy. The skill avoids the problem by ranking only within models you can actually select.

**These numbers move.** A fix to token accounting once changed `claude-opus-5` from $7.63 to $11.95 per task while every score stayed identical. Check `provenance.measured_on` and refetch if it looks old.

## How it decides

1. **Reads your repo and task, then asks what happens if the change is wrong.** That sets a quality floor — 55 for a prototype, 75 for a security path. Not how big the task is: on this data, task complexity explains only **6%** of the difference between models.
2. **Asks your assistant which models it can select.** A self-hosted model you have wired up appears; one you have not does not. Getting a model is not the skill's problem.
3. **Recommends the cheapest of those that clears the floor** — or tells you to stay where you are, which is often the right answer.

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
