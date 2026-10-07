# The Strands harness agent

`--agent strands-harness` runs a benchmark task with the Strands team's [`create_harness()`](https://strandsagents.com/docs/user-guide/harness/), a preconfigured coding agent from the `strands-harness` package. On Claude Haiku 4.5 it scored 56.05 on the 21-task v2 dataset, level with omp (56.18) and 4.85 points above the repo's hand-built Strands agent, at $0.70 a task.

## How it differs from `--agent strands`

Both agents run in [strands_agent_runner.py](../benchmarks/scripts/strands_agent_runner.py) and share its event stream, token accounting, pricing, recursion limit and loop guard. They differ in how the runner builds the agent:

| | `--agent strands` | `--agent strands-harness` |
|---|---|---|
| Agent | a hand-built `strands.Agent` | `create_harness()` with web tools, subagents, memory and sessions off |
| Tools | `shell`, `file_editor` | `shell`, `read`, `write`, `edit`, `todo_write`, plus a `bash` alias |
| Large tool results | cut at 100,000 characters by the runner | offloaded to disk by the harness, with `retrieve_offloaded_content` to read them back |
| Older turns | `SummarizingConversationManager` | the harness's context manager |
| System prompt | the runner's own | the harness's contract, with the runner's notes appended |
| Results folder | `<model>/strands/` | `<model>/strands-harness/` |

[strands-setup.md](strands-setup.md#the-strands-harness---agent-strands-harness) lists every harness setting the runner keeps or turns off, and why.

## Running it

The `strands` dependency group installs both packages, and the e2e script installs the group when it is missing:

```bash
cd benchmarks
./scripts/run-e2e-benchmark.sh --provider bedrock \
  --model us.anthropic.claude-haiku-4-5-20251001-v1:0 \
  --dataset dataset/mcp-gateway-registry-v2.yaml --agent strands-harness --skill swe3
```

The same flag works with `--provider vllm`, which the MiniCPM5-2B run used, and `run-multi-model-benchmark.sh` accepts it too.

## Results so far

| Model | omp | `--agent strands` | `--agent strands-harness` |
|---|---|---|---|
| claude-haiku-4-5 | 56.18, 21/21, $0.76 | 51.20, 20/21, $0.70 | 56.05, 21/21, $0.70 |
| minicpm5-2b | 42.59, 19/21 | 45.28, 21/21 | 41.91, 20/21 |

Each cell is the mean score, the tasks scored and, for Bedrock, the cost per task, from each harness's `run-summary.json` under `benchmarks/swe-benchmark-data/<model>/`. Per-task tables and charts: [harness-strands-harness-swe3.md](harness-strands-harness-swe3.md). The MiniCPM5-2B harness run predates the loop guard, and two of its tasks looped; one of them used most of its tokens and ended at the recursion limit with no artifacts.

## Which one to use

Use `--agent strands-harness` to measure Strands as its team recommends using it. On Haiku 4.5 it finished every task and matched omp, and its offloading removed the large-tool-result failures that cost the hand-built agent tasks on a 128K-token window. Use `--agent strands` to compare against earlier Strands results, which all ran on the hand-built agent.

## Related

- [strands-setup.md](strands-setup.md): installing Strands, credentials and routing, token accounting, and every place the runner departs from Strands as it ships.
- [harness-strands-swe3.md](harness-strands-swe3.md): results for `--agent strands`.
