---
name: swe-auto
description: "Cost-aware router skill: the developer does NOT pick the model. Given a repo + ref + problem, a router model triages the task into a tier (budget | workhorse | frontier), consults the measured cost/quality Pareto frontier, picks the cheapest non-dominated model that clears that tier's band, then runs /swe3 through the in-repo headless runner with the selected model. Escalates one tier and re-runs on non-completion (or, with the judge on, a below-band score), bounded by max_escalations. Produces the six /swe3 artifacts plus routing.json. Runs on Claude Code or pi. Use when someone wants frontier-quality results at workhorse cost without managing model selection."
license: Apache-2.0
metadata:
  author: Amit Arora
  version: "0.1.0"
---

# Cost-Aware Router (SWE-Auto) Skill

Use this skill when the developer wants a coding task done well **without choosing the model themselves**. The skill triages the task, reads the measured cost/quality Pareto frontier this repo produces, and routes the task to the cheapest model that is good enough for it, then runs the `/swe3` skill with that model. It is the first concrete step of [docs/vision.md](../../../docs/vision.md); the flow it follows is the mermaid sequence in that document.

**What this skill does NOT do:** it does not itself design or implement the change. It classifies the task and delegates the actual work to `/swe3` (run through the headless runner). Its own output is the routing decision (`routing.json`) plus the six `/swe3` artifacts the selected model produced.

## The two jobs, and who does them

The skill splits cleanly into a model-driven half (you) and a deterministic half (a tested Python module):

- **You (the router model)** do exactly one judgement call: read the problem and the relevant code, and classify the task into a **tier**. That is the only place model reasoning is needed.
- **The module** (`benchmarks/scripts/swe_auto_run.py`) does everything mechanical: consult the frontier, pick the cheapest model that clears the tier's band, run `/swe3` via the headless runner over an ephemeral one-task dataset, optionally judge it, escalate a tier and re-run if it falls short, and write `routing.json`.

Do **not** pick the model yourself, do the frontier arithmetic yourself, or invoke the runner yourself step by step. Classify the tier, then hand off to the module with one command.

## Non-interactive mode (headless)

When `repo`, `ref`, and a problem source are provided, run end to end without asking questions. The problem can be given **either** as a verbose description **or** as a GitHub issue link:

```
# verbose description
/swe-auto repo: <github-url> ref: <git-tag-or-branch> problem: "<what to do, in enough detail to act on>"

# or a GitHub issue link (the issue is the task description)
/swe-auto repo: <github-url> ref: <git-tag-or-branch> issue: <github-issue-url>
```

The task inputs are **always** user arguments; they are never read from a config file. Only routing behavior lives in `swe-auto.yaml` (see below).

## Step 1: Load the routing config

Read the routing knobs from `swe-auto.yaml` in this skill's own directory (`.claude/skills/swe-auto/swe-auto.yaml`). If it does not exist, fall back to the committed `swe-auto.example.yaml` beside it and say so. Note the values you will need to report: `router_model`, `harness`, `frontier_scope`, `budget_posture`, `judge`, `max_escalations`. Do not edit the config.

## Step 2: Triage the task into a tier (the one model-driven step)

1. **Get the task description.** If the task came as an `issue:` link, fetch that issue read-only (its title and body) and treat that as the description. A verbose `problem:` is used as-is.
2. **Clone the repo read-only at the ref and study it - do not triage from the issue text alone.** The issue tells you *what* to do; the repository tells you *how hard it is here* - its size, stack, conventions, and where the change actually lands - and that is what the tier depends on. Clone into a temporary directory and read; do not edit anything. This is a quick scoping read, not a full analysis (the selected `/swe3` model does the deep work later).
3. **Orient cheaply: read the repo's own agent guide first, so you do not scan the whole tree.** Look for a guide file at the repo root, in this exact order, and let it steer which parts you read:
   - **`AGENTS.md`** (preferred) - the canonical agent guide (repo map + conventions);
   - else **`CLAUDE.md`**;
   - if **neither exists**, say so **loudly** in your output, to this effect: *"No AGENTS.md or CLAUDE.md found in this repository. I will study whatever parts of the repo I judge necessary from the issue, which may consume many more tokens than needed. Adding an AGENTS.md or CLAUDE.md (a repo map plus conventions) would make future runs much cheaper."* Then read the directly relevant paths guided by the task.

   When a guide is present, use it to jump straight to the relevant modules instead of reading everything - that is the point of preferring it.
