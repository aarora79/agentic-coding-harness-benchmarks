# do-not-include

Benchmark runs kept as data points but held off the frontier, the charts and the vended `swe-router` model list.

## How the exclusion works

Every chart and frontier generator discovers models with a **shallow** scan of `swe-benchmark-data/`:

```python
for model_dir in sorted(p for p in data_dir.iterdir() if p.is_dir()):
    repo_dir = model_dir / harness / skill / repo
    if not repo_dir.is_dir():
        continue
```

A run nested one level deeper is invisible to that scan. `do-not-include` is itself seen as a directory, but `do-not-include/<harness>/<skill>/<repo>` never exists, so it is skipped and nothing downstream sees the runs beneath it. [build_vended_models.py](../../scripts/build_vended_models.py) globs `*/{harness}/{skill}/{dataset}/run-summary.json`, whose single `*` sits at the model level, so a nested path does not match there either.

Moving a model directory in or out of here is therefore the whole mechanism. There is no denylist in code to keep in sync.

**Do not "fix" this by deleting a model's `performance-summary.json` instead.** [plot_cost_quality.py](../../scripts/plot_cost_quality.py) falls back to the run-summary cost estimate when no performance summary exists, and to `0.0` when that is missing too -- so a model with no cost data plots as free and dominates the frontier. Nesting the run is the safe removal; deleting its cost is not.

## What is in here, and why

### qwen3.6-35b-fp8

Qwen3.6-35B-A3B in FP8 on a single L40S (`g6e.4xlarge`), running `/swe3` over `mcp-gateway-registry-v2`. Two harnesses sit side by side under this model, both scored by `openai.gpt-5.6-sol` at high reasoning effort against ref `1.23.0`:

| Harness | Run date | Scored | Mean score | Tokens/task | $/task at c=10 |
|---|---|--:|--:|--:|--:|
| [omp](qwen3.6-35b-fp8/omp/swe3/mcp-gateway-registry-v2/run-summary.json) | 2026-09-10 | 21/21 | 59.23 | 10,186,260 | $0.5555 |
| [codex](qwen3.6-35b-fp8/codex/swe3/mcp-gateway-registry-v2/run-summary.json) | 2026-09-11 | 21/21 | 61.45 | 4,850,652 | $0.2645 |

Neither run failed a task, and both produced 126/126 artifacts. codex scores 2.22 higher on half the tokens, so it costs half as much per task. The score gap is inside the noise: the paired per-task delta is +2.22 with sd 8.27, a 95% confidence interval of -1.32 to +5.75, and codex ahead on 11 of 21 tasks. Its lead concentrates in the `implementation` artifact (52.5 against 46.4) and in the trivial complexity tier (+6.08). It takes 1.68x the turns to get there (2,822 against 1,679), each turn shorter, which is why it replays less transcript.

**Read the token fields with the right convention before reusing these files.** The two harnesses report cache differently, and [token_accounting.py](../../scripts/token_accounting.py) resolves each one:

- **omp**: `cache_read + cache_write` is a partition of `input_tokens`, so `total = input + output`. The detector confirms the signature on 18 of 21 tasks. On the other three the server-side `cache_read` counter overshoots the client-side `input_tokens` by 0.1-0.6%, because the two numbers come from different places, and the 5% tolerance still lands on partition.
- **codex**: `DISJOINT_CACHE_AGENTS` declares the fields disjoint, so `total = input + output + cache_read`. Raw `input_tokens` therefore counts only fresh prompt tokens (3.65M across the run) where omp's counts the whole prompt (212.5M). Comparing those two fields directly is a units error; compare `total_tokens`.

Both runs price on the same hardware-derived rate as the charts: the cheapest blended $/token in [throughput/qwen3.6-35b-fp8/performance-summary.json](../../../self-hosted/vllm/benchmark-output/throughput/qwen3.6-35b-fp8/performance-summary.json), which is $0.0545/1M at concurrency 10 (6,556 prompt + 55 decode tok/s, $1.298/hr). That sweep's own `min_task_cost_blended_usd` of $0.5555 already is the omp figure, because its `task_input_tokens` of 10,120,244 came from the omp run. State the operating point with any of these numbers: at c=1 the same tokens cost $0.9672 (omp) and $0.4606 (codex), and the box is KV-bound from c=5 on, where `kv_cache_usage.peak` reaches 1.00.

Both are excluded on **cost basis**, not on quality. Two reasons, either of which alone is disqualifying:

1. **The throughput sweep is on a different hardware basis from the fleet.** Every self-hosted point on the published frontier is priced on the canonical `p5en.48xlarge` arm so the whole fleet shares one basis. This model was swept on `g6e.4xlarge` at $1.298/hr, and there is no p5en sweep for it. Charting it would put two hardware bases on one cost axis, which [plot_cost_quality.py](../../scripts/plot_cost_quality.py) explicitly warns against.
2. **The token counts are confounded with context window.** Both runs used `MAX_MODEL_LEN=262144` against the BF16 run's 200000. A larger window means less auto-compaction and a bigger transcript replayed per turn, and the omp run used roughly double the tokens per task (10.1M input vs 5.2M) for the same score. Whether that is the quantisation or the window is unresolved, and separating them needs an FP8 run at 200000 that is not planned.

