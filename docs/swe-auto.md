# /swe-auto: the cost-aware router skill

`/swe-auto` is the first concrete slice of [the vision](vision.md): a skill where the developer does **not** pick the model. Given a repo, a ref, and a problem, it triages the task into a tier, consults the measured [cost/quality Pareto frontier](../README.md#results-a-worked-example) this repo produces, picks the cheapest non-dominated model that clears that tier's quality band, and runs the [`/swe3`](../.claude/skills/swe3/SKILL.md) skill with that model through the in-repo headless runner. If the run falls short it escalates one tier and re-runs. It works on **Claude Code or pi**, and tracks issue [#123](https://github.com/aarora79/agentic-coding-harness-benchmarks/issues/123).

The point: **frontier-quality results at workhorse-level cost**, without a human choosing the model per task. The frontier this repo measures is the lookup table; `/swe-auto` is the consumer.

## How it works

The skill splits into a model-driven half and a deterministic half, matching the sequence diagram in [vision.md](vision.md):

1. **Triage (model-driven).** The router model clones the repo read-only, reads the problem and the relevant code, and classifies the task into one tier: **budget** (small/mechanical/low-risk), **workhorse** (a typical feature or refactor), or **frontier** (business-critical, cross-cutting, or subtle-correctness/security work). This is the only step that needs model reasoning; it lives in [the skill](../.claude/skills/swe-auto/SKILL.md).
2. **Select (deterministic).** [`benchmarks/scripts/swe_auto_router.py`](../benchmarks/scripts/swe_auto_router.py) reads the frontier JSON for the chosen harness+skill, maps the tier to a quality band (shifted by `budget_posture`), and picks the **cheapest model that clears the band** (the frontier tier picks the top-scoring model regardless of cost). Reliability gating prefers models that completed every task in the frontier data.
3. **Execute (deterministic).** [`benchmarks/scripts/swe_auto_run.py`](../benchmarks/scripts/swe_auto_run.py) writes an ephemeral one-task dataset and runs `run-swe-headless.py --agent <harness> --model <selected> --skill swe3` over it, producing the six `/swe3` artifacts.
4. **Judge + escalate (optional / deterministic).** With `judge` on, the codex judge scores the run. If the run did not complete all six artifacts, or (with the judge on) scored below its tier's band, the router escalates one tier and re-runs, bounded by `max_escalations`.
5. **Present.** Every attempt and the final decision are written to `routing.json` beside the artifacts.

## Quick start

The skill reads its knobs from `swe-auto.yaml` in its own directory. Create it from the template once:

```bash
cp .claude/skills/swe-auto/swe-auto.example.yaml .claude/skills/swe-auto/swe-auto.yaml
# edit swe-auto.yaml: confirm the Bedrock model ids for your account, add any
# self-hosted endpoints you run
```

Then invoke the skill (from Claude Code or pi):

```
/swe-auto repo: https://github.com/agentic-community/mcp-gateway-registry ref: 1.24.4 problem: "Remove FAISS from the codebase and documentation."
```

The task can also be given as a **GitHub issue link** instead of a verbose description - the skill fetches the issue to triage it, and the runner appends it to the `/swe3` prompt as `Reference issue: <url>`:

```
/swe-auto repo: https://github.com/agentic-community/mcp-gateway-registry ref: 1.24.4 issue: https://github.com/agentic-community/mcp-gateway-registry/issues/1285
```

You can also drive the deterministic half directly, which is useful for previewing a decision or checking prerequisites without running anything:

```bash
cd benchmarks

# Preview the routing decision for a tier (no clone, no run, no judge):
uv run scripts/swe_auto_run.py --tier workhorse --dry-run \
    --config ../.claude/skills/swe-auto/swe-auto.yaml

# Check prerequisites only (agent CLI, judge, the /swe3 skill):
uv run scripts/swe_auto_run.py --tier workhorse --preflight \
    --config ../.claude/skills/swe-auto/swe-auto.yaml
```

## Worked example: a `--dry-run` decision

Previewing a `workhorse` task against the `bedrock-only` frontier for the Claude Code harness selects the cheapest Bedrock model that clears the 54-point band:

```json
{
  "selection": {
    "tier": "workhorse",
    "band_floor": 54.0,
    "selected_model": "claude-opus-4-8",
    "clears_band": true,
    "candidates_considered": ["claude-haiku-4-5", "claude-opus-4-8", "claude-opus-5"],
    "rationale": "tier=workhorse (band >= 54), scope=bedrock-only, posture=balanced: "
  },
  "execution": { "provider": "bedrock", "model": "us.anthropic.claude-opus-4-8", "endpoint": null }
}
```

Here `claude-haiku-4-5` is a candidate but scores below the 54 band on this frontier, so it is skipped; `claude-opus-4-8` clears it and is cheaper than `claude-opus-5`, so it wins. Change `--budget-posture cheap` and the band drops by `posture_shift_points`; change `--frontier-scope self-hosted-only` and it routes among self-hosted models instead (which need a running endpoint, see below).

## Configuration

All knobs live in `swe-auto.yaml` (documented in full in [swe-auto.example.yaml](../.claude/skills/swe-auto/swe-auto.example.yaml)); each can be overridden per invocation.

| Knob | Default | Meaning |
|---|---|---|
| `router_model` | `claude-opus-5` | The model that triages the task into a tier. |
| `harness` | `pi` | Which agent the executor runs `/swe3` under (`claude-code` or `pi`); also selects which frontier JSON is read. Defaults to `pi` (single-agent, typically faster and cheaper per task). |
| `frontier_file` | canonical GitHub raw URL | Which `pareto-frontier-*.json` to consult. A local `docs/metrics` copy is the fallback if the URL is unreachable. |
| `frontier_scope` | `combined` | `combined` (cross-hosting, directional cost) / `bedrock-only` / `self-hosted-only`. |
| `budget_posture` | `balanced` | Shifts the budget/workhorse bars: `cheap` lowers, `best` raises. |
| `tier_bands` | budget 47 / workhorse 54 / frontier=top | Minimum mean score each tier must clear. Calibrate against the current frontier. |
| `judge` | `true` | Score the run with the codex judge. Off = escalate on non-completion only. |
| `max_escalations` | `1` | How many times the router may escalate a tier and re-run. |
| `reliability_gating` | `true` | Prefer models that completed every task in the frontier data. |
| `model_execution` | Bedrock-seeded | How to launch each selectable frontier model (see below). |

### The frontier is the selectable universe

`/swe-auto` only ever picks from models **on the frontier** for the chosen harness+skill; it never invents a model. The `model_execution` block is **not** a second catalog of models: it only says *how to launch* a frontier model that the frontier JSON does not itself describe (the wire model id and, for self-hosted, the endpoint URL).

- **Bedrock models work out of the box.** The provider is derived from the frontier entry's hosting, and the Anthropic inference-profile ids are built in (or derived as `us.anthropic.<slug>` for an unknown `claude-*` slug), so the Bedrock path needs zero registry config beyond valid AWS credentials.
- **Self-hosted models need an endpoint.** A self-hosted frontier model is only selectable once you add its `endpoint` (a vLLM server already serving it) to `model_execution` in `swe-auto.yaml`. Until then it is simply skipped, so an out-of-the-box run routes among whatever is actually reachable (Bedrock by default).

### Frontier freshness

`routing.json` records `frontier_file`, `frontier_source` (`github-raw` / `local-fallback` / an explicit path), and `frontier_as_of`. When the canonical URL is unreachable and the committed local copy is used instead, a `frontier_stale_warning` is recorded, since the local copy may lag the default branch.

## v1 scope and limitations

- **In v1:** per-task routing (one model for the whole task), tier-up escalation between runs, the optional judge, and `routing.json`.
- **The runner is used in place (monorepo).** `/swe-auto` runs the in-repo `run-swe-headless.py`; there is no packaged/pinned installable yet, so the skill is used from within this repo. Packaging it for use outside the repo is a planned follow-up.
- **Triage model.** The configured `router_model` names the intended classifier; in v1 the triage is performed by the model driving the skill, and both are recorded. Dispatching triage to a distinct `router_model` is a follow-up.
- **Later (out of v1):** per-*phase* routing (plan with a frontier model, execute with a workhorse) and in-flight mid-run model switching.

## See also

- [vision.md](vision.md) - the north star and the sequence diagram this skill implements.
- [issue #123](https://github.com/aarora79/agentic-coding-harness-benchmarks/issues/123) - the feature spec.
- [/swe3 skill](../.claude/skills/swe3/SKILL.md) - what the selected model actually runs.
- [cost-per-task-methodology.md](cost-per-task-methodology.md) - the tiers and the two cost bases.
