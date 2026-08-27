<h1 align="center">Agentic Coding Harness and Benchmarks</h1>

<p align="center">
<a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT--0-yellow.svg" alt="License: MIT-0"></a>
<a href="https://docs.aws.amazon.com/bedrock/latest/userguide/models-endpoint-availability.html"><img src="https://img.shields.io/badge/Amazon-Bedrock-blue" alt="Bedrock"></a>
<a href="./"><img src="https://img.shields.io/badge/Models-45%20from%2011%20providers-orange" alt="Models: 45"></a>
</p>

<p align="center">
<a href="https://github.com/aarora79/agentic-coding-harness-benchmarks">GitHub Repo</a> |
<a href="#what-do-i-do-with-this">What do I do with this?</a> |
<a href="docs/results-swe3.md">Results (/swe3)</a> |
<a href="docs/agentic-coding-swe-comparison-swe3.md">Harness Comparison</a> |
<a href="docs/slides/agentic-coding-benchmarks-presentation.pdf">Slide Deck</a> |
<a href="docs/slides/agentic-coding-benchmarks-exec.pdf">Executive Brief</a> |
<a href="docs/cost-per-task-methodology.md">Cost Methodology</a>
</p>

> **This is sample code intended for demonstration and learning purposes only.**
> It is not meant for production use. Review and harden all scripts, configurations,
> and IAM permissions before using in any production or sensitive environment.

> [!WARNING]
> **These results are actively churning -- expect the numbers to move for a few days.**
> We are re-running benchmarks almost hourly and learning a great deal about how
> different **coding-harness x model** combinations behave: their real token usage,
> caching, cost, and how each model drives (or under-drives) a long-horizon agentic
> task. As we learn, methodology improves (e.g. counting subagent tokens, switching
> the default skill to a single-agent variant) and figures get re-measured. Treat
> the current numbers as a **live snapshot**, not final -- they should settle over
> the coming days.

## Why this exists

Enterprises are adopting coding agents and models at scale, and the bill grows with every developer and every task. The two big levers on that bill -- **which harness** drives the work and **which model** it drives -- are usually chosen on gut feel or on public leaderboards that may already be **saturated**: models can be tuned toward well-known public test sets, so a high headline number does not reliably predict performance on a team's actual, messy, long-horizon coding work.

This repo measures the thing that actually matters instead: **harness x model, on real agentic software-engineering tasks against real repositories**, reporting all three axes a buyer trades off -- **cost, latency, and accuracy**. Crossing harnesses with models gives real **optionality**: the same model can be a few points more accurate under one agent yet several times cheaper and faster under another (see the [cross-harness comparison](docs/agentic-coding-swe-comparison-swe3.md)). With those numbers in hand, an organization can make an **informed, defensible decision** about the cost/latency/accuracy trade-off for its own workload -- and, very often, **lower its coding bill substantially** by picking a cheaper harness-and-model pairing that is more than good enough, rather than defaulting to the most expensive option. That is the deliverable: an evidence base for smart, budget-aware choices on work that looks like yours, not like a leaderboard.

## Overview

