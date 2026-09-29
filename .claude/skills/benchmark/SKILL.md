---
name: benchmark
description: "Run one end-to-end SWE benchmark of an LLM on real coding tasks, driven by any supported coding agent (omp, Claude Code, pi, codex, or kiro-cli) on any of the hosting paths (Anthropic on Bedrock, open-weight on Bedrock via the LiteLLM proxy, a self-hosted vLLM server, or any OpenAI/Anthropic-compatible endpoint). Drives the full flow: pre-flight checks including repository reachability, clearing stale artifact folders, running the harness over a dataset, and scoring the artifacts with the codex judge. Use when the user wants to benchmark a model, run the SWE harness end to end, score a model on a dataset, or compare models on coding tasks, AND the machine is already wired up. For a first run on new infrastructure (their own gateway, their own private repos) use onboard-benchmark instead. Wraps benchmarks/scripts/run-e2e-benchmark.sh and tells the user how to watch each step."
license: Apache-2.0
metadata:
  author: Amit Arora
  version: "1.0"
---

# Benchmark Skill

Use this skill to run **one complete SWE benchmark end to end** for a chosen model: bring up the backing service, pre-flight checks, the harness run over a dataset, and scoring with the judge. It is the interactive front end to [`benchmarks/scripts/run-e2e-benchmark.sh`](../../../benchmarks/scripts/run-e2e-benchmark.sh); it collects three inputs, surfaces the exact command to watch each long-running step, and fails loudly with an actionable message the moment anything is wrong. For the **vllm** path it also manages the server (starts it on the requested model, stopping any other model first) and the DuckDB metrics collector (starts it before the run, stops it and archives the snapshot after).

**If this is the first run on this infrastructure, use [`onboard-benchmark`](../onboard-benchmark/SKILL.md) instead.** That skill covers what this one assumes is already true: a machine that reaches both the model endpoint and the code host, an agent and a judge proven against a real model call, credentials for private repositories, and a dataset of the user's own tasks. This skill starts from a working setup and runs one model through it.

All the real logic lives in the shell script and its Python helpers ([`preflight_check.py`](../../../benchmarks/scripts/preflight_check.py), [`run-swe-headless.py`](../../../benchmarks/scripts/run-swe-headless.py), [`codex_judge.py`](../../../benchmarks/scripts/codex_judge.py)). This skill orchestrates them and reports. The concepts and the per-path setup are documented in [`benchmarks/README.md`](../../../benchmarks/README.md) and [`benchmarks/docs/`](../../../benchmarks/docs/); the full manual run-book is [`benchmarks/docs/end-to-end-self-hosted-run.md`](../../../benchmarks/docs/end-to-end-self-hosted-run.md).

## The three inputs

Collect these three, in order. Do not guess -- ask if any is missing.

1. **provider** -- one of:
   - `bedrock` -- Anthropic models (Claude Opus/Sonnet/Haiku) directly on Amazon Bedrock.
   - `litellm` -- open-weight models on Amazon Bedrock through the LiteLLM mantle proxy (Kimi, Qwen, DeepSeek, Mistral, ...).
   - `vllm` -- a model you self-host on a local vLLM server (`127.0.0.1:8000`).
2. **model** -- the model id / served-model-name. Examples: `us.anthropic.claude-opus-4-8` (bedrock), `moonshotai.kimi-k2-thinking` (litellm), `qwen3-coder-30b` (vllm).
3. **dataset** -- a dataset YAML under `benchmarks/dataset/`. Default to **`dataset/mcp-gateway-registry-v2.yaml`**, the 21-task set behind the published results, whose tasks are each pinned to the release before their upstream fix and spread across four complexity tiers. `dataset/mcp-gateway-registry.yaml` is the older 5-task v1 set, kept for comparison with earlier runs. Suggest `dataset/hello-world.yaml` for a quick sanity check, and `dataset/workshop-template.yaml` as the starting point when the user wants to benchmark their **own** repositories (then use the [`onboard-benchmark`](../onboard-benchmark/SKILL.md) skill, not this one).

   **Scores from different datasets never merge.** Different tasks, refs and difficulty mixes mean separate tables.

