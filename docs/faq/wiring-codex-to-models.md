# How do I wire codex to a model?

`codex` appears twice in this repository, configured separately each time. It is the **judge** that scores every run, always against Amazon Bedrock, and it is one of five **coding harnesses** (`--agent codex`) that can drive a task. This answers the harness half: pointing `--agent codex` at a model on each of the three hosting paths.

For installing codex, wiring it to Bedrock, and the one-line proof that the judge works, see [codex-setup.md](../codex-setup.md). This page assumes `codex --version` already answers.

## The one fact everything follows from

**codex speaks the OpenAI Responses API and nothing else.** codex 0.153.4 removed the chat-completions wire and rejects the fallback outright:

```
Error loading config.toml: `wire_api = "chat"` is no longer supported.
How to fix: set `wire_api = "responses"` in your provider config.
```

So whatever serves the model must answer `POST /v1/responses`. Amazon Bedrock does that for the `openai.*` family only, which is why an open-weight model on Bedrock needs a bridge and a model on your own vLLM server does not.

## How do I wire codex to an open-weight model on Bedrock (Qwen, Kimi, DeepSeek)?

Put a LiteLLM proxy in front that speaks Responses to codex and Converse to Bedrock. Use LiteLLM's **native `bedrock/` provider**, which authenticates from ambient AWS credentials with no bearer token:

```yaml
# litellm-responses-bedrock.yaml
model_list:
  - model_name: qwen.qwen3-coder-30b-a3b-instruct
    litellm_params:
      model: bedrock/qwen.qwen3-coder-30b-a3b-v1:0
      aws_region_name: us-east-2

litellm_settings:
  drop_params: true
```

```bash
uv run --with 'litellm[proxy]' litellm --config litellm-responses-bedrock.yaml \
    --host 127.0.0.1 --port 4002
```

Then run the harness against it as an endpoint:

```bash
cd benchmarks
./scripts/run-e2e-benchmark.sh --provider litellm --endpoint http://127.0.0.1:4002 \
    --agent codex --skill swe3 --model qwen.qwen3-coder-30b-a3b-instruct \
    --dataset dataset/mcp-gateway-registry-v2.yaml --yes < /dev/null
```

Without the bridge, Bedrock rejects the request:

```
The model 'qwen.qwen3-coder-30b-a3b-v1:0' does not support the '/openai/v1/responses' API
```

The model works on Bedrock; it just does not answer that API. `aws bedrock-runtime converse` against the same id returns normally.

**Two traps.**

The committed [litellm-mantle.yaml](../../benchmarks/config/litellm-mantle.yaml) **cannot** serve this path. It registers each model as `openai/<id>` against the `bedrock-mantle` endpoint, so LiteLLM forwards `/v1/responses` untouched and mantle rejects it for a non-`openai.*` model. That config exists for Claude Code, which speaks the Anthropic Messages API. Write a separate config with the `bedrock/` provider for codex.

Pin nothing older than current LiteLLM. The range the mantle script uses, `litellm[proxy]>=1.72,<1.84`, fails the bridge with `500 'NoneType' object has no attribute 'encode'`.

### Prompt caching does not happen on this route

Bedrock Converse caching is opt-in per request: the caller must place `cachePoint` blocks in the message content. codex has no cache-control concept and LiteLLM's bridge adds none, so `cache_read_tokens` is 0 on every task and every token is billed fresh. Measured over the 21-task `mcp-gateway-registry-v2` run: 83,488,690 input tokens, zero cache reads, $13.17.

Two separate limits hide behind that zero, and it is worth knowing which one applies:

| Model | `cachePoint` on Converse |
|---|---|
| `qwen.qwen3-coder-30b-a3b-v1:0` | `AccessDeniedException: You invoked an unsupported model or your request did not allow prompt caching` |
| `us.anthropic.claude-haiku-4-5` | cold call writes `cacheWriteInputTokens: 5204`; warm call reads `cacheReadInputTokens: 5204` |

Qwen cannot cache on Bedrock at all, and a model that can still will not through this bridge. Because Qwen publishes no cache rate, its row in [bedrock_pricing.py](../../benchmarks/scripts/bedrock_pricing.py) carries no `cache_read` or `cache_write` key, and `cost_usd` returns `None` rather than pricing cached tokens at zero if a caller ever reports them.

## How do I wire codex to an open-weight model I serve on vLLM?

Serve the model, then point codex at the server:

```bash
cd benchmarks
./scripts/run-e2e-benchmark.sh --provider vllm --agent codex --skill swe3 \
    --model qwen3.6-35b-fp8 --dataset dataset/mcp-gateway-registry-v2.yaml < /dev/null
```

