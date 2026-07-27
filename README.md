# Agentic Coding Harness and Benchmarks

[![License: MIT-0](https://img.shields.io/badge/License-MIT--0-yellow.svg)](LICENSE)
[![Bedrock](https://img.shields.io/badge/Amazon-Bedrock-blue)](https://docs.aws.amazon.com/bedrock/latest/userguide/models-endpoint-availability.html)
[![Models: 45](https://img.shields.io/badge/Models-45%20from%2011%20providers-orange)](./)

> **This is sample code intended for demonstration and learning purposes only.**
> It is not meant for production use. Review and harden all scripts, configurations,
> and IAM permissions before using in any production or sensitive environment.

## Overview

This repository is a **benchmark and harness for measuring how well different LLMs perform real-world software-engineering tasks** when driven by a coding agent. The coding agent is [Claude Code](https://docs.anthropic.com/en/docs/claude-code), Anthropic's command-line coding agent, which by default talks only to Anthropic's own models. Here it is wired up to run with a model hosted in any of **three different places**, so you can put many models through the *same* tasks with the *same* agent and compare them directly on both quality and cost.

Each task points the agent at a real GitHub repository and a real problem. The agent works the task **non-interactively** through the `/swe` skill, which lands four design artifacts on disk (`github-issue.md`, `lld.md`, `review.md`, `testing.md`). The harness records what the run cost -- token usage, latency, and the number of LLM turns -- and a separate [judge](benchmarks/docs/harness-reference.md#scoring-the-artifacts-the-judge) scores the artifacts for quality. Run the same task across models and the resulting `metrics.json` / `eval.json` files line up side by side.

## The three hosting paths

Whichever path you choose, the agent (Claude Code), the tasks, the `/swe` skill, and the scoring are identical -- only *where the model runs and how the request reaches it* changes.

```mermaid
flowchart TD
    subgraph Harness["Benchmark harness (benchmarks/)"]
        CC["Claude Code CLI<br/>(the coding agent)<br/>speaks Anthropic Messages API"]
    end

    BedrockA["Path 1<br/>Amazon Bedrock<br/>Anthropic route<br/>───────────────<br/>Claude Opus · Sonnet · Haiku"]
    Proxy["LiteLLM proxy (we run it)<br/>Anthropic ↔ OpenAI translation"]
    BedrockM["Path 2<br/>Amazon Bedrock (mantle endpoint)<br/>───────────────<br/>Kimi · Qwen · DeepSeek · Mistral …<br/>(any open-weight model on Bedrock)"]
    VLLM["Path 3<br/>EC2 GPU node · vLLM<br/>───────────────<br/>your self-hosted open-weight model"]

    CC -- "Anthropic Messages<br/>(provider: bedrock)" --> BedrockA
    CC -- "Anthropic Messages<br/>(provider: endpoint)" --> Proxy
    Proxy -- "/v1/chat/completions" --> BedrockM
    CC -- "Anthropic Messages<br/>(provider: endpoint, SSH tunnel)" --> VLLM

    classDef agent fill:#E5E7EB,stroke:#6B7280,color:#111827
    classDef proxy fill:#EDE9FE,stroke:#7C3AED,color:#3B0764
    classDef bedrock fill:#FFF3E0,stroke:#FF9900,color:#1F2937
    classDef ec2 fill:#E0F2FE,stroke:#0284C7,color:#0C4A6E
    class CC agent
    class Proxy proxy
    class BedrockA,BedrockM bedrock
    class VLLM ec2
```

| | Path 1 - Anthropic on Bedrock | Path 2 - open-weight on Bedrock (LiteLLM) | Path 3 - self-hosted on EC2 (vLLM) |
| --- | --- | --- | --- |
| **Which models** | Anthropic family (Claude Opus, Sonnet, Haiku) | Any open-weight model on Bedrock (Kimi, Qwen, DeepSeek, Mistral, GLM, …) | Any open-weight model you can serve (Qwen3-Coder, GLM, Kimi, …) |
| **Where the model runs** | Amazon Bedrock | Amazon Bedrock | Your EC2 GPU instance |
| **How Claude Code reaches it** | Directly, native Anthropic route | Through a [LiteLLM](https://github.com/BerriAI/litellm) proxy we run that translates Anthropic ↔ OpenAI | Directly to your vLLM server (over an SSH tunnel) |
| **Cost model** | Pay-per-token | Pay-per-token | Fixed hourly GPU cost |
| **Extra infrastructure** | None | The LiteLLM proxy ([one script](benchmarks/scripts/bedrock-mantle-proxy.sh)) | An EC2 GPU node running vLLM |
| **Best for** | Benchmarking the Anthropic family | Model variety with zero infrastructure to manage | Data sovereignty, air-gapped, and high-volume workloads where fixed GPU cost beats per-token pricing |
| **Operational guide** | [Path 1](benchmarks/docs/path-anthropic-on-bedrock.md) | [Path 2](benchmarks/docs/path-open-weight-on-bedrock-litellm.md) | [Path 3](benchmarks/docs/path-self-hosted-vllm.md) |

The key enabler for Path 2 is the LiteLLM proxy. Claude Code speaks the [Anthropic Messages API](https://docs.aws.amazon.com/bedrock/latest/userguide/inference-messages-api.html), which on Bedrock reaches **only** Claude/Anthropic models; the open-weight models are reachable solely through Bedrock's OpenAI-compatible [`bedrock-mantle` endpoint](https://docs.aws.amazon.com/bedrock/latest/userguide/inference.html) (Chat Completions). The proxy sits between the two and translates in both directions, so **any open-weight model on Bedrock can be wired into Claude Code** without changing the agent. All 38 third-party models on `bedrock-mantle` support tool calling and streaming natively.

## What a single benchmark run does

The flow below is identical across all three paths; only the box the request lands in (Bedrock's Anthropic route, the LiteLLM proxy, or your vLLM server) changes.

```mermaid
sequenceDiagram
    participant H as Harness<br/>(run-swe-headless.py)
    participant G as GitHub repo
    participant CC as Claude Code<br/>(/swe skill)
    participant M as Model<br/>(path 1/2/3)
    participant J as Judge<br/>(codex_judge.py)

    H->>G: clone repo at pinned ref (temp dir)
    H->>CC: claude -p "/swe repo … problem … model …"
    loop agent loop (bounded by max_turns)
        CC->>M: Anthropic Messages request
        M-->>CC: reply (text and/or tool_use)
        CC->>CC: run tools (read repo, write artifacts)
    end
    CC-->>H: 4 artifacts + JSON result (tokens, latency, turns)
    H->>H: write metrics.json beside artifacts
    H->>G: remove temp clone
    J->>J: score the 4 artifacts against the rubric
    J-->>H: eval.json (quality scores) merged into metrics.json
```

The skill **stops at design**. It does not modify production code, run tests, or open PRs -- whether the design is any good is the downstream evaluation step the judge (or a human) performs on the artifacts. Full mechanics are in the [harness reference](benchmarks/docs/harness-reference.md).

> **"SWE" here means software engineering in general -- not [SWE-bench](https://www.swebench.com/), the specific benchmark dataset.** The `/swe` skill lets you run any model against any task in any repo of your choosing. It is a *harness*, not a fixed benchmark set: compare results across models on the same task, or a single model across tasks of varying difficulty.

## Datasets

A dataset is a single YAML file: a metadata header plus a list of tasks, each pointing at a GitHub repo and a problem. Two datasets ship in [benchmarks/dataset/](benchmarks/dataset/):

- [hello-world.yaml](benchmarks/dataset/hello-world.yaml) -- a trivial sanity dataset (the [octocat/Hello-World](https://github.com/octocat/Hello-World) repo) for kicking the tires of a new model or endpoint.
- [mcp-gateway-registry.yaml](benchmarks/dataset/mcp-gateway-registry.yaml) -- the reference dataset, whose tasks are drawn from real upstream issues in [agentic-community/mcp-gateway-registry](https://github.com/agentic-community/mcp-gateway-registry).

**Nothing in the harness is specific to a particular repository.** Adding your own benchmark dataset is just writing another YAML file in the same format -- point tasks at any public repo and pinned ref. The dataset format is documented in the [harness reference](benchmarks/docs/harness-reference.md#the-dataset).

## Results: a worked example

To show what the harness produces, we ran it against [agentic-community/mcp-gateway-registry](https://github.com/agentic-community/mcp-gateway-registry) at tag `1.24.4` -- **5 tasks**, each scored by the judge. The numbers below are only for models **we have actually run end to end so far**, all **self-hosted via vLLM**: two frontier models (Kimi-K2.7-Code and GLM-5.2) on **8x H200 (`p5en.48xlarge`)**, and three open-weight Qwen models on a single **`g6e.12xlarge` (4x L40S)**. The other hosting paths (Anthropic on Bedrock, open-weight on Bedrock via the LiteLLM proxy) are **coming soon** -- we publish only what we have measured here. (The `mcp-gateway-registry` dataset ships in [benchmarks/dataset/](benchmarks/dataset/mcp-gateway-registry.yaml) so you can reproduce the run; the generated artifacts themselves are not committed, so a customer's own runs never risk landing in version control. The only committed worked example under [benchmarks/swe-benchmark-data/](benchmarks/swe-benchmark-data/) is the trivial `Hello-World` sanity run.)

| # | Problem | Difficulty | Source |
|---|---------|-----------|--------|
| 1 | `remove-faiss` | Medium | Upstream [#1285](https://github.com/agentic-community/mcp-gateway-registry/issues/1285) / [#452](https://github.com/agentic-community/mcp-gateway-registry/issues/452) |
| 2 | `remove-efs-from-terraform-aws-ecs` | Medium | Upstream [#1286](https://github.com/agentic-community/mcp-gateway-registry/issues/1286) |
| 3 | `ssrf-hardening-outbound-url-validation` | Medium | Upstream [#1282](https://github.com/agentic-community/mcp-gateway-registry/issues/1282) |
| 4 | `migrate-ecs-env-vars-to-secrets-manager` | High | Upstream [#1134](https://github.com/agentic-community/mcp-gateway-registry/issues/1134) |
| 5 | `replace-keycloak-db-password-with-rds-iam` | High | Upstream [#1303](https://github.com/agentic-community/mcp-gateway-registry/issues/1303) |

**Models benchmarked so far (all Path 3, self-hosted on vLLM):** Kimi-K2.7-Code, GLM-5.2, MiniMax-M2.5, and Qwen3-Coder-480B-A35B-Instruct (all on 8x H200 / `p5en.48xlarge`), plus Qwen3.6-35B-A3B, Qwen3-Coder-30B-A3B-Instruct, Qwen3-Coder-Next, and Gemma-4-31B-it (on `g6e.12xlarge` / 4x L40S). **Coming soon:** Path 1 (Anthropic family on Bedrock -- Claude Opus/Sonnet/Haiku) and Path 2 (open-weight on Bedrock via the LiteLLM proxy -- DeepSeek, Mistral, …).

### Scoring rubric (LLM-as-judge)

Each of the 4 artifacts is scored 0-100 by an independent judge session. Within each artifact the judge applies the same 4-criterion rubric, **25 points per criterion, summing to 100**:

| Criterion | 0-25 each | What the judge evaluates |
|-----------|-----------|--------------------------|
| **Completeness** | 25 | Did the artifact identify all affected files, dependencies, and components? Any obvious touchpoints (Terraform, IAM, Docker, tests, docs) missed? |
| **Correctness** | 25 | Are the proposed changes technically right? Would the design actually work? Are AWS service patterns idiomatic (e.g. ECS `secrets` block vs custom boto3 code)? |
| **Specificity** | 25 | Concrete file paths, line numbers, code snippets, resource names -- or vague hand-waving? Could a junior engineer implement this artifact alone? |
| **Risk awareness** | 25 | Rollback strategy, backwards-compat, deployment cutover, edge cases (cold start, secret rotation, token expiry, etc.) -- enumerated or ignored? |

**Artifact total = sum of 4 criteria (0-100). Task score = mean of the 4 artifact totals (also 0-100).** The judge is calibrated so a median artifact scores around 60-70, not 85; 90+ is reserved for genuinely excellent work; hallucinated files or functions lose at least 10 points off Correctness. Per-cell JSON with criterion breakdowns and judge notes lives at `{model}/{repo}/{task}/eval.json`. The judge itself is documented in the [harness reference](benchmarks/docs/harness-reference.md#scoring-the-artifacts-the-judge).

### Results -- 5 tasks x self-hosted models

All cells are task scores (0-100), the mean of the artifact totals per (task x model). These are **`/swe2` runs -- design *and* implementation** (six artifacts: the four design docs plus `patch.diff` + `implementation.md`), scored by the same judge (`codex exec`, `gpt-5.6-sol`, high reasoning effort). All models were **self-hosted via vLLM**; hardware differs by model size (see the row under the table). Bold = top score in row. Other hosting paths are **coming soon**.

| Task | Difficulty | GLM-5.2⁶ | Kimi-K2.7-Code | MiniMax-M2.5 | Gemma-4-31B | Qwen3.6-35B | Qwen3-Coder-480B⁷ | Qwen3-Coder-30B | Qwen3-Coder-Next⁴ |
|------|-----------|---------:|---------------:|-------------:|------------:|------------:|------------------:|----------------:|:-----------------:|
| `remove-faiss` | Medium | 62.8 | 0.0 ⁵ | 44.2 | 49.4 | **57.6** | 45.6 | 24.4 | n/a |
| `remove-efs-from-terraform-aws-ecs` | Medium | **73.8** | 70.8 | 62.0 | 60.4 | 59.0 | 55.4 | 0.0 ⁵ | n/a |
| `ssrf-hardening-outbound-url-validation` | Medium | 64.6 | **72.0** | 58.2 | 49.4 | 54.6 | 0.0 ⁵ | 0.0 ⁵ | n/a |
| `migrate-ecs-env-vars-to-secrets-manager` | High | **68.6** | 67.2 | 53.6 | (re-running)⁸ | 39.2 | 41.0 | 32.2 | n/a |
| `replace-keycloak-db-password-with-rds-iam` | High | **64.2** | 52.2 | 39.8 | 40.0 | 36.0 | 37.8 | 22.8 | n/a |
| **Mean (excl. failed task⁵)** | | **66.80** | 65.55 | 51.56 | 49.80 | 49.28 | 44.95 | 26.47 | n/a |

The **Mean** row excludes any task that scored 0 -- a genuine model failure (missing artifacts), which is an unresolved anomaly rather than a quality measurement, so it is left out of the average **pending further investigation** and flagged with `⁵`. Per-task 0.0 cells are still shown so the failure is visible. GLM-5.2 / MiniMax-M2.5 / Qwen3.6-35B score over all 5 tasks (no failures); Kimi over 4 (one failed), Qwen3-Coder-480B over 4, Qwen3-Coder-30B over 3 (two failed), Gemma-4-31B over the 4 it has completed (the fifth is re-running -- see `⁸`).

**Hardware:** Kimi-K2.7-Code (1.06T-param MoE, ~1 TB weights) ran on **8x H200** (`p5en.48xlarge`) at its full **131,072-token (128K) native context window**; GLM-5.2 (744B MoE / 40B active, ~750 GB FP8 weights), MiniMax-M2.5, and Qwen3-Coder-480B (480B MoE / 35B active, FP8, TP=4) also ran on **8x H200** (`p5en.48xlarge`); the three smaller Qwen models (3B-active MoE) and Gemma-4-31B (dense, ~63 GB) ran on a single **`g6e.12xlarge`** (4x L40S) at a 200K window. All via vLLM. Gemma-4-31B is dense and slow, so it used a raised per-task timeout (`--timeout-seconds 3600`); the default 1800s was not enough for it to return. Note Kimi's 128K window is below the harness's 200K agentic-coding guideline, yet it completed 4 of 5 tasks -- the one failure (`keycloak-rds-iam`) was a turn-cap timeout, not a context overflow.

⁴ Qwen3-Coder-Next (79.6B, ~160 GB weights) **could not be benchmarked on the `g6e.12xlarge`.** There the weights leave room for only a ~16K context window, but agentic coding tasks need 100K-250K input tokens per request, so every task overflows the window on the first prompt. It needs a larger-VRAM node (e.g. `g6e.48xlarge`) to serve a >=200K window. The `/benchmark` skill enforces a 200K-minimum gate by default as a conservative guideline -- Kimi's 128K run shows a window somewhat below 200K can still work when the tasks fit, but 16K cannot. See [self-hosted/vllm/models/qwen3-coder-next.md](self-hosted/vllm/models/qwen3-coder-next.md).

⁵ **Genuine model failures, scored 0.** On these `/swe2` runs the failures are: Kimi-K2.7-Code on `remove-faiss`, Qwen3-Coder-480B on `ssrf`, and Qwen3-Coder-30B on `remove-efs` and `ssrf`. Each failed to produce a scorable artifact set (typically the model exhausted its turn budget on the implementation step without landing edits, so no `patch.diff`). The judge records a missing/empty-artifact folder as a 0 with a `MODEL FAILURE` verdict rather than dropping it. The **Mean** row excludes these tasks (over the tasks each model completed): GLM-5.2 66.80 (5/5), Kimi 65.55 (4/5), MiniMax-M2.5 51.56 (5/5), Gemma-4-31B 49.80 (4 completed), Qwen3.6-35B 49.28 (5/5), Qwen3-Coder-480B 44.95 (4/5), Qwen3-Coder-30B 26.47 (3/5).

⁶ **GLM-5.2 ran with more headroom than the others -- not strictly apples-to-apples.** GLM-5.2 (`zai-org/GLM-5.2-FP8`, 744B MoE / 40B active, ~750 GB FP8 weights) was served on **8x H200** at a **300K context window**. It leads on quality (66.80 over 5/5) but on the biggest, most expensive box measured (~$18/task, see the cost section). Treat cross-instance comparisons as indicative until normalized.

⁷ **Qwen3-Coder-480B intermittently fails to produce artifacts -- the failure is nondeterministic, not task-specific.** Qwen3-Coder-480B (`Qwen/Qwen3-Coder-480B-A35B-Instruct-FP8`, 480B MoE / 35B active) was served on the **8x H200** node at **TP=4** (a block-FP8 MoE sharding constraint forces TP=4, not 8 -- see [its model guide](self-hosted/vllm/models/qwen3-coder-480b.md)), 200K window. Like the smaller Qwen3-Coder-30B, it periodically explores/edits the repo instead of completing the artifact chain (or exhausts the turn cap), scoring 0 on some tasks. It is a harness-conformance instability of a coder-tuned model, not a serving or context problem.

⁸ **Gemma-4-31B's `migrate-ecs` task is being re-run.** On the sweep it produced only the four design artifacts for this task (no `patch.diff`/`implementation.md` -- the model stopped after design), so `summarize_run.py` excluded it; Gemma's 49.80 mean is over the 4 tasks it completed. The task is re-running under the updated `/swe2` skill (which added explicit implementation-step discipline); this row and Gemma's mean will update when it lands.

### Cost vs. quality

![Cost vs. quality scatter: mean estimated cost per task against mean task score, for the self-hosted models, with the cost/quality frontier highlighted](docs/images/cost-quality.png)

Mean **hardware-derived** cost per task (x) against mean task score (y), one point per model. **Cost is now measured, not estimated:** each model's blended cost per token (from its throughput sweep -- instance $/hr / measured tokens/sec, see [cost-per-task-methodology.md](self-hosted/vllm/cost-per-task-methodology.md)) times that model's *actual* input+output tokens per task on this quality run, averaged over its non-failed tasks. The cost/quality frontier runs **Qwen3.6-35B ($0.59 / 49.28) -> MiniMax-M2.5 ($1.55 / 51.56) -> Kimi-K2.7-Code ($11.09 / 65.55) -> GLM-5.2 ($18.10 / 66.80)**; Gemma-4-31B ($3.43), Qwen3-Coder-30B ($1.29 / 26.47), and Qwen3-Coder-480B ($9.98 / 44.95) sit **below** the frontier (dominated), and Qwen3-Coder-Next is omitted (not viable on this node). A model's mean excludes any 0-score failed task, matching the table (see footnote ⁵). Regenerate from the committed run + performance summaries with `uv run scripts/plot_cost_quality.py` (add `--dark` for the dark theme) from `benchmarks/`.

### Per-model leaderboard (self-hosted, so far)

Mean score is over the tasks each model completed (any 0-score failed task is excluded pending investigation; see the note above). **$/task** is the hardware-derived blended cost (instance $/hr / measured tokens/sec x this run's actual per-task tokens); lower is better.

| Rank | Model | Params (active) | Hardware | Mean score | $/task | Tasks scored |
|-----:|-------|----------------|----------|-----------:|-------:|-------------:|
| 1 | GLM-5.2⁶ | 744B (40B) | 8x H200 | **66.80** | $18.10 | 5/5 |
| 2 | Kimi-K2.7-Code | 1,058.6B (MoE) | 8x H200 | **65.55** | $11.09 | 4/5 |
| 3 | MiniMax-M2.5 | 230B (10B) | 8x H200 (TP=4) | **51.56** | $1.55 | 5/5 |
| 4 | Gemma-4-31B-it⁸ | 31B (dense) | g6e.12xlarge | **49.80** | $3.43 | 4 done |
| 5 | Qwen3.6-35B-A3B | 35.9B (3B) | g6e.12xlarge | **49.28** | **$0.59** | 5/5 |
| 6 | Qwen3-Coder-480B-A35B-Instruct⁷ | 480B (35B) | 8x H200 (TP=4) | **44.95** | $9.98 | 4/5 |
| 7 | Qwen3-Coder-30B-A3B-Instruct | 30.5B (3B) | g6e.12xlarge | **26.47** | $1.29 | 3/5 |
| - | Qwen3-Coder-Next | 79.6B (3B) | (needs bigger node) | not viable on g6e.12xlarge | -- | 0 |

**Coming soon:** Claude Opus/Sonnet/Haiku (Path 1, Bedrock) and the open-weight Bedrock models via the LiteLLM proxy (Path 2 -- DeepSeek, Mistral, …).

### What the data says (so far)

These are early self-hosted numbers on differing hardware; treat them as a starting point, not a final ranking. Cross-path comparisons wait until the Bedrock paths are run.

- **GLM-5.2 leads on quality (66.80 over 5/5), Kimi-K2.7-Code is close behind (65.55 over 4/5)** -- but both need an 8x H200 box and cost **$11-18 per task**, an order of magnitude more than the small-node models. On this `/swe2` (design + implementation) benchmark the trillion-parameter models are the quality ceiling but the expensive corner of the frontier.
- **Qwen3.6-35B is the value story, now with a measured price:** on one mid-range GPU node (a single g6e.12xlarge) it scores 49.28 over all 5 tasks with no failures at a **hardware-derived $0.59 per task** -- the cheapest measured, ~30x under GLM-5.2, and on the cost/quality frontier.
- **MiniMax-M2.5 is the best quality-per-dollar in the upper half:** 51.56 over 5/5 at **$1.55/task** -- it beats the dense Gemma-4-31B ($3.43) and the much pricier Qwen3-Coder-480B ($9.98) while costing a fraction, sitting on the frontier just above Qwen3.6-35B.
- **Cost is now measured, not estimated.** Every $/task above is `instance $/hr / measured tokens/sec` (from each model's throughput sweep) times that model's real per-task token load -- so the cost axis reflects actual serving economics on the benchmarked hardware, not a token-price guess. See [cost-per-task-methodology.md](self-hosted/vllm/cost-per-task-methodology.md).
- **The judge is strict, and implementation is harder than design.** These `/swe2` runs score design *and* code; scores in the 40-67 range reflect artifacts that are serviceable but often light on the specificity, risk-analysis, and complete implementation the rubric rewards. Coder-tuned models (Qwen3-Coder-30B/480B) are the least reliable here -- they tend to burn the turn budget implementing instead of completing the full artifact set, producing the 0-score failures.
- **MoE economics are the reason to self-host these.** Nearly every model here is a mixture-of-experts, so per-token compute (and cost) tracks the active-expert count, not the total -- the regime where a fixed-cost GPU node can beat per-token API pricing under load. The 3B-active Qwen MoEs on a single L40S node are the clearest example: sub-$1.50/task.

> **The example repo is the example, not the contract.** `/swe` works against any GitHub URL -- clone the target you actually care about, write the task description, and run.

## Prerequisites

- An **AWS account** with [Amazon Bedrock model access](https://console.aws.amazon.com/bedrock/home#/modelaccess) enabled for the models you want (Paths 1 and 2).
- **AWS credentials** configured locally (`aws configure`, an IAM role, or AWS SSO).
- **[Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code)** installed.
- **[uv](https://docs.astral.sh/uv/)** and **Python 3.10+** for the harness.
- For Path 3: permission to launch an **EC2 GPU instance** (e.g. `g6e.12xlarge`).

> The `bedrock-mantle` endpoint used for Path 2 (third-party models) is currently available in **`us-east-1`**.

## Get started

1. **Set up the harness** (its own isolated virtual environment):

   ```bash
   cd benchmarks
   uv sync
   cp config/runner.example.yaml config/runner.yaml
   ```

2. **Run a benchmark.** The fastest way is the **`/benchmark` skill** from Claude Code, which drives the whole flow interactively -- pre-flight checks, the harness run over a dataset, and the judge -- for any of the three paths. It even manages the vLLM server and metrics collector for the self-hosted path:

   ```
   /benchmark provider=vllm model=qwen3.6-35b dataset=dataset/mcp-gateway-registry.yaml
   ```

   Prefer a script? The same flow runs headless via [benchmarks/scripts/run-e2e-benchmark.sh](benchmarks/scripts/run-e2e-benchmark.sh) (`--provider bedrock|litellm|vllm --model ... --dataset ...`).

3. **Pick a path and follow its guide** for the setup details each one needs -- every guide ends with a copy-pasteable run command:
   - [Path 1 - Anthropic models directly on Amazon Bedrock](benchmarks/docs/path-anthropic-on-bedrock.md)
   - [Path 2 - open-weight models on Amazon Bedrock via a LiteLLM proxy](benchmarks/docs/path-open-weight-on-bedrock-litellm.md)
   - [Path 3 - self-hosted open-weight models on EC2 with vLLM](benchmarks/docs/path-self-hosted-vllm.md)

4. **Read the shared mechanics** once (they apply to every path): the [harness reference](benchmarks/docs/harness-reference.md) covers the dataset format, the runner config, running the benchmark, the metrics file, and the judge.

For Path 3 you must first stand up the vLLM server itself -- see [self-hosted/vllm/README.md](self-hosted/vllm/README.md) (or let the `/benchmark` skill start it for you).

## Repository structure

```text
claude-code-multi-model/
├── README.md                  ← You are here (concepts, the three paths, results)
├── LICENSE                    MIT-0
├── CODE_OF_CONDUCT.md
├── CONTRIBUTING.md
├── SECURITY.md
├── SUPPORT.md
├── THIRD_PARTY                Third-party dependency attributions
├── .github/                   Issue and pull-request templates
├── .claude/                   ← Claude Code skills shipped with the repo
│   └── skills/
│       ├── benchmark/         /benchmark — run one end-to-end benchmark (service + harness + judge)
│       ├── swe/               /swe — drive a model through a SWE task on any repo
│       ├── security-check/    /security-check — Cipher security review + fix before any commit
│       └── vllm-setup/        /vllm-setup — stand up the EC2 vLLM server (Path 3)
├── benchmarks/                ← The benchmark harness and results
│   ├── README.md              Harness landing page
│   ├── docs/                  Shared harness reference + one guide per hosting path
│   ├── config/                runner.example.yaml, litellm-mantle.yaml (Path 2 proxy)
│   ├── dataset/               Benchmark dataset YAML files
│   ├── scripts/               Run harness, dataset/config loaders, judges, proxy launcher
│   ├── tests/                 Unit tests
│   └── swe-benchmark-data/    Committed example: Hello-World only; all other runs are gitignored
└── self-hosted/               ← Path 3: EC2 self-hosted serving (vLLM)
    └── vllm/
        ├── README.md          Full EC2 + vLLM setup guide
        ├── models/            Per-model serving guidelines (one .md per model)
        ├── scripts/           vllm-install.sh, vllm-serve.sh, tunnel.sh, …
        ├── clients/           Inference + metrics-collection Python clients
        ├── tests/             unittest suite for the clients
        └── config/            claude-code.json, opencode.json
```

## See also

- [Claude Code docs](https://docs.anthropic.com/en/docs/claude-code) -- official Claude Code documentation
- [benchmarks/README.md](benchmarks/README.md) -- the harness landing page
- [self-hosted/vllm/README.md](self-hosted/vllm/README.md) -- standing up a self-hosted vLLM server (Path 3)

## License

This library is licensed under the MIT-0 License. See the [LICENSE](LICENSE) file.