Two optional inputs:

4. **agent** -- which coding agent drives the task, passed as `--agent`. The task definition, the six artifacts, the metrics file and the judge are identical for all of them, so a model's score is comparable across agents; only the binary and its invocation change.

   | `--agent` | What it is | Providers it supports |
   |---|---|---|
   | `omp` | [oh-my-pi](../../../docs/omp-setup.md), a fork of pi. **Produced this repository's headline results.** | `endpoint` (vllm/litellm) and `bedrock` |
   | `claude` | Claude Code, `claude -p`. The default. | every provider |
   | `pi` | the pi coding agent, `pi -p --mode json` | `endpoint` and `bedrock` (it bundles the AWS SDK bedrock-runtime client) |
   | `codex` | OpenAI Codex, `codex exec --json` | `endpoint` (via `OPENAI_BASE_URL` / `OPENAI_API_KEY`) and `bedrock` |
   | `strands` | [Strands Agents SDK](../../../docs/strands-setup.md). No CLI binary: it runs in-process from `strands_agent_runner.py` | `endpoint` and `bedrock` |
   | `kiro` | [kiro-cli](../../../docs/kiro-cli-setup.md), which drives Kiro's own managed models | `kiro` only, and it forces `--provider kiro` for you |

   `claude` remains the default, so only ask if the user brings it up. Two things worth knowing if they do: `omp` is what the published frontier was measured with, and only the `claude` agent gets the `--stream` live trace (the others emit their own event stream or plain text).

   **`--agent codex` on the `vllm` path needs a Responses-safe tool parser.** codex 0.153.4 speaks only the Responses API (it removed the chat-completions wire), and seven of vLLM 0.29.0's tool parsers read the nested chat-completions tool shape and crash on the flat Responses shape: `minicpm5xml`, `dots`, `hy_v3`, `hy_v4`, `rust`, `step3`, `step3p5`. Against one of those, tool extraction aborts, the stream ends with no `response.completed`, and codex retries every request five times before failing the turn. `qwen3_coder` and `hermes` work, verified with `qwen3.6-35b-fp8` at a 262,144-token window. Check the parser in the model guide before choosing this agent (issue #183).

   **`--agent codex` makes the same tool produce and score the artifacts.** The judge is `codex exec` too (Step 4), on a separate call. That is not automatically wrong, since the judge runs over the artifacts on disk with its own model and prompt, but pick a judge model different from the one under test or the run marks its own homework.

5. **skill** -- which SWE skill runs, passed as `--skill`. Default **`swe3`**, the single-agent variant: all work happens inline in the main loop with no subagent fan-out, so its token and cost accounting is complete and comparable across harnesses, including agents that have no subagent mechanism at all. `swe2` is the older multi-agent variant that fans out to parallel `Task` subagents; same six artifacts, but its main-agent usage undercounts subagent tokens. Both land in sibling folders and never overwrite each other.

## Workflow

1. **Gather the three inputs** -- provider, model, dataset. Confirm them back to the user.
2. **Bring up / confirm the backing service** for the chosen path. For **vllm**: check the HF token, then (re)start the vLLM server on the requested model -- stopping any other model first -- using the model guide's serve command at its largest context window; **check the served window against the 200K recommended floor** (>=200K proceed; somewhat below, e.g. 128K, warn and confirm; a tiny ~16K window is not benchmarkable and stops the run); then start the DuckDB collector. For litellm/bedrock: confirm the proxy/credentials.
3. **Dry-run the pre-flight** so the user sees what will happen before anything runs.
4. **Run the orchestrator**, streaming its output, and tell the user what to tail.
5. **Wrap up and report**: (vllm) stop the collector and archive its DuckDB snapshot tagged with model/scope/timestamp; run `summarize_run.py` to write `run-summary.json` (machine-readable, for charting) and `run-summary.md` into the run's `{model-slug}/{harness}/{skill}/{scope}/` folder; then report where the results landed.

