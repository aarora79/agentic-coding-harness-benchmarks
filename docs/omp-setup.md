# omp (oh-my-pi) setup

Install and configuration reference for **[oh-my-pi](https://github.com/can1357/oh-my-pi)** (`omp`, [omp.sh](https://omp.sh)) as a coding-agent harness for this benchmark. omp is a fork of the [pi coding agent](https://github.com/earendil-works/pi-coding-agent) and speaks the same JSON-lines event stream, so the harness reuses pi's result parser. It differs in three ways the harness handles for you, listed under [How the harness drives it](#how-the-harness-drives-it).

Pick it per run with `--agent omp`. Results land under `swe-benchmark-data/<model>/omp/<skill>/<repo>/<task>/`, separate from every other harness.

## Install

```bash
curl -fsSL https://omp.sh/install | sh
omp --version
```

The installer puts a single binary in `~/.local/bin/omp` (override with `PI_INSTALL_DIR`). Add that directory to `PATH` if it is not there already -- the pre-flight check fails with `omp CLI not found on PATH` otherwise.

Two install modes, chosen for you:

- **Prebuilt binary** (the default when `bun` is absent). Downloads `omp-linux-x64` from the GitHub release, ~186 MB, and runs `omp --version` to prove the binary starts before reporting success.
- **From source via bun** (`--source`, or automatic when a matching-architecture `bun` >= 1.3.14 is already installed). Add `--binary` to force the prebuilt path.

To pin a version, pass `--ref <tag>`. The results in this repo were produced with **v18.0.10**. A Bedrock model newer than your omp build needs a newer omp: run `omp update`, and read [Model resolution](#model-resolution) for why an old build fails without an error.

If you would rather not pipe a remote script to a shell, read it first:

```bash
curl -fsSL https://omp.sh/install -o /tmp/omp-install.sh
less /tmp/omp-install.sh
sh /tmp/omp-install.sh
```

### Under a systemd unit

A `systemd --user` unit starts with a minimal `PATH` that excludes `~/.local/bin`, so `omp` and `uv` both disappear and the run dies at pre-flight. Export a `PATH` inside any script you launch that way:

```bash
export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin"
```

## Authentication

omp reaches models two ways, matching the harness's `provider` setting:

- **`--provider vllm` / `endpoint`** -- an OpenAI-compatible base URL. The harness writes the provider block for you (see below); no credentials beyond the endpoint's own API key, which is usually the throwaway `local`.
- **`--provider bedrock`** -- Amazon Bedrock, as `amazon-bedrock/<wire model id>`. omp resolves AWS credentials itself, including an EC2 instance role.

On the Bedrock path the harness logs `could not resolve AWS credentials via 'aws configure export-credentials'`. That warning is harmless when an instance role is present: omp finds the role on its own. Confirm by watching the artifacts appear, or `tail` the event stream.

## How the harness drives it

```bash
omp -p --mode json --no-session --auto-approve --max-time=1800 \
    --model <provider>/<model-id> -- "<SKILL.md + task prompt>"
```

Three differences from pi that the harness papers over:

1. **Config is YAML, not JSON.** pi reads `models.json`; omp reads `models.yml` (custom providers) and `config.yml` (settings). The harness writes both per run into a private agent directory pinned by `PI_CODING_AGENT_DIR`, which omp inherits from pi, so a run never touches a developer's global `~/.omp`.
2. **No `--skill` flag.** omp's `--skills` is a glob filter over discovered skills, not a path, so the harness inlines the whole `SKILL.md` ahead of the task prompt the way it does for kiro-cli. The trailing `--` ends option parsing, which matters because the inlined SKILL.md opens with `---` (YAML frontmatter) that omp would otherwise reject as a flag.
3. **stdin must be closed.** omp treats an inherited stdin as a piped prompt and blocks waiting for EOF, ignoring the positional prompt. The harness passes `stdin=DEVNULL`. Without it a task hangs until the timeout with no output.

### Compaction

omp expresses its compaction trigger as an absolute `compaction.thresholdTokens`, where pi uses `reserveTokens`. The harness converts, reserving a full response plus ~8K of headroom. Without it omp fills the context window to within its default reserve and one capped response overflows, killing the run before the last artifacts are written.

### The wall-clock cap

omp has no turn cap, so a model that finishes the work and keeps emitting tokens would run until the harness timeout and then burn a retry. `agent_max_time_seconds` (default **1800**, in `config/runner.yaml`) becomes `--max-time`, letting omp stop itself first. Set it to `0` to disable and rely on the harness timeout alone.

### Model resolution

omp's `--model` is a fuzzy match. When the id after `amazon-bedrock/` is missing from the catalog omp has loaded, omp sends the request to the nearest model it knows and reports no error. omp 18.1.15 had no Claude 5.5 entries, so `us.anthropic.claude-haiku-5-5` ran as Haiku 4.5 and `us.anthropic.claude-opus-5-5` would have run as Opus 5. A 21-task Haiku 5.5 run on 2026-10-08 was Haiku 4.5 throughout, and only the `model` field on each message in `omp-stream.jsonl` showed it.

An upgrade alone does not fix this. In a fresh agent directory, `omp -p` resolves against the snapshot bundled in the binary, and only `omp models` fetches the full catalog and caches it in that directory's `models.db`. omp 18.8.8 lists Haiku 5.5 in its full catalog and still sends it to Haiku 4.5 from a cold directory.

The harness guards against both cases:

1. **Before the first task**, it runs `omp models amazon-bedrock --json` and exits if the exact id is missing, with a message to run `omp update`.
2. **Before each Bedrock task**, it runs the same listing in that task's agent directory, which fills the cache that `omp -p` then reads.
3. **After each task**, it compares the model named on every assistant message with the one requested. A mismatch fails the task with `result_subtype: error_model_mismatch`, skips the retry, and the ids omp used land in `metrics.json` as `models_used`.

`run-swe-router-headless.py` applies checks 2 and 3 to every omp judgment and raises an error on a mismatch, since a judgment from the wrong model is no use.

To check an id by hand, compare Bedrock's list with omp's:

```bash
aws bedrock list-inference-profiles --region us-east-1 \
    --query 'inferenceProfileSummaries[].inferenceProfileId' --output text | tr '\t' '\n' | grep anthropic
omp models find claude-haiku-5-5
```

## Watching a run

omp buffers nothing to the terminal for tens of minutes at a time. The harness mirrors its events to `<artifacts_dir>/omp-stream.jsonl`, which is the only way to watch a task in flight:

```bash
uv run benchmarks/scripts/omp_stream_view.py --latest
tail -f path/to/omp-stream.jsonl | uv run benchmarks/scripts/omp_stream_view.py -
```

The stream is one line per token, so read it through the viewer rather than raw. omp's own `~/.omp/logs` holds lifecycle debug lines, not the event stream.

## Known behaviour

- **Partial artifacts on the first pass.** omp sometimes exits after four of the six artifacts. The harness's top-up pass re-prompts for the missing ones and recovers; a task that needs it costs two agent invocations. Across 63 Bedrock tasks this did not recur systematically.
- **A finished run can end on `stopReason: toolUse`.** omp sometimes closes the session with a tool call still pending, right after the model writes its final summary. The harness records that as `is_error`, but keeps the artifacts: a task with all six on disk is never retried, because a retry deletes them first. Before this rule, a Haiku 4.5 task lost six finished artifacts this way and scored 0.
- **Stream files are large.** A single task's `omp-stream.jsonl` runs from 1 MB to 47 MB. They stay gitignored, including inside the committed `Hello-World` worked examples.

## Results

- [harness-omp-swe3.md](harness-omp-swe3.md) -- every model run under omp with `/swe3`, the repo's headline results.
- [agent-cli-bedrock-setup.md](../benchmarks/docs/agent-cli-bedrock-setup.md) -- wiring `omp` and the `codex` judge to Amazon Bedrock. Working AWS credentials are not enough for `codex`; prove it with a real call before a long run.