4. **Classify the task into exactly one tier**, using this rubric:

   | Tier | Use when the task is... | Examples |
   |---|---|---|
   | `budget` | small, mechanical, low-risk; a cheap model will get it right | rename/move, doc update, dependency bump, boilerplate, a small localized fix |
   | `workhorse` | a typical feature or refactor; real but well-scoped engineering | add an endpoint, refactor a module, remove a subsystem, wire a config through |
   | `frontier` | business-critical, cross-cutting, or subtle-correctness/security work where a wrong design is expensive | auth/security changes, data-model or migration work, anything spanning many components or with sharp edge cases |

5. **Write down a one- or two-sentence rationale** for the tier (what about the task put it there). You will pass this along; it is recorded in `routing.json`.

**Tier is about risk multiplied by leverage, not raw size** - a small security change can be `frontier`, and a `low`-complexity feature can be `workhorse`. For worked examples of each tier drawn from the shipped datasets (including two deliberate "small task, high tier" cases), read [triage-examples.md](triage-examples.md) before classifying.

When in doubt between two tiers, pick the **lower** one: the escalation loop will bump it up automatically if the run falls short, so starting low is the cost-aware default.

## Step 3: Hand off to the router module

From the `benchmarks/` directory, run the executor with the tier you chose. It selects the model, runs `/swe3`, judges (if enabled), escalates if needed, and writes `routing.json`:

```bash
cd benchmarks
uv run scripts/swe_auto_run.py \
  --tier <budget|workhorse|frontier> \
  --repo "<github-url>" \
  --ref "<ref>" \
  --problem "<problem-slug>" \
  --problem-statement "<the full task description the developer gave /swe-auto>" \
  --config ../.claude/skills/swe-auto/swe-auto.yaml
```

If the task was given as an issue link, pass `--problem-issue-url <url>` instead of (or in addition to) `--problem-statement`; the runner appends it to the `/swe3` prompt as `Reference issue: <url>`.

Notes:

- Derive `<problem-slug>` as a kebab-case slug of the task (e.g. "remove FAISS" -> `remove-faiss`, or `issue-<number>` for an issue link); it becomes the artifact subfolder name.
- Pass the developer's full task description verbatim as `--problem-statement`; that is what the executed `/swe3` run acts on. For an issue link, pass `--problem-issue-url` (the issue is the source); you may also pass a `--problem-statement` summary you distilled from the issue. With neither, the executor falls back to a generic pointer that only names the slug.
- Preview without executing anything by adding `--dry-run` (prints the selected model and candidates). Check prerequisites only with `--preflight`.
- The module runs its own preflight first and fails early with a clear list if a prerequisite is missing (the agent CLI, the judge when enabled, the `/swe3` skill).
- Do not add `--config` pointing at a file you cannot read; if only the example exists, pass `../.claude/skills/swe-auto/swe-auto.example.yaml`.

## Step 4: Present the result

When the module finishes it prints the routing record (also written to `routing.json` in the selected model's artifact folder). Summarize for the developer:

- The **tier** you classified the task into and why (your rationale).
- The **selected model** and its hosting/pricing basis, and the **candidates considered**.
- Whether the run **completed** all six artifacts and, if the judge ran, its **score** vs. the tier's band.
- Any **escalation** that happened (which tier it bumped to and why).
- Where the artifacts and `routing.json` landed on disk.

Point the developer at the six `/swe3` artifacts (`github-issue.md`, `lld.md`, `review.md`, `testing.md`, `patch.diff`, `implementation.md`) as the deliverable, exactly as `/swe3` would.

## Constraints

- **You classify; the module decides and executes.** Never hardcode or hand-pick the model, and never reimplement the frontier lookup in prose.
- **Triage is read-only.** Do not modify the cloned repo during triage; the `/swe3` run gets its own fresh clone through the runner.
- **The task is always a user argument.** Never take repo/ref/problem from the config file.
- **v1 scope.** One model for the whole task; escalation is between runs (a tier up), not mid-run. The configured `router_model` names the intended classifier; in v1 the triage is performed by the model driving this skill, and both are recorded. Per-phase routing and in-flight model switching are later steps (see docs/vision.md).
- **No emojis or em-dashes** in any output.