Keep the user informed at every step: before each long-running command, print it verbatim and give the tail/status command to watch it.

---

## Step 1 - Gather and confirm the three inputs

Ask for provider, model, and dataset if the user did not already give them. Then restate the plan and the folder the results will land in:

> I will run an end-to-end benchmark:
> - provider: **{provider}**
> - model: **{model}**
> - dataset: **{dataset}**
> - agent: **{agent}** / skill: **{skill}**
>
> Results will land under `benchmarks/swe-benchmark-data/{model-slug}/{harness}/{skill}/{scope}/<task>/`. Proceed?

Wait for confirmation before running anything.

## Step 2 - Confirm (and for vllm, bring up) the backing service

The orchestrator re-checks the service and fails loudly, but for the **vllm** path this skill actively brings the server up on the requested model. Handle the path the user chose:

### provider = vllm -- ensure the server is serving `{model}`

Do these in order. Do not skip the HF-token check; a missing token is the most common cause of a stalled first download.

**2a. HuggingFace token must be available BEFORE starting vLLM.** `vllm-serve.sh` resolves a token from `$HF_TOKEN`, else a `.hf_token` file in the repo root, the `self-hosted/vllm/` dir, or `$HOME`. Check that at least one is present:

```bash
cd ~/agentic-coding-harness-benchmarks
if [ -n "${HF_TOKEN:-}" ] || [ -s .hf_token ] || [ -s self-hosted/vllm/.hf_token ] || [ -s "$HOME/.hf_token" ]; then
  echo "HF token available"
else
  echo "NO HF TOKEN"
fi
```

If it prints `NO HF TOKEN`, **stop and ask the user to provide one** before continuing -- e.g. write it to `.hf_token` in the repo root (the file is gitignored):