The omp run cost **$0.556 per task** on its own g6e basis, against **$0.493** for BF16 on 4x L40S recomputed on the same task tokens. The cheaper hardware does not win, because the box sustains a quarter of the throughput (67 tok/s peak against 145) and the model spends twice the tokens. The codex run at $0.2645 clears that bar, and would beat the BF16 point that currently anchors the cheap end of the omp `/swe3` frontier ($0.2594 at 59.24). That comparison crosses both a hardware basis and a precision, so treat it as the case for running an FP8 sweep on p5en rather than a result.

The serving guide is [qwen3.6-35b-a3b-fp8.md](../../../self-hosted/vllm/models/qwen3.6-35b-a3b-fp8.md); the throughput measurement stays at `self-hosted/vllm/benchmark-output/throughput/qwen3.6-35b-fp8/`, where it is a valid record of what one L40S sustains and is unreachable from the charts while these runs are nested here.

**What they are good for.** They show the model runs at full 256K context on a $1.298/hr single-GPU box at the same quality as its BF16 parent, and they measure what the harness costs on top: same model, same box, same tasks, 2.1x the cost per task under omp. That is a useful answer for anyone sizing a single-developer or small-team deployment, where the hourly rate matters more than throughput-normalised cost per task.

### claude-haiku-5-5-resolved-as-haiku-4-5

A 21-task omp `/swe3` run over `mcp-gateway-registry-v2` on 2026-10-08, requested as `us.anthropic.claude-haiku-5-5` and **answered by Haiku 4.5 on every turn**. omp 18.1.15 had no Claude 5.5 entries in its catalog, and its `--model` is a fuzzy match, so it sent each request to the nearest model it knew, `us.anthropic.claude-haiku-4-5-20251001-v1:0`, and reported no error. Each task's `metrics.json` still records the model the harness asked for, because this run predates the `models_used` field. The `omp-stream.jsonl` files, kept locally and never committed, name Haiku 4.5 on all 21 tasks.

It is excluded on **identity**: the folder name says Haiku 5.5 and the model was Haiku 4.5. The real Haiku 5.5 run is at [claude-haiku-5-5](../claude-haiku-5-5/omp/swe3/mcp-gateway-registry-v2/run-summary.json).

| | Value |
|---|---|
| Tasks generated | 21 / 21 |
| Tasks judged | 13 / 21; judging stopped and was never resumed |
| Mean over the 13 judged | 55.58, one of them a 0 |
| Cost | $18.35, $0.87 a task, at omp 18.1.15's Haiku 4.5 rates ($1 / $5 / $0.10 / $1.25 per million tokens) |
| No run summary | it was never summarized |

The 0 is `consistent-csrf-across-toggle-endpoints`. omp wrote all six artifacts, then ended the session on `stopReason: toolUse`; the harness counted that as an error, retried, and the retry deleted the finished work before producing nothing.

Both faults are fixed in [#218](https://github.com/aarora79/agentic-coding-harness-benchmarks/pull/218): the harness now refuses a Bedrock id missing from omp's catalog, warms that catalog in each task's agent directory, fails any task whose replies name a different model (`error_model_mismatch`), and never retries a task with all six artifacts on disk. [omp-setup.md](../../../docs/omp-setup.md#model-resolution) explains the resolution behaviour.

**What it is good for.** It is the evidence for #218, and a second partial Haiku 4.5 sample: 55.58 over 13 tasks against the published 56.18 over 21.

### claude-haiku-5-5-misplaced-artifacts

The six artifacts Haiku 5.5 produced for `registration-admission-control-gate` in its published run on 2026-10-10. The prompt named the output directory `.../omp/swe3/mcp-gateway-registry-v2/registration-admission-control-gate/` 56 times; the model wrote everything to `.../omp/swe3/mcp-gateway-registry/registration-admission-control-gate/` instead, dropping the `-v2`. The harness found nothing in the right place and retried, and the retry stopped after 12 turns without writing anything.

The task counts as a **failure** in the published run (20 / 21 scored, mean 72.69). These files were never judged and must not be: scoring them would grant Haiku 5.5 a pass no other model could have earned by writing to the wrong folder. They are kept, outside the harness's scan, so the failure can be read. Unlike the other runs here they include the markdown artifacts and `patch.diff`, which the repo's `.gitignore` excludes by default; they were added explicitly. One hunk header in `patch.diff` quoted an example token from upstream's `terraform.tfvars.example`; it reads `<redacted upstream example value>` here. Git ignores hunk-header text, so the patch still applies at `v1.0.19`.

The same failure recurred on the cli/cli dataset on 2026-10-14, for two of the 21 tasks. Both sit under `omp/swe3/cli-cli-v1/`, the path the prompt named:

| Task | Where Haiku 5.5 wrote | Retry |
|---|---|---|
| `auth-clipboard-config-default` | `claude-haiku-5-5/claude-code/cli/auth-clipboard-config-default/`, the skill's generic model / harness / repo layout instead of the given path | Wrote to the same wrong folder |
| `skill-install-nested-discovery` | `claude-haiku-5-5/omp/swe3/cli-v1/skill-install-nested-discovery/`, dropping one `cli` | Wrote nothing; said the request named no `artifacts_dir` and asked for one |

Both count as **failures** in the published run (19 / 21 scored, mean 80.82), and neither was judged. A third misplaced write, `cli-ci-v1/repo-clone-ghe-ssh-ca-url/` on that task's first attempt, is not kept: the retry wrote to the right place and was scored. The secret scan found nothing to redact in these files.