This repository is a **benchmark and harness for measuring how well different LLMs perform real-world software-engineering tasks** when driven by a coding agent. It supports **four coding agents (harnesses)** today -- [Claude Code](https://docs.anthropic.com/en/docs/claude-code), Anthropic's command-line coding agent; [pi](https://github.com/earendil-works/pi-coding-agent), a lightweight open-source agent; [omp](https://omp.sh) (oh-my-pi), a fork of pi; and [kiro-cli](https://kiro.dev) (the successor to the Amazon Q Developer CLI), which drives Kiro's own managed, Amazon Bedrock-backed models -- with [opencode](https://opencode.ai) being added soon. Claude Code and pi are each wired to run with a model hosted in any of **three different places**, so you can put many models through the *same* tasks with the *same* harness and compare them directly on both quality and cost; kiro-cli instead runs Kiro's managed models directly (it cannot target a self-hosted endpoint -- see [kiro-cli setup](docs/kiro-cli-setup.md)). Pick the harness per run with `--agent claude` (default), `--agent pi`, `--agent omp`, or `--agent kiro`, and the skill with `--skill swe2`/`--skill swe3`; results are kept separate on disk (`<model>/<harness>/<skill>/<repo>/<task>`) so neither the agents nor the two skills ever overwrite each other.

It runs **two complementary benchmarks**, and combining them is the whole point:

1. **Quality** -- how well a model actually does a real coding task (scored 0-100 by an independent LLM judge).
2. **Throughput** -- how many tokens per second a self-hosted model sustains on a given GPU instance, which turns the instance's hourly price into a **hardware-derived cost per task**.

Quality alone tells you which model is best; cost alone tells you which is cheapest. Plotting one against the other yields the **cost/quality Pareto frontier** (the chart below) -- the set of models where nothing else is both better *and* cheaper. That frontier is the deliverable: it is what lets you choose a model for a real budget, and it exists only because this repo measures both halves.

**Crucially, the two benchmarks must be combined over the *real agentic coding tasks*, not over a synthetic input:output token ratio.** Agentic coding is a **prefill-heavy, long-horizon** workload: each task replays a large, growing transcript as fresh input on every turn and emits a comparatively tiny edit, so the real input:output ratio runs ~150:1 up to ~660:1 -- far more lopsided than the ~3:1 or ~4:1 assumed by generic pricing. A model's cost per task therefore depends on *how* it drives the task (how many turns, how much context it re-reads, whether prefix caching hits), which a lab-style token-count estimate cannot capture. This repo measures throughput on that same prefill-heavy shape and multiplies it by the tokens each real run actually processed, so the cost on the frontier is the cost of the *work as it happens* -- see [cost-per-task-methodology.md](docs/cost-per-task-methodology.md).

**Where this is headed:** the frontier is the lookup table for a coding harness that, given a task, **automatically routes to the right model** -- plan with a frontier model, execute with a cheaper workhorse or budget model, and switch back up when a run needs it -- so a developer gets frontier-quality results at a fraction of the cost without ever managing model selection. See [the vision](docs/vision.md), and the concrete first step, [`/swe-auto` (#123)](https://github.com/aarora79/agentic-coding-harness-benchmarks/issues/123) -- a router skill that triages a task, consults this frontier, and runs the chosen model.

**This is not a static, single-shot benchmark.** Most model evaluations measure one prompt and one response. Here the unit of work is a **long-horizon, multi-turn agentic task**: the model drives Claude Code through an open-ended tool-use loop -- reading files, editing code, running commands, and reacting to results over **tens to hundreds of LLM turns** (typically ~50-250, up to 300+) that run **anywhere from ~10 minutes to over an hour** per task. What we measure is whether a model can *sustain* coherent engineering work across that horizon -- staying on task, using tools correctly, and landing a working change -- not whether it can answer a single question well. That is a fundamentally different (and harder) thing to be good at, and it is where models that look similar on conventional benchmarks pull apart.

Each task points the agent at a real GitHub repository and a real problem. The agent works the task **non-interactively** through the `/swe2` skill, which lands six artifacts on disk -- four design docs (`github-issue.md`, `lld.md`, `review.md`, `testing.md`) plus the implemented change (`patch.diff`, `implementation.md`). The harness records what the run cost -- token usage, latency, and the number of LLM turns -- and a separate [judge](benchmarks/docs/harness-reference.md#scoring-the-artifacts-the-judge) scores the artifacts for quality. Run the same task across models and the resulting `metrics.json` / `eval.json` files line up side by side.

## Results: a worked example

To show what the harness produces, we ran it against [agentic-community/mcp-gateway-registry](https://github.com/agentic-community/mcp-gateway-registry) at tag `1.24.4` -- **5 real tasks**, each scored 0-100 by an independent LLM judge, across **16 models** on the Claude Code and pi harnesses (plus **5 models** on the newer [kiro-cli](docs/harness-kiro-cli-swe3.md) harness, and `qwen3.8-27b` a second time on [omp](docs/harness-omp-swe3.md)). The flagship view below is the **cost/quality Pareto frontier** for the single-agent `/swe3` skill, **merged across harnesses**: mean cost per task (x) against mean task score (y), one point per model, with the non-dominated frontier highlighted. Each model is plotted at its **best harness** -- decided by Pareto dominance, and by cost-per-point where neither harness dominates (the rule, and every runner-up it set aside, are in [best-harness-selection.md](docs/best-harness-selection.md)). Marker shape says which harness won.

![Cost vs. quality Pareto frontier, best harness per model on /swe3](docs/images/cost-quality-combined-swe3.png)

> **What is a Pareto frontier, and what does it mean here?** The frontier is the set of models where **no other model is both higher-scoring _and_ cheaper**. Those are the only models worth considering; everything else is *dominated* -- some frontier model beats it on both axes, so there is never a reason to pick it. Concrete example from this chart: **`deepseek-v3.2` (54/100, $1.71/task) dominates `qwen3-coder-480b` (44/100, $3.11/task)** -- deepseek scores *higher* and costs *less* (both self-hosted, so the dollars are like-for-like), so qwen3-coder-480b is off the frontier. Merging the harnesses adds a sharper one: **`qwen3.8-27b` on omp (70.3/100, $3.49/task) dominates `claude-sonnet-5` on pi (66.5/100, $3.81/task)** -- a 27B open-weight model on a single GPU, beating a frontier API model on both axes at once. Reading it is a two-step decision: pick the quality level your task needs on the y-axis, then take the **leftmost (cheapest) model on the frontier at that level**. (Costs come in two non-comparable bases -- metered Bedrock bills vs hardware-derived self-hosted figures -- so we also draw the honest frontier *within* each hosting basis; see the results docs.)

**claude-opus-5** tops quality (75.7/100). The best open-weight result is a near tie -- **glm-5.2** at 70.8 and **qwen3.8-27b** at 70.3 -- but they cost very different things to get: glm-5.2 is a 744B MoE on 8x H200 at $5.98/task, qwen3.8-27b a 27B dense model on a **single L40S** at $3.49/task. Both sit on the frontier. The full story -- task-by-task tables, per-model leaderboard, hardware, footnotes, the cost methodology, and the model-tier buying guidance -- is split by skill:

- **[Results -- /swe3 (single-agent)](docs/results-swe3.md)** -- the primary results view (pi harness), 16 models.
- **[Results -- /swe2 (multi-agent)](docs/results-swe2.md)** -- the multi-agent skill (Claude Code harness), 14 models.
- **[Cross-harness comparison (/swe3)](docs/agentic-coding-swe-comparison-swe3.md)** -- Claude Code vs pi on the same models: per-metric win tallies and the model-tier buying guidance (which model for which job, and which harness).

Path 1 (Anthropic on Bedrock) and Path 3 (self-hosted on vLLM) are measured; Path 2 (open-weight on Bedrock via LiteLLM) is [fully implemented](benchmarks/docs/path-open-weight-on-bedrock-litellm.md) but has no published run yet. The `mcp-gateway-registry` dataset ships in [benchmarks/dataset/](benchmarks/dataset/mcp-gateway-registry.yaml) so you can reproduce the run; generated artifacts are not committed.

> **The example repo is the example, not the contract.** `/swe3` works against any GitHub URL -- clone the target you actually care about, write the task description, and run.

### Results by harness and skill

The same models can be driven by different coding agents (harnesses), and each harness can run more than one SWE skill (`swe2`, the multi-agent skill, vs `swe3`, the single-agent skill) -- token consumption and accuracy differ enough that results are kept per (harness, skill). Each combination has its own generated results document (a running table plus cost-quality and quality-radar charts); the two cross-harness comparison docs put Claude Code and pi head to head per skill.

| Skill | Results write-up | Cross-harness comparison | Per-harness generated docs |
|---|---|---|---|
| `/swe3` (single-agent) | [results-swe3.md](docs/results-swe3.md) | [comparison](docs/agentic-coding-swe-comparison-swe3.md) | [Claude Code](docs/harness-claude-code-swe3.md) · [pi](docs/harness-pi-swe3.md) · [omp](docs/harness-omp-swe3.md) · [kiro-cli](docs/harness-kiro-cli-swe3.md) |
| `/swe2` (multi-agent) | [results-swe2.md](docs/results-swe2.md) | [comparison](docs/agentic-coding-swe-comparison-swe2.md) | [Claude Code](docs/harness-claude-code-swe2.md) · [pi](docs/harness-pi-swe2.md) |

**kiro-cli** ([#73](https://github.com/aarora79/agentic-coding-harness-benchmarks/issues/73)) has landed as a third harness (`/swe3`, 5 models -- see [its results](docs/harness-kiro-cli-swe3.md) and [setup/cost notes](docs/kiro-cli-setup.md)); it drives Kiro's managed Bedrock-backed models and is priced on a distinct **Kiro-credit** basis (see the [cost methodology](docs/cost-per-task-methodology.md)). [opencode](https://opencode.ai) ([#72](https://github.com/aarora79/agentic-coding-harness-benchmarks/issues/72)) is coming.

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

The `/swe2` and `/swe3` skills land **six artifacts** -- four design docs plus the implemented change (`patch.diff`, `implementation.md`) -- but they do **not** run tests or open PRs; whether the design and code are any good is the downstream evaluation the judge (or a human) performs on the artifacts. Full mechanics are in the [harness reference](benchmarks/docs/harness-reference.md).

> **"SWE" here means software engineering in general -- not [SWE-bench](https://www.swebench.com/), the specific benchmark dataset.** The `/swe` skill lets you run any model against any task in any repo of your choosing. It is a *harness*, not a fixed benchmark set: compare results across models on the same task, or a single model across tasks of varying difficulty.

## Datasets

A dataset is a single YAML file: a metadata header plus a list of tasks, each pointing at a GitHub repo and a problem. Two datasets ship in [benchmarks/dataset/](benchmarks/dataset/):

- [hello-world.yaml](benchmarks/dataset/hello-world.yaml) -- a trivial sanity dataset (the [octocat/Hello-World](https://github.com/octocat/Hello-World) repo) for kicking the tires of a new model or endpoint.
- [mcp-gateway-registry.yaml](benchmarks/dataset/mcp-gateway-registry.yaml) -- the reference dataset, whose tasks are drawn from real upstream issues in [agentic-community/mcp-gateway-registry](https://github.com/agentic-community/mcp-gateway-registry).

**Nothing in the harness is specific to a particular repository.** Adding your own benchmark dataset is just writing another YAML file in the same format -- point tasks at any public repo and pinned ref. The dataset format is documented in the [harness reference](benchmarks/docs/harness-reference.md#the-dataset).

### What do I do with this?

The point of this repo is to help you **pick the right coding agent and model for your tasks** -- the pairing that lands the quality you need at the cost and latency you can live with, instead of defaulting to the most expensive option. There are two ways to get there:

1. **Use the frontier we already published.** The cost/quality results here (across harnesses, models, and hosting paths) are a strong, ready-made baseline -- read the [harness comparison](docs/agentic-coding-swe-comparison-swe3.md) and per-harness docs and pick from the models on the frontier. No runs of your own required.
2. **Build your own frontier on your own code.** When you want numbers on **work that looks like yours** rather than our example repo, use the benchmarking harness in this repo: write a dataset YAML pointing at your repositories and run it -- the models, harnesses, judge, and cost math are identical to what produced the results above. This is the rest of this section.

**We are also working on making this automatic.** [`/swe-auto` (#123)](https://github.com/aarora79/agentic-coding-harness-benchmarks/issues/123) is a planned router skill that will triage a task, consult the cost/quality frontier, and **select and run the right model for the job for you** -- so you get frontier-quality results at a fraction of the cost without managing model selection by hand.

### Benchmark your own code repositories

This is option 2 above -- building your own frontier on your own code. It is a few steps:

1. **Create a dataset file** under [benchmarks/dataset/](benchmarks/dataset/), e.g. `my-team.yaml`. Copy [mcp-gateway-registry.yaml](benchmarks/dataset/mcp-gateway-registry.yaml) as a template. Minimal shape:

   ```yaml
   schema_version: "1.0"
   name: my-team
   title: My team's benchmark
   description: Real tasks from our own repositories.
   default_ref: main                      # pin a tag/commit per task for reproducibility
   metrics: [input_tokens, output_tokens, num_turns]
   complexity_levels: [low, medium, high]
   tasks:
     - id: add-rate-limiting-to-gateway
       repo: https://github.com/your-org/your-repo
       ref: v2.3.0                         # pin so every run clones the same code
       complexity: medium
       tags: [python, api, feature]
       problem_statement: |
         Describe the task in enough detail for an agent to act on it without
         you present -- what to change, constraints, and what "done" means.
   ```

   Each task points at a repo + pinned ref + a problem statement (from a real ticket or issue). Full field reference: [harness reference -> The dataset](benchmarks/docs/harness-reference.md#the-dataset). Any repo the runner can `git clone` works (public, or private with credentials available to your shell).

2. **Run it** against whichever model/harness/path you want -- same commands as the example, just swap the dataset:

   ```
   /benchmark provider=bedrock model=claude-opus-5 dataset=dataset/my-team.yaml
   ```

   or headless: `benchmarks/scripts/run-e2e-benchmark.sh --provider bedrock --model ... --dataset dataset/my-team.yaml`. Pick the harness with `--agent claude|pi|kiro` and the skill with `--skill swe2|swe3` (`--agent kiro` drives Kiro's managed models and sets `--provider kiro` automatically).

3. **Read your results.** Artifacts and scores land under `benchmarks/swe-benchmark-data/<model>/<harness>/<skill>/<your-dataset-repo>/<task>/`, and the same generators build your own cost/quality frontier (`gen_swe_comparison.py`, `plot_cost_quality.py`). Your runs are gitignored, so a customer's private code never lands in version control.

> **Tips for good tasks:** pin a `ref` so reruns are comparable; write the `problem_statement` like a well-scoped ticket; use `tags` to slice results by language/domain/change-type; and add optional `ground_truth` (reviewer-only, never shown to the agent) if you want the judge to check against a known-good approach.

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

## Documentation map

Where to read more, by topic:

| Document | What it covers |
|----------|----------------|
| [docs/results-swe3.md](docs/results-swe3.md) / [docs/results-swe2.md](docs/results-swe2.md) | Full benchmark results per skill: task-by-task tables, per-model leaderboard, cost/quality frontier, hardware, and what the data says. |
| [docs/vision.md](docs/vision.md) | The north star: a cost-aware harness that routes each task (and each phase) to the right model on the frontier -- frontier / workhorse / budget -- switching automatically. |
| [benchmarks/README.md](benchmarks/README.md) | The benchmark harness landing page: the three hosting paths, how a run works, and how to reproduce the results above. |
| [benchmarks/docs/harness-reference.md](benchmarks/docs/harness-reference.md) | Full harness reference: config, the `/swe2` flow, context-window/auto-compaction, and the LLM-as-judge scoring. |
| [docs/agentic-coding-swe-comparison-swe3.md](docs/agentic-coding-swe-comparison-swe3.md) | Claude Code vs pi on the same models and tasks (per skill): per-metric win tallies, the cost/quality frontier, and hand-authored model-tier buying guidance. Claude Code is a few points more accurate on some models; pi is far more token-efficient (and thus faster and, when self-hosting, cheaper). See the [per-skill results docs](#results-by-harness-and-skill) for each agent's full table and charts. |
| [benchmarks/docs/path-anthropic-on-bedrock.md](benchmarks/docs/path-anthropic-on-bedrock.md) | Path 1 setup: benchmarking the Anthropic family (Claude Opus/Sonnet/Haiku) directly on Amazon Bedrock. |
| [benchmarks/docs/path-open-weight-on-bedrock-litellm.md](benchmarks/docs/path-open-weight-on-bedrock-litellm.md) | Path 2 setup: open-weight models on Amazon Bedrock through the LiteLLM proxy. |
| [benchmarks/docs/path-self-hosted-vllm.md](benchmarks/docs/path-self-hosted-vllm.md) | Path 3 setup: self-hosting a model on vLLM and pointing the harness at it. |
| [docs/kiro-cli-setup.md](docs/kiro-cli-setup.md) | The kiro-cli harness: install, sign-in, headless use, the Bedrock-managed-only constraint, and how its Kiro-credit spend is calculated. Results: [harness-kiro-cli-swe3.md](docs/harness-kiro-cli-swe3.md). |
| [benchmarks/docs/end-to-end-self-hosted-run.md](benchmarks/docs/end-to-end-self-hosted-run.md) | The full manual run-book for an end-to-end self-hosted benchmark. |
| [self-hosted/vllm/README.md](self-hosted/vllm/README.md) | Standing up a vLLM server: install, tensor parallelism, tool-call parsers, and the serving-config reference. |
| [self-hosted/vllm/models/](self-hosted/vllm/models/) | Per-model serving guides (HF repo, context window, TP size, tool parser, hardware fit) for every benchmarked model. |
| [docs/agentic-coding-throughput-comparison.md](docs/agentic-coding-throughput-comparison.md) | Serving-economics comparison across models: throughput, saturation, and hardware-derived cost per token / per task. |
| [docs/cost-per-task-methodology.md](docs/cost-per-task-methodology.md) | How the cost numbers are derived: the two cost lenses, prompt-caching accounting (API vs self-hosted), and why agentic coding is prefill-bound. |
| [docs/serving-optimization-notes.md](docs/serving-optimization-notes.md) | Portable vLLM serving defaults and why we do not tune the prefill knobs per model. |
| [CONTRIBUTING.md](CONTRIBUTING.md) / [SECURITY.md](SECURITY.md) / [SUPPORT.md](SUPPORT.md) | How to contribute, report a vulnerability, and get help. |

## See also

- [Claude Code docs](https://docs.anthropic.com/en/docs/claude-code) -- official Claude Code documentation
- [benchmarks/README.md](benchmarks/README.md) -- the harness landing page
- [self-hosted/vllm/README.md](self-hosted/vllm/README.md) -- standing up a self-hosted vLLM server (Path 3)

## License

This library is licensed under the MIT-0 License. See the [LICENSE](LICENSE) file.