> No HuggingFace token found. vLLM needs one to download `{model}` at a usable speed (without it, HF's anonymous rate limits can make a 60-160 GB download crawl or stall). Please provide a token: write it to `.hf_token` in the repo root, or export `HF_TOKEN`. Let me know once it's set and I'll continue.

Do not print or echo the token value. **Note:** the serve script reads `.hf_token` (with an underscore). If the user only has a `.hftoken` file, tell them to rename it to `.hf_token` or export `HF_TOKEN`, because the script will not pick up `.hftoken`.

**2b. Check what vLLM is currently serving (if anything):**

```bash
curl -s http://127.0.0.1:8000/v1/models | python3 -c "import sys,json; print([m['id'] for m in json.load(sys.stdin).get('data',[])])" 2>/dev/null || echo "not running"
```

- If it already serves `{model}` -> nothing to do, move on.
- If it serves a **different** model -> stop it first, then start the requested one:
  ```bash
  cd self-hosted/vllm/scripts && ./vllm-serve.sh --stop
  ```
- If it is **not running** -> start the requested one.

**2c. Start vLLM on `{model}` using the parameters from its model guide.** Read `self-hosted/vllm/models/{model}.md` (e.g. `qwen3.6-35b-a3b.md`) and use the serve command it documents, choosing the **largest practical context window** that guide endorses (the "Serve it" block's `MAX_MODEL_LEN`; do not exceed the guide's recommended max, since a bigger window can fail to boot at useful concurrency). Copy that guide's `MODEL`, `SERVED_NAME`, `TOOL_PARSER`, and `MAX_MODEL_LEN` exactly. `vllm-serve.sh` always tees its log to `self-hosted/vllm/logs/vllm-serve.log`.

```bash
cd self-hosted/vllm/scripts
# Values below come straight from self-hosted/vllm/models/{model}.md -- do not invent them.
MODEL="<HF repo from the guide>" \
SERVED_NAME="{model}" \
TP=4 \
PORT=8000 \
MAX_MODEL_LEN="<largest window the guide endorses>" \
GPU_MEM_UTIL=0.90 \
TOOL_PARSER="<parser from the guide>" \
  ./vllm-serve.sh
# The launcher blocks until the server is ready (first download can take minutes).
# Watch progress in another terminal:  tail -f self-hosted/vllm/logs/vllm-serve.log
```

If there is no guide for `{model}` under `self-hosted/vllm/models/`, tell the user and ask for the HF repo id, tool-call parser, and desired context window rather than guessing.

**2d. Context-window gate -- 200K recommended; below it, WARN and confirm; a tiny window fails outright.** Agentic coding tasks on real repositories routinely need 100K-250K input tokens in a single request (the SWE skill prompt alone is ~12K, and reading repo files pushes far higher). **200K is the recommended floor.** A window well below that risks overflowing on turn 1 (before auto-compaction can help, since the first prompt already does not fit). This is a node/VRAM limitation, not a model-quality signal. Note this is a guideline, not a hard law: Kimi-K2.7-Code completed 4 of 5 tasks at a **128K** window, so a window somewhat under 200K can still work when the tasks fit -- but a tiny window (e.g. ~16K, all a 79.6B model fits on a 4x L40S node) cannot hold even the first prompt and every task fails.

After the server reports ready, read the window it actually booted with:

```bash
WINDOW="$(curl -s -m 5 http://127.0.0.1:8000/v1/models \
  | python3 -c 'import sys,json; d=json.load(sys.stdin).get("data",[]); print(next((m.get("max_model_len") for m in d if m.get("max_model_len")), 0))' 2>/dev/null || echo 0)"
echo "served context window: $WINDOW"
if [ "$WINDOW" -lt 200000 ]; then echo "BELOW 200K RECOMMENDED FLOOR"; fi
```

Decide by how far below 200K it is:

- **>= 200000:** proceed to Step 2e, no caveat.
- **Between ~100000 and 200000 (e.g. Kimi's 128K):** **warn the user and ask them to confirm** before proceeding. Do not silently run, and do not hard-stop -- state the window, note the overflow risk on the largest tasks, and let the user decide. Example: "`{model}` booted at a {WINDOW}-token window, below the 200K recommended floor. Sub-200K can still complete these tasks (Kimi did at 128K) but larger tasks may overflow. Proceed anyway?"
- **Far below (roughly < ~64000, and certainly ~16K):** treat as not benchmarkable -- the SWE skill prompt plus a single file read will not fit, so every task fails on turn 1. Do not run; tell the user, e.g.:

  > `{model}` booted at only a {WINDOW}-token context window on this node -- too small for agentic coding, where the prompt alone plus one file read exceeds the window and every task fails on turn 1. This is a VRAM limitation of the current machine, not the model. Options: benchmark a model that fits a larger window on this node (e.g. `qwen3.6-35b` or `qwen3-coder-30b`), or serve `{model}` on a larger-VRAM node (see its model guide for the required instance).

  Stop the collector if it was already started, leave the notes for the user, and do not proceed to Step 3. (This is why Step 2c picks the *largest* window the guide endorses -- if even that is tiny, the model is not benchmarkable here.)

**2e. Start the DuckDB metrics collector** so a GPU time series is captured for the whole run (it is stopped and the snapshot archived in Step 5):

```bash
cd self-hosted/vllm/scripts && ./vllm-metrics.sh start && ./vllm-metrics.sh status
```

### provider = litellm -- the LiteLLM proxy must be up on `127.0.0.1:4000`

```bash
cd benchmarks && ./scripts/bedrock-mantle-proxy.sh --status
# if not running:
./scripts/bedrock-mantle-proxy.sh
tail -f benchmarks/.litellm.log
```

### provider = bedrock -- confirm AWS credentials

```bash
aws sts get-caller-identity
```

## Step 3 - Pre-flight (see what will happen first)

**3a. Two CLIs must be installed: the chosen agent, and the judge.** The harness runs the agent binary to produce the artifacts, and the judge runs `codex exec` to score them. The agent binary follows `{agent}`: `claude -p`, `omp -p --mode json`, `pi -p --mode json`, `codex exec --json`, or `kiro-cli chat --no-interactive`. Confirm the one in play, plus codex:

`--agent strands` is the exception: it has no binary, because it runs in-process from the Strands Agents SDK. It needs an optional uv dependency group instead, and the orchestrator installs it (`uv sync --group strands`) when it is missing. See [docs/strands-setup.md](../../../docs/strands-setup.md). Only codex needs to be on PATH for that agent.

```bash
command -v {agent-binary} && command -v codex || echo "MISSING a required CLI"
```

If the agent binary is missing, stop -- the harness cannot run. `omp` is the one most often absent, because the machine setup installs it only behind `--with-omp`; its installer drops the binary in `~/.local/bin`, so a missing `omp` is sometimes just a `PATH` problem. If `codex` is missing, the run can still proceed with `--skip-judge` (score later once codex is installed). The orchestrator re-checks both and fails loudly.

State this expectation to the user **loudly**, because the skill does not configure it: both CLIs must already be authenticated against **Amazon Bedrock** on this machine. The codex judge *always* calls Bedrock for its scoring model; on `--provider bedrock`, `claude` calls Bedrock too (on the litellm/vllm paths `claude` is pointed at the proxy/local server instead, but the judge still uses Bedrock). If either CLI is unconfigured or pointed elsewhere, the run or the scoring will fail.

> Heads-up: this benchmark assumes `claude` and `codex` on this machine are already wired to Amazon Bedrock (credentials/region). The judge always calls Bedrock; on the bedrock path claude does too. I do not configure them -- if either is pointed elsewhere, the run or scoring will fail.

Working AWS credentials are **not** sufficient: an unconfigured `codex` ignores them and 401s against `api.openai.com`. Prove the judge end to end before a long run, because the alternative is discovering it after the harness has finished:

```bash
codex exec --skip-git-repo-check "Reply with exactly: JUDGE OK"
```

If it fails, [benchmarks/docs/agent-cli-bedrock-setup.md](../../../benchmarks/docs/agent-cli-bedrock-setup.md) has the fix (codex ships a native `amazon-bedrock` provider; no proxy or bearer token needed).

**3b. Every repository in the dataset must be reachable at its pinned ref.** The harness clones per task, so a bad credential or a ref that does not exist would otherwise fail once per task, hours into a run, as an opaque `git clone failed`. This check uses `git ls-remote`, so it transfers no objects and costs seconds:

```bash
cd benchmarks
uv run python scripts/preflight_check.py --dataset {dataset} --check-repos
```

It separates a missing credential, a rejected token, an untrusted internal CA, an unresolvable host and a missing tag, and names the fix for each. The orchestrator runs it too, but running it here means the user sees it before anything long starts. It matters most on a **private or enterprise-hosted** repository, where the usual cause is a credential helper that is not recording the token or an internal CA that git does not trust; [docs/benchmark-your-own-repo.md](../../../docs/benchmark-your-own-repo.md) has the setup.

**3c. A real gateway token belongs in the environment, not the config.** If `{provider}` routes through an endpoint that needs genuine credentials rather than the throwaway `local` a self-hosted vLLM server ignores, set `api_key_env` in `config/runner.yaml` (or pass `--api-key-env`) to name the variable holding it. A named variable that is unset fails at config load rather than hours later inside the agent. Never print the value; refer to the variable name.

**3d.** Show the user which artifact folders already exist for this model+dataset (a pre-existing folder makes the headless run stall on its overwrite prompt). This is a read-only check:

```bash
uv run python scripts/preflight_check.py --dataset {dataset} --model {model} \
    --agent {agent} --skill {skill} --check
```

- Exit 0: nothing exists, safe to run.
- Exit 2: folders exist. Ask the user whether to **clear** them (a fresh run) or **keep** them (rename to preserve the prior run). If clearing, the orchestrator does it automatically when passed `--yes`; or clear explicitly:
  ```bash
  uv run python scripts/preflight_check.py --dataset {dataset} --model {model} \
      --agent {agent} --skill {skill} --clear
  ```

Pass `--agent` and `--skill` so the check targets the same tree the run will write. Omitting them checks the default `claude`/`swe3` folder, which is the wrong one whenever the user chose otherwise.

## Step 4 - Run the orchestrator

Run the end-to-end script from `benchmarks/`. It re-runs every pre-flight check (fail-loud), runs the harness with `--stream`, then scores with the judge. Pass `--yes` only after the user has agreed to clear any existing folders in Step 3.

```bash
cd benchmarks
./scripts/run-e2e-benchmark.sh --provider {provider} --model {model} --dataset {dataset} \
    [--agent claude|pi|omp|codex|strands|kiro] [--skill swe3|swe2] [--yes] [--count N] [--skip-judge]
```

Tell the user, before it runs:

- The harness streams a live trace; add `--count 1` to try a single task first on a big dataset.
- **vllm path** -- watch the server and GPU metrics in another terminal:
  ```bash
  tail -f self-hosted/vllm/logs/vllm-serve.log
  cd self-hosted/vllm && uv run python -m clients.build_dashboard && echo "open benchmark-output/dashboard.html"
  ```
- **litellm path** -- watch the proxy: `tail -f benchmarks/.litellm.log`
- The judge (`codex exec`) buffers output and prints only its final message per folder, so a few minutes each at high effort is normal; it is working, not hung.

If the run is long, remind the user they can run only the harness now and score later with `--skip-judge`, then:
```bash
cd benchmarks/scripts && uv run python codex_judge.py --recursive --no-overwrite --folder ../swe-benchmark-data/{model-slug}/{harness}/{skill}/{scope}
```

**For a MULTI-MODEL batch, do not hand-write a scoring watcher.** Use [scripts/run-multi-model-benchmark.sh](../../../benchmarks/scripts/run-multi-model-benchmark.sh) with `--judge-mode async`: it judges each model in the background while the next one generates. The judge is a Bedrock call and uses no GPU, so the two overlap for free -- roughly 50 minutes per 21-task model that would otherwise be GPU-idle time (inline) or a serial tail after the batch (`--skip-judge`). It keeps judge, summarize and commit together, waits for outstanding judging before reporting `ALL DONE`, and exits non-zero naming any model whose judging failed.

```bash
cd benchmarks
./scripts/run-multi-model-benchmark.sh {model} {model} --agent {agent} --skill {skill} --judge-mode async
```

`--judge-mode async` requires a working `codex`; the script proves it with a live call before serving anything, so a misconfigured judge fails in seconds rather than hours later inside a background job.

## Step 5 - Wrap up (stop the collector, archive the DuckDB snapshot, write the run summary) and report

**5a. (vllm path) Stop the DuckDB metrics collector** now that the run is done, so it stops appending to the live database:

```bash
cd self-hosted/vllm/scripts && ./vllm-metrics.sh stop
```

**5b. (vllm path) Archive the DuckDB snapshot** by renaming the live database to one tagged with the model, dataset/task scope, and a timestamp -- so it is preserved for this run and the next run starts from a fresh, empty database. The live file is `self-hosted/vllm/benchmark-output/vllm-metrics.duckdb`. Build the timestamp from the actual current time (do not hardcode it), and use the dataset's repo name as the task scope:

```bash
cd self-hosted/vllm/benchmark-output
TS="$(date -u +%Y%m%dT%H%M%SZ)"
# {model-slug} = the model folder name; {scope} = the dataset repo (e.g. mcp-gateway-registry)
mv vllm-metrics.duckdb "vllm-metrics_{model-slug}_{scope}_${TS}.duckdb"
echo "archived snapshot: vllm-metrics_{model-slug}_{scope}_${TS}.duckdb"
```

If the collector was never started (or this is not the vllm path), skip 5a/5b. If you want a dashboard from the archived snapshot, render it before or after the rename by pointing `--db` at the file:

```bash
cd self-hosted/vllm && uv run python -m clients.build_dashboard \
  --db benchmark-output/vllm-metrics_{model-slug}_{scope}_{timestamp}.duckdb \
  --output benchmark-output/dashboard_{model-slug}_{scope}_{timestamp}.html
```

**5c. Write the run summary** with the summarizer script, which reads the run's per-task `metrics.json` + `eval.json` and writes **both** a machine-readable `run-summary.json` (for later charting/aggregation) and a human-readable `run-summary.md`, into `benchmarks/swe-benchmark-data/{model-slug}/{harness}/{skill}/{scope}/`. Do this on **every** path (bedrock/litellm/vllm), after scoring. Do not hand-write the summary -- the script computes the failed-task-excluded mean, the serving block, and the per-task table consistently:

```bash
cd benchmarks
uv run python scripts/summarize_run.py \
  --folder swe-benchmark-data/{model-slug}/{harness}/{skill}/{scope} --run-date "$(date -u +%Y-%m-%d)"
```

The script treats a 0-score task as a model failure (missing artifacts) and excludes it from the headline mean, matching the leaderboard convention, while still listing it. Read the resulting `run-summary.md` back to the user; if a task failed, its 0 and the `failed_tasks` list make that visible -- do not present a partial run as a clean sweep.

The `run-summary.json` carries the structured data (per-task scores/turns/cost, the `serving` block with instance_type / tensor_parallel_size / precision / context_window, mean_task_score_excl_failed, failed_tasks) so runs can be charted or aggregated later without re-parsing every task folder.

**5d. Report** where the results are and what they contain:

- Point the user at the `run-summary.md` you just wrote first.
- Each `benchmarks/swe-benchmark-data/{model-slug}/{harness}/{skill}/{scope}/<task>/` holds the four design artifacts plus the implementation artifact (`patch.diff` + `implementation.md`), `metrics.json` (cost + any vLLM server metrics), and `eval.json` (quality scores; `task_score` is the mean of the five artifact totals).
- The same task run by another model lands under a sibling top-level `{model-slug}/` folder, directly comparable.
- Suggest inspecting one result:
  ```bash
  cat benchmarks/swe-benchmark-data/{model-slug}/{harness}/{skill}/{scope}/<task>/eval.json
  ```
- If a DuckDB snapshot was archived (5b), point the user at it.

## Notes

- **This skill manages the vLLM server and the DuckDB collector for the `vllm` path** (Step 2 brings the server up on the requested model, stopping any other model first; Step 5 stops the collector and archives its snapshot). It does **not** manage the LiteLLM proxy -- that is a long-lived service with its own script (`bedrock-mantle-proxy.sh`); the skill only checks it is up.
- **provider = bedrock is Anthropic-only.** For non-Anthropic Bedrock models use `litellm`. The orchestrator warns if a non-Anthropic id is passed with `bedrock`.
- **The model slug is not always the model id.** For a Bedrock inference profile the folder name drops the `us.anthropic.` prefix and any `[...]` suffix (e.g. `us.anthropic.claude-opus-4-8` -> `claude-opus-4-8`); a served name like `qwen3-coder-30b` is unchanged. The pre-flight helper and the orchestrator both compute this the same way the harness does.
- **Model, harness and skill are each their own folder level**, so a pi run never overwrites a Claude Code one and `swe3` never overwrites `swe2`. The `{scope}` level below them is the repository name, unless the dataset sets `output_scope`. Getting this wrong points the judge and the summarizer at a tree the harness never wrote to.
- **`context_window` is required for a model behind a custom base URL.** Claude Code and omp cannot detect the window of a custom model, so without it the conversation grows until the endpoint rejects the request, and the client retries that rejection forever. The orchestrator reads it from `/v1/models` automatically on the `vllm` path; on `litellm` or any other gateway, set it to the underlying model's window. Leave it unset for Anthropic on Bedrock, where the window is already known.
- **An endpoint needing a real API key should read it from the environment** via `api_key_env`, never a literal in `config/runner.yaml`. Never echo the value.
- Every script takes `--help`.
