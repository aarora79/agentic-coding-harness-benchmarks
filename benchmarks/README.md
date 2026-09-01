# Benchmark harness

This directory holds the benchmark harness that drives [Claude Code](https://docs.claude.com/en/docs/claude-code) through real-world software-engineering tasks non-interactively, records what each run cost (tokens, latency, turns), and scores the artifacts it produces for quality.

For the concepts -- what the benchmark measures, the three model-hosting paths, the run flow, and the worked-example results -- start at the [top-level README](../README.md).

## Layout

```
benchmarks/
├── config/    # runner.example.yaml, and litellm-mantle.yaml for the Path 2 proxy
├── dataset/   # benchmark dataset YAML files (hello-world, mcp-gateway-registry)
├── docs/      # the shared harness reference and one setup guide per hosting path
├── scripts/   # the run harness, dataset/config loaders, the judges, the proxy launcher
├── tests/     # unit tests
└── swe-benchmark-data/  # artifacts + metrics.json + eval.json from runs (worked example)
```

## Where to go next

- **[docs/harness-reference.md](docs/harness-reference.md)** -- the shared mechanics used by every path: prerequisites, the dataset format, the dataset loader, the runner config, running the harness, the metrics file, the judge, and the development workflow.
- **Pick a hosting path** (each guide ends with a copy-pasteable run command):
  - [docs/path-anthropic-on-bedrock.md](docs/path-anthropic-on-bedrock.md) -- Path 1: Anthropic models directly on Amazon Bedrock.
  - [docs/path-open-weight-on-bedrock-litellm.md](docs/path-open-weight-on-bedrock-litellm.md) -- Path 2: open-weight models on Amazon Bedrock via a LiteLLM proxy.
  - [docs/path-self-hosted-vllm.md](docs/path-self-hosted-vllm.md) -- Path 3: self-hosted open-weight models on EC2 with vLLM.
- **[docs/end-to-end-self-hosted-run.md](docs/end-to-end-self-hosted-run.md)** -- a full run-book that ties Path 3 together end to end: pre-flight checks, serve the model, capture GPU metrics into DuckDB, run the benchmark, and score with the judge.

## One-command end-to-end run

The whole flow -- pre-flight and error checks (including clearing stale artifact folders that would stall the headless run), the benchmark harness over a dataset, and the codex judge -- runs behind three inputs: `provider` (`bedrock` | `litellm` | `vllm`), `model`, and `dataset`.

**Recommended: the `/benchmark` skill.** Run it from Claude Code to drive the run interactively -- it prompts for the three inputs and walks each step, printing the tail/status command to watch. For the **vllm** path it also manages the backing service: it checks the HuggingFace token, (re)starts the vLLM server on the requested model (stopping any other model first) using that model's guide at its largest context window, starts the DuckDB metrics collector, and at the end stops the collector and archives its snapshot tagged with model/scope/timestamp.

```
/benchmark provider=vllm model=qwen3.6-35b dataset=dataset/mcp-gateway-registry.yaml
```

**Headless: [scripts/run-e2e-benchmark.sh](scripts/run-e2e-benchmark.sh).** The same flow as a script, failing loudly at the first problem. It does *not* start the vLLM server or the LiteLLM proxy -- bring those up first (they are long-lived services).

```bash
cd benchmarks
./scripts/run-e2e-benchmark.sh --provider vllm --model qwen3-coder-30b \
    --dataset dataset/mcp-gateway-registry.yaml --yes
./scripts/run-e2e-benchmark.sh --help
```

## Many models in one batch

[scripts/run-multi-model-benchmark.sh](scripts/run-multi-model-benchmark.sh) runs the same end-to-end flow over several self-hosted models back to back, serving each in turn from its own model registry. It self-detaches, so a session teardown cannot kill a multi-hour run.

```bash
cd benchmarks
./scripts/run-multi-model-benchmark.sh qwen3-coder-30b gemma-4-31b --agent omp --skill swe3
./scripts/run-multi-model-benchmark.sh --help   # prints the model catalog
```

**When the judge runs is a knob, and it matters for wall-clock.** Generation runs on your GPUs; the codex judge is an Amazon Bedrock call that uses no GPU at all. `--judge-mode` decides whether those two overlap:

| Mode | Behavior | Use when |
|---|---|---|
| `inline` (default) | Judge each model right after it generates. | One model, or you want each result final before the next starts. |
| `async` | Judge in the background **while the next model generates**. | A multi-model batch. Judging is roughly 50 minutes per 21-task model, and this hides essentially all of it. |
| `skip` | Harness only; score later. | The judge is unavailable, or you want to score on another machine. |

`async` keeps judge, summarize, and commit together as one background unit, so a run-summary is never committed before its scores exist. Only one judge runs at a time: every model in a batch judges the same dataset, so concurrent judges would collide on the same `/tmp/swe-judge-repos` checkout. The run waits for outstanding judging before reporting `ALL DONE`, and exits non-zero naming any model whose judging failed.

Score a `skip`ped run later with:

```bash
cd benchmarks/scripts && uv run python codex_judge.py --recursive --no-overwrite \
    --folder ../swe-benchmark-data/{model-slug}/{harness}/{skill}/{scope}
uv run python summarize_run.py --folder ../swe-benchmark-data/{model-slug}/{harness}/{skill}/{scope}
```

## Quick start

```bash
cd benchmarks
uv sync
cp config/runner.example.yaml config/runner.yaml
# then follow one of the path guides above
```