The harness builds codex's provider block on the command line rather than through environment variables, because **codex 0.153.4 ignores `OPENAI_BASE_URL`** and takes its base URL from whichever provider its config selects. Exporting that variable alone sent endpoint runs wherever `~/.codex/config.toml` pointed, which on a judge-configured machine is Bedrock, producing the misleading `404 The model 'minicpm5-2b' does not exist` (issue #183). What it passes:

```bash
codex exec --json --skip-git-repo-check --dangerously-bypass-approvals-and-sandbox \
  --cd <clone> --model <served-name> \
  -c model_provider=<name> \
  -c model_providers.<name>.base_url=http://127.0.0.1:8000/v1 \
  -c model_providers.<name>.wire_api=responses \
  -c model_providers.<name>.env_key=OPENAI_API_KEY \
  -c model_context_window=262144
```

`OPENAI_API_KEY` travels in the environment, never on the command line, so no local user can read it out of `ps`. A vLLM server that wants no key still needs the variable set; the harness uses `local`.

**The tool-call parser must accept Responses-shaped tools.** The Responses API sends a flat tool definition, `{"type": "function", "name": ...}`; chat completions nests it under `"function"`. Seven of vLLM 0.29.0's parsers read only the nested shape, abort tool extraction on the flat one, end the stream with no `response.completed`, and make codex retry every request five times before failing the turn:

| Works with codex | Breaks with codex |
|---|---|
| `qwen3_coder`, `hermes` | `minicpm5xml`, `dots`, `hy_v3`, `hy_v4`, `rust`, `step3`, `step3p5` |

Check the parser in the model's guide under [self-hosted/vllm/models/](../../self-hosted/vllm/models/) before choosing this agent. Verified working: `qwen3.6-35b-fp8` at a 262,144-token window with `qwen3_coder`.

**Tell codex the context window.** A self-hosted model is unknown to codex, which warns `Model metadata not found. Defaulting to fallback metadata` and sizes its context from that guess. Pass `--context-window` so the harness forwards `model_context_window`.

## How do I wire codex to an OpenAI model hosted on Bedrock?

Nothing to bridge. Bedrock serves the Responses API natively for the `openai.*` family:

```bash
cd benchmarks
./scripts/run-e2e-benchmark.sh --provider bedrock --agent codex --skill swe3 \
    --model openai.gpt-5.6-luna --dataset dataset/mcp-gateway-registry-v2.yaml < /dev/null
```

The harness pins `AWS_REGION` from the config and passes `-c model_provider=amazon-bedrock`; authentication comes from the ambient credential chain, with no proxy and no bearer token. This is the same provider the judge uses.

Cost is derived from the token counts through [bedrock_pricing.py](../../benchmarks/scripts/bedrock_pricing.py), because `codex exec` reports usage but never a billed cost. A model missing from that table yields a null cost rather than a misleading zero.

## Why does my codex run hang before the first request?

Because stdin is open. `codex exec` reads stdin even when the prompt arrives as an argument, and it blocks forever on an open, empty one. The log stops after `Reading additional input from stdin...`, the rollout file under `~/.codex/sessions/` stops growing, and the server sees no requests. One run sat like that for ten minutes and finished in 78 seconds once relaunched with stdin closed.

Redirect on every launch:

```bash
./scripts/run-e2e-benchmark.sh ... < /dev/null > .scratchpad/e2e-<slug>.log 2>&1
```

A frozen rollout file is the fastest way to tell a hung run from a slow one:

```bash
tail -f "$(ls -t ~/.codex/sessions/*/*/*/*.jsonl | head -1)"
```

## Which path serves which model?

| You want to benchmark | Flags | Bridge needed |
|---|---|---|
| `openai.*` on Bedrock | `--provider bedrock` | no |
| Any model on your own vLLM server | `--provider vllm` | no, but the tool parser must be Responses-safe |
| Open-weight on Bedrock (Qwen, Kimi, DeepSeek) | `--provider litellm --endpoint ...` | yes, LiteLLM with the native `bedrock/` provider |
| Anthropic models | any | codex reaches them on Bedrock, though Claude Code is the better-measured harness for them |

## Related

- [agent-cli-bedrock-setup.md](../../benchmarks/docs/agent-cli-bedrock-setup.md) -- wiring the `codex` judge and `claude` to Bedrock, and proving it with a live call before a long run.
- [harness-reference.md](../../benchmarks/docs/harness-reference.md#choosing-the-agent) -- every supported agent, its providers, and how each one's cost is accounted.
- [cost-per-task-methodology.md](../cost-per-task-methodology.md) -- why a metered Bedrock bill and a hardware-derived self-hosted figure do not compare as raw dollars.
