# Wiring the agent CLIs to Amazon Bedrock

The harness shells out to two CLIs that must reach **Amazon Bedrock** on their own: `claude` (or `pi` / `omp` / `kiro-cli`) produces the artifacts, and `codex` scores them as the judge. Neither is configured by the harness, the `/benchmark` skill, or any script here -- they read their own config, so a machine can pass every pre-flight check and still fail the moment a model is invoked.

**`aws sts get-caller-identity` succeeding is not enough.** The pre-flight in [end-to-end-self-hosted-run.md](end-to-end-self-hosted-run.md) only proves the instance can reach AWS. A CLI that has not been pointed at Bedrock will ignore those credentials entirely and call its vendor's public API instead. The failure looks like this, on a box whose exec role is perfectly healthy:

```text
ERROR: unexpected status 401 Unauthorized: Missing bearer or basic authentication in header,
       url: https://api.openai.com/v1/responses
```

That is `codex` talking to OpenAI, not Bedrock. Nothing about it mentions Bedrock or AWS, which is what makes it slow to diagnose.

This page is the copy-pasteable fix for both CLIs. It is condensed from [aarora79/claude-codex-bedrock-ec2](https://github.com/aarora79/claude-codex-bedrock-ec2), which carries the fuller version (VS Code extension setup, the legacy LiteLLM route, region discovery); when the two disagree, that repo is upstream.

## Prerequisite: the exec role

Both CLIs use the standard AWS SDK credential chain, so an EC2 instance role with Bedrock access needs no keys on disk:

```bash
aws sts get-caller-identity
```

The principal needs `bedrock:InvokeModel` and `bedrock:InvokeModelWithResponseStream` (plus `bedrock:ListInferenceProfiles` if you use inference profiles). For the judge it also needs the **`bedrock-mantle`** OpenAI-compatible endpoint; the managed policy `arn:aws:iam::aws:policy/AmazonBedrockLimitedAccess` covers both.

## Codex (the judge)

Codex ships a native `amazon-bedrock` provider that talks to `bedrock-mantle` and authenticates from the credential chain. **No proxy and no bearer token are required** -- the LiteLLM route older notes describe is legacy.

```bash
npm install -g @openai/codex
codex --version    # must be >= 0.144 for the native provider
```

```bash
mkdir -p ~/.codex
cat > ~/.codex/config.toml <<'EOF'
model_provider = "amazon-bedrock"
model_providers.amazon-bedrock.aws.region = "us-east-2"
model = "openai.gpt-5.6-sol"
EOF
```

Verify before trusting a benchmark run to it:

```bash
codex exec --skip-git-repo-check "Reply with exactly: JUDGE OK"
```

Two things that decide whether this works:

- **The region must host the model.** The GPT-5.6 models are region-scoped, and asking a region that does not host one returns a 404 (`The model '...' does not exist`), not a helpful message. `openai.gpt-5.6-sol` -- the judge's default ([codex_judge.py](../scripts/codex_judge.py), overridable with `JUDGE_MODEL`) -- runs in **us-east-1 and us-east-2 only**; `openai.gpt-5.6-terra` and `openai.gpt-5.6-luna` add us-west-2.
- **Scope the region in `config.toml`, not `AWS_REGION`.** `model_providers.amazon-bedrock.aws.region` pins Codex to one region without disturbing the ambient environment -- which matters here, because the same box may point Claude Code at a different region and drives a local vLLM server that reads `AWS_*` for its own reasons.

`--skip-git-repo-check` is only needed outside a git repo or trusted folder; the judge passes its own flags. If Codex warns that `bubblewrap` is missing it falls back to a bundled copy, which is harmless for `--sandbox read-only` judging; `sudo apt install bubblewrap` silences it.

## Claude Code (the agent, on the Bedrock path)

Only needed when Claude Code itself must call Bedrock -- that is `--provider bedrock`. On the `vllm` and `litellm` paths the harness points Claude Code at the local server or proxy instead, and only the judge uses Bedrock.

```bash
npm install -g @anthropic-ai/claude-code
```

```bash
cat >> ~/.bashrc <<'EOF'
export CLAUDE_CODE_USE_BEDROCK=1
export AWS_REGION=us-east-1
export ANTHROPIC_MODEL='us.anthropic.claude-opus-4-8[1m]'
export ANTHROPIC_SMALL_FAST_MODEL='us.anthropic.claude-haiku-4-5-20251001'
EOF
source ~/.bashrc
```

Confirm with `/status` inside `claude`.

The **VS Code extension does not read `~/.bashrc`** (it is not a login shell), so put the same variables in the `env` block of `~/.claude/settings.json` and fully restart VS Code -- a window reload is usually not enough, because the extension host reads that file on boot. Merge into the file if it already exists. On Remote-SSH it must be the copy on the remote box.

## Checking both before a run

```bash
command -v claude codex
aws sts get-caller-identity >/dev/null && echo "aws ok"
codex exec --skip-git-repo-check "Reply with exactly: JUDGE OK"
```

The third line is the one that matters: it is the only check that proves the judge can actually reach Bedrock. Run it before starting a long benchmark, because `--skip-judge` is the fallback if it fails, and discovering that after a multi-hour harness run means scoring a second time.

## Related

- [aarora79/claude-codex-bedrock-ec2](https://github.com/aarora79/claude-codex-bedrock-ec2) -- upstream source for this page.
- [end-to-end-self-hosted-run.md](end-to-end-self-hosted-run.md) -- the full manual run-book; its pre-flight assumes what this page sets up.
- [harness-reference.md](harness-reference.md#running-the-codex-judge) -- what the judge does with the model once it can reach it.
- [path-anthropic-on-bedrock.md](path-anthropic-on-bedrock.md) -- Path 1, where Claude Code itself runs on Bedrock.
