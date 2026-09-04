# Results

The headline run, and every earlier run kept as background. Results are held per (harness, skill, dataset), and scores from different task sets do not merge.


The headline run is the **omp** harness driving the single-agent `/swe3` skill over the **`mcp-gateway-registry-v2`** dataset: 21 tasks, 16 models, every task scored 0-100 by an independent judge. Each task comes from a closed issue in [agentic-community/mcp-gateway-registry](https://github.com/agentic-community/mcp-gateway-registry), pinned to the release *before* the fix shipped, so the defect is present in the tree the agent clones. The tasks span four complexity tiers, so the results split by how hard the work is.

This repo also holds earlier runs on other harnesses, skills and datasets -- Claude Code and pi on the 5-task v1 dataset, kiro-cli, and the multi-agent `/swe2` skill. Those stay published as background. They use different task sets, so their scores do not line up with the table below and must not be merged into it.

![Cost vs. quality Pareto frontier, omp harness on /swe3](images/cost-quality-omp-swe3.png)

> **What is a Pareto frontier, and what does it mean here?** The frontier is the set of models where **no other model is both higher-scoring _and_ cheaper**. Those are the only models worth considering; everything else is *dominated*, so there is never a reason to pick it. From this chart: **`qwen3.8-27b` (78.48, $1.47/task) dominates `claude-sonnet-5` (76.97, $4.67/task)** -- a 27B open-weight model outscores a frontier API model at under a third of the cost. Read it in two steps: pick the quality you need on the y-axis, then take the cheapest model on the frontier at that level. Costs come in two bases that do not compare as raw dollars -- metered Bedrock bills against hardware-derived self-hosted figures -- so the results docs also draw the frontier within each basis.

**claude-opus-5 tops quality at 82.83 for $11.95 a task.** `glm-5.3` comes within 1.6 points at 81.27 for $8.09. The cheapest way to reach the high 70s is `qwen3.8-27b`: 78.48 for **$1.47 a task**. At the other end, `qwen3.6-35b` scores 59.24 for **26 cents**. Every self-hosted figure is priced on one basis -- the p5en.48xlarge sweep -- so the fleet compares like for like even where a model was served on a smaller box; a figure is the cost of that model's work on p5en, not a quote for the box it ran on.

Within the metered Bedrock rows alone the frontier is `claude-haiku-4-5` ($0.76, 56.18), `claude-opus-4-5` ($4.18, 66.32), `claude-sonnet-5` ($4.67, 76.97) and `claude-opus-5` ($11.95, 82.83). Three Opus builds fall off it: Sonnet 5 beats `claude-opus-4-7` (75.60, $7.35), `claude-opus-4-8` (74.69, $5.32) and `claude-opus-4-6-v1` (70.64, $4.95) on score and on price.

- **[omp harness, /swe3, v2 dataset](harness-omp-swe3.md)** -- the headline table above, 16 models, with the quality radar and the cost-accuracy view.
- **[Which model for which task?](model-selection-by-complexity.md)** -- what a model upgrade buys you at each difficulty tier.
- **[Cost per task, and why the two bases differ](cost-per-task-methodology.md)** -- how a fixed instance price becomes a cost per token and per task.

Background runs, on other datasets and harnesses:

- **[Results -- /swe3 on the v1 dataset](results-swe3.md)** -- 5 tasks, 16 models, pi harness.
- **[Results -- /swe3 on v2](results-swe3-v2.md)** -- the v2 dataset under the earlier harnesses.
- **[Results -- /swe2 (multi-agent)](results-swe2.md)** -- the multi-agent skill, Claude Code harness, 14 models.
- **[Cross-harness comparison (/swe3)](agentic-coding-swe-comparison-swe3.md)** -- Claude Code against pi on the same models.

Path 1 (Anthropic on Bedrock) and Path 3 (self-hosted on vLLM) have published runs. Path 2 (open-weight on Bedrock via LiteLLM) [works](../benchmarks/docs/path-open-weight-on-bedrock-litellm.md) but nobody has run it yet. Both datasets ship in [benchmarks/dataset/](../benchmarks/dataset/) so you can reproduce a run; generated artifacts are not committed.

> **The example repo is the example, not the contract.** `/swe3` works against any GitHub URL -- clone the target you care about, write the task description, and run.

## Results by harness and skill

One model can be driven by different coding agents (harnesses), and each harness runs either SWE skill (`swe2`, the multi-agent one, or `swe3`, the single-agent one). Token use and accuracy differ enough that results are kept per (harness, skill), each with its own generated document: a table plus cost-quality and quality-radar charts. **The reported result is omp with `/swe3` on the v2 dataset**; the rest of this table is earlier work on other datasets, kept for reference and not comparable with it.

| Skill | Results write-up | Cross-harness comparison | Per-harness generated docs |
|---|---|---|---|
| `/swe3` (single-agent) | [results-swe3.md](results-swe3.md) | [comparison](agentic-coding-swe-comparison-swe3.md) | [Claude Code](harness-claude-code-swe3.md) · [pi](harness-pi-swe3.md) · [omp](harness-omp-swe3.md) · [kiro-cli](harness-kiro-cli-swe3.md) |
| `/swe2` (multi-agent) | [results-swe2.md](results-swe2.md) | [comparison](agentic-coding-swe-comparison-swe2.md) | [Claude Code](harness-claude-code-swe2.md) · [pi](harness-pi-swe2.md) |

**kiro-cli** ([#73](https://github.com/aarora79/agentic-coding-harness-benchmarks/issues/73)) has landed as a third harness (`/swe3`, 5 models -- see [its results](harness-kiro-cli-swe3.md) and [setup/cost notes](kiro-cli-setup.md)); it drives Kiro's managed Bedrock-backed models and is priced on a distinct **Kiro-credit** basis (see the [cost methodology](cost-per-task-methodology.md)). [opencode](https://opencode.ai) ([#72](https://github.com/aarora79/agentic-coding-harness-benchmarks/issues/72)) is coming.

---

[< Back to the README](../README.md)
