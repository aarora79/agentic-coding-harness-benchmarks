# Results -- /swe3 (single-agent skill)

Full benchmark results for the **`/swe3`** skill (the single-agent variant -- one agent loop, no sub-agent fan-out) on [agentic-community/mcp-gateway-registry](https://github.com/agentic-community/mcp-gateway-registry) at tag `1.24.4`: **5 tasks**, each scored 0-100 by an independent LLM judge (`codex exec`, `gpt-5.6-sol`, high reasoning effort). This is the **primary results view**; the multi-agent `/swe2` numbers live in [results-swe2.md](results-swe2.md).

> **These results are a live snapshot, not final** -- benchmarks are re-run frequently and methodology keeps improving. Treat the numbers as directional.

The headline numbers below are the **pi** harness (the single-agent shape a developer drives at the terminal); every model was also run under **Claude Code**, and the full head-to-head is in the [cross-harness comparison](agentic-coding-swe-comparison-swe3.md). Path 2 (open-weight on Bedrock via the LiteLLM proxy) is [fully implemented](../benchmarks/docs/path-open-weight-on-bedrock-litellm.md) but has no published run yet.

## Cost basis (read this first)

Two **non-comparable** cost bases share the cost column:

- **metered (Bedrock)** -- a hosted API's real per-token bill, summed over the run. Benefits from Bedrock prompt caching.
- **hardware-derived (self-hosted)** -- a rented GPU has no per-token bill, so cost is the model's blended `$/token` (instance `$/hr / measured tokens/sec` from the throughput sweep) times the tokens the run processed. Configurable pricing: p5en on-demand with a 0.35 placeholder discount (pay 65%), g6e 3-year Reserved Instance.

Compare **within** a hosting basis; treat cross-hosting dollars as order-of-magnitude, not exact. Full treatment: [cost-per-task-methodology.md](cost-per-task-methodology.md).

> [!IMPORTANT]
> **The p5en 35% discount is a PLACEHOLDER.** Self-hosted rates are configurable in [`self-hosted/vllm/pricing.json`](../self-hosted/vllm/pricing.json): g6e uses its **3-year RI rate**; p5en uses **on-demand with a 0.35 placeholder `discount`** (35% off = pay 65% -> $41.14/hr). Set your own committed/negotiated discount there and every self-hosted cost rescales linearly.

## The tasks

| # | Problem | Difficulty | Source |
|---|---------|-----------|--------|
| 1 | `remove-faiss` | Medium | Upstream [#1285](https://github.com/agentic-community/mcp-gateway-registry/issues/1285) / [#452](https://github.com/agentic-community/mcp-gateway-registry/issues/452) |
| 2 | `remove-efs-from-terraform-aws-ecs` | Medium | Upstream [#1286](https://github.com/agentic-community/mcp-gateway-registry/issues/1286) |
| 3 | `ssrf-hardening-outbound-url-validation` | Medium | Upstream [#1282](https://github.com/agentic-community/mcp-gateway-registry/issues/1282) |
| 4 | `migrate-ecs-env-vars-to-secrets-manager` | High | Upstream [#1134](https://github.com/agentic-community/mcp-gateway-registry/issues/1134) |
| 5 | `replace-keycloak-db-password-with-rds-iam` | High | Upstream [#1303](https://github.com/agentic-community/mcp-gateway-registry/issues/1303) |

## Cost vs. quality (Pareto frontier)

![Cost vs. quality scatter for the pi harness on /swe3, with the cost/quality frontier highlighted](images/cost-quality-pi-swe3.png)

Mean cost per task (x) against mean task score (y), one point per model, pi harness. Anthropic points are **real token-metered Bedrock bills**; self-hosted points are **hardware-derived** (see the cost basis above). Because the two bases are not comparable as raw dollars, the honest frontier is taken **within each hosting basis** -- but if you force a single cross-hosting frontier it runs **qwen3-coder-30b ($0.16 / 26.9, 2/5) -> qwen3.6-35b ($0.44 / 52.3) -> deepseek-v3.2 ($1.71 / 54.4) -> claude-sonnet-5 ($3.81 / 66.5) -> glm-5.2 ($5.98 / 70.8) -> claude-opus-5 ($8.28 / 75.7)**. Note this is the **pi-only** frontier: `qwen3.8-27b`, run under the omp harness (see below), sits at **$3.49 / 70.32** and would displace `claude-sonnet-5` from it entirely -- see [the combined chart](best-harness-selection.md), which merges the harnesses. The cheap open-weight models hold the low-to-mid frontier, and with self-hosted costs corrected (see the note below) glm-5.2 now joins the top of it just under claude-opus-5. Machine-readable frontier: [metrics/pareto-frontier-pi-swe3.json](metrics/pareto-frontier-pi-swe3.json). Regenerate with `uv run scripts/plot_cost_quality.py --harness pi --skill swe3` (add `--dark`) from `benchmarks/`.

## Results -- 5 tasks x models (pi harness)

All cells are task scores (0-100), the mean of the artifact totals per (task x model). These are **`/swe3` runs -- design *and* implementation** (six artifacts: the four design docs plus `patch.diff` + `implementation.md`), scored by the same judge. **Claude-Opus-5, Claude-Sonnet-5, Claude-Opus-4.8, and Claude-Haiku-4.5** are **Path 1** (Anthropic on Amazon Bedrock); every other row is **Path 3, self-hosted via vLLM**. Rows ordered by mean score. Bold = mean.

| Model | Hosting | `remove-faiss` | `remove-efs` | `ssrf` | `migrate-secrets` | `keycloak-iam` | **Mean⁵** | Completed |
|-------|---------|---:|---:|---:|---:|---:|---:|---:|
| claude-opus-5 | Bedrock | 79.6 | 88.8 | 69.6 | 74.2 | 66.4 | **75.72** | 5/5 |
| glm-5.2 | self-hosted | 67.4 | 77.8 | 72.6 | 69.6 | 66.4 | **70.76** | 5/5 |
| claude-sonnet-5 | Bedrock | 68.4 | 65.0 | 71.4 | 68.6 | 59.2 | **66.52** | 5/5 |
| qwen3.8-27b | self-hosted | 66.8 | 77.0 | 81.2 | 70.2 | 36.8 | **66.40** | 5/5 |
| claude-opus-4-8 | Bedrock | 68.0 | 59.8 | 59.6 | 68.0 | 48.0 | **60.68** | 5/5 |
| kimi-k2.7-code | self-hosted | 55.4 | 70.6 | 78.8 | 44.0 | 54.6 | **60.68** | 5/5 |
| grok-4.6 | Bedrock | 58.6 | 56.2 | 65.0 | 49.2 | 52.4 | **56.28** | 5/5 |
| nemotron-ultra-550b | self-hosted | 58.0 | 67.8 | 52.8 | 49.4 | 48.0 | **55.20** | 5/5 |
| deepseek-v3.2 | self-hosted | 47.6 | 64.8 | 57.4 | 52.4 | 50.0 | **54.44** | 5/5 |
| qwen3.6-35b | self-hosted | 0.0 ⁵ | 55.4 | 60.2 | 51.6 | 42.0 | **52.30** | 4/5 |
| devstral-2-123b | self-hosted | 45.4 | 48.6 | 54.2 | 52.0 | 38.0 | **47.64** | 5/5 |
| claude-haiku-4-5 | Bedrock | 40.8 | 54.2 | 54.6 | 47.4 | 38.6 | **47.12** | 5/5 |
| minimax-m2.5 | self-hosted | 35.0 | 57.0 | 48.6 | 50.2 | 34.6 | **45.08** | 5/5 |
| qwen3-coder-480b | self-hosted | 34.0 | 54.0 | 52.2 | 42.2 | 37.4 | **43.96** | 5/5 |
| gemma-4-31b | self-hosted | 38.8 | 42.0 | 57.2 | 39.4 | 37.4 | **42.96** | 5/5 |
| qwen3-coder-30b | self-hosted | 17.8 | 0.0 ⁵ | 36.0 | 0.0 ⁵ | 0.0 ⁵ | **26.90** | 2/5 |

⁵ **The Mean excludes any task that scored 0** -- a genuine model failure (missing/empty artifacts), an unresolved anomaly rather than a quality reading, left out of the average pending investigation. Per-task 0.0 cells are still shown so the failure is visible. Under pi/`swe3` the failures are **qwen3.6-35b on `remove-faiss`** (4/5) and **qwen3-coder-30b on `remove-efs`, `migrate-secrets`, and `keycloak-iam`** (2/5). qwen3-coder-30b is a coder-tuned model that burns its turn budget exploring/editing instead of completing the artifact chain -- the same harness-conformance instability seen under `/swe2`.

## Per-model leaderboard (pi harness, /swe3)

`$/task` = run cost / scored tasks. Bedrock rows are a real metered API bill; self-hosted rows are hardware-derived (instance $/hr / measured tokens/sec x the run's tokens).

| Rank | Model | Hosting | Mean score | $/task | Completed |
|-----:|-------|---------|-----------:|-------:|----------:|
| 1 | claude-opus-5 | Bedrock | **75.72** | $8.28† | 5/5 |
| 2 | glm-5.2 | self-hosted | **70.76** | $5.98 | 5/5 |
| 3 | claude-sonnet-5 | Bedrock | **66.52** | $3.81† | 5/5 |
| 4 | qwen3.8-27b | self-hosted | **66.40** | $3.53 | 5/5 |
| 5 | claude-opus-4-8 | Bedrock | **60.68** | $4.60† | 5/5 |
| 6 | kimi-k2.7-code | self-hosted | **60.68** | $5.52 | 5/5 |
| 7 | grok-4.6 | Bedrock | **56.28** | $13.34† | 5/5 |
| 8 | nemotron-ultra-550b | self-hosted | **55.20** | $3.91 | 5/5 |
| 9 | deepseek-v3.2 | self-hosted | **54.44** | $1.71 | 5/5 |
| 10 | qwen3.6-35b | self-hosted | **52.30** | $0.44 | 4/5 |
| 11 | devstral-2-123b | self-hosted | **47.64** | $0.76 | 5/5 |
| 12 | claude-haiku-4-5 | Bedrock | **47.12** | $0.64† | 5/5 |
| 13 | minimax-m2.5 | self-hosted | **45.08** | $0.47 | 5/5 |
| 14 | qwen3-coder-480b | self-hosted | **43.96** | $3.11 | 5/5 |
| 15 | gemma-4-31b | self-hosted | **42.96** | $1.04 | 5/5 |
| 16 | qwen3-coder-30b | self-hosted | **26.90** | $0.16 | 2/5 |

† Bedrock `$/task` is a real token-metered API bill, not hardware-derived. Machine-readable: [metrics/pareto-frontier-pi-swe3.json](metrics/pareto-frontier-pi-swe3.json) and [metrics/harness-delta-swe3.json](metrics/harness-delta-swe3.json).

## What the data says

- **claude-opus-5 tops quality (75.7), and under pi it is also the cost/latency leader for its tier** -- it beats its own Claude Code run on every axis (higher score, one-third the cost, half the wall-clock). See the harness comparison for why.
- **glm-5.2 is the best open-weight model (70.8)** and the self-hosted quality anchor -- at $5.98/task on a full 8x H200 box it sits on the combined frontier just below claude-opus-5 (opus-5 scores higher, at $8.28/task): a legitimate cheaper, lower-scoring frontier point, not a dominated one. Its standing swings with the configurable GPU discount (see cost basis note).
- **qwen3.6-35b is the value story:** 52.3 at ~$0.44/task on a single mid-range g6e node, one of several open-weight models now on the combined frontier alongside qwen3-coder-30b, deepseek-v3.2, and glm-5.2. Reliability asterisk: it completed 4/5 (failed `remove-faiss`), so it is a frontier point to watch, not a set-and-forget workhorse.
- **deepseek-v3.2 is the reliable self-hosted workhorse:** 54.4 at $1.71/task, 5/5, roughly three-quarters of glm-5.2's quality for under a third of the cost -- and non-dominated on the combined frontier.
- **Implementation is the hard part.** These `/swe3` runs score design *and* code; coder-tuned models (qwen3-coder-30b/480b) are the least reliable, burning the turn budget implementing instead of completing the artifact set -- qwen3-coder-30b failed 3 of 5.

For the full model-tier guidance (premium / open-weight / value / most-cost-effective, and which harness to use), see the **[cross-harness comparison](agentic-coding-swe-comparison-swe3.md)**.

## Quality by dimension

The single task score hides *how* a model earns it. The radar breaks the judge's scores out by **rubric criterion** (complete? correct? specific? risk-aware?) and by **artifact** (which deliverable is it best at?), read from each run's per-artifact `eval_scores`.

![Radar charts of quality by rubric criterion and by artifact, pi harness on /swe3](images/quality-radar-pi-swe3.png)

Every model dips hardest on **implementation** and **correctness** -- landing working code is the hard part. Regenerate with `uv run scripts/plot_quality_radar.py --harness pi --skill swe3` (add `--dark`) from `benchmarks/`.

## Also measured: qwen3.8-27b on the omp harness

Everything above is the **pi** harness. One model has been run under a fourth harness, [omp](https://omp.sh) (oh-my-pi), and is kept in its own section rather than mixed into the pi tables:

| Model | Harness | Mean score | Completed | Cost/task | Hardware |
|---|---|---:|---:|---:|---|
| `qwen3.8-27b` (FP8) | omp | **70.32** | 5/5 | $3.49 | 1x L40S (`g6e.4xlarge`) |

Two things make it worth reading next to the pi table above, with the harness caveat firmly attached:

- It matches `glm-5.2` (70.76) for **42% less** per task, on a **single 46 GB GPU** rather than 8x H200, and it beats `claude-sonnet-5` (66.52) at slightly lower cost.
- It completed **5/5** with all six artifacts. Its predecessor `qwen3.6-35b` scores 52.30 over 4/5 -- the task it failed outright (`remove-faiss`) is one qwen3.8 completed and scored 70.0 on.

**Do not read this as a like-for-like row in the pi leaderboard.** The harness is a real variable here: on `remove-faiss`, `claude-opus-5` scores 79.6 under pi and 69.6 under Claude Code, a 10-point swing on one model and one task. Until qwen3.8-27b is also run under pi, its 70.32 is a statement about *omp plus qwen3.8*, not about the model in isolation. Full per-harness detail: [harness-omp-swe3.md](harness-omp-swe3.md).

Its quality run used a **200K context window**; the throughput/cost sweep for the same model was measured at **65K**, because one L40S cannot serve a long window and useful concurrency at once. See [its model guide](../self-hosted/vllm/models/qwen3.8-27b.md).

## Hardware

- **Bedrock (Path 1):** claude-opus-5, claude-sonnet-5, claude-opus-4-8, claude-haiku-4-5 -- no self-hosting; `$/task` is a real metered API bill.
- **8x H200 (`p5en.48xlarge`):** glm-5.2, kimi-k2.7-code, nemotron-ultra-550b, deepseek-v3.2, qwen3-coder-480b (TP=4), devstral-2-123b (TP=4).
- **`g6e.12xlarge` (4x L40S):** qwen3.6-35b, minimax-m2.5, gemma-4-31b, qwen3-coder-30b.

All self-hosted via vLLM. Per-model serving guides: [self-hosted/vllm/models/](../self-hosted/vllm/models/). Instance rates: [self-hosted/vllm/pricing.json](../self-hosted/vllm/pricing.json) (us-east-1; p5en on-demand with a 0.35 placeholder `discount` = pay 65% -> $41.14/hr, g6e 3-year RI $4.533/hr; both configurable).

## Reproduce

```bash
cd benchmarks
uv run python scripts/run-swe-headless.py --agent pi --skill swe3 --config config/runner.yaml --model <model> --dataset dataset/mcp-gateway-registry.yaml
uv run python scripts/gen_swe_comparison.py --skill swe3
uv run python scripts/plot_cost_quality.py --harness pi --skill swe3
uv run python scripts/plot_harness_delta.py --skill swe3
```
