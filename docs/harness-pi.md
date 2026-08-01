# Results: pi harness

Benchmark results for every model run under the **pi** coding agent on `mcp-gateway-registry`, generated from the committed `run-summary.json` files. Regenerate with `uv run scripts/gen_agent_report.py --harness pi`. Companion to the cross-agent [harness comparison](harness-comparison.md).

## Results by model

| Model | Mean score | Completed | Total tokens | Wall-clock | Run cost* |
|---|---:|---:|---:|---:|---:|
| qwen3.6-35b | 47.15 | 4/5 | 627,404 | 29.4m | $5.14 |
| gemma-4-31b | 43.52 | 5/5 | 600,667 | 60.8m | $10.63 |
| qwen3-coder-30b | -- (0 scored) | 0/5 | 410,050 | 17.0m | $2.98 |

\* Run cost is the whole 5-task run, hardware-derived at g6e.12xlarge on-demand ($10.49/hr): `($/hr / 3600) x wall-clock seconds`. On a rented GPU there is no per-token bill, so time is the cost -- see [cost-per-task-methodology.md](cost-per-task-methodology.md).

A task scoring 0 (missing/empty artifacts) is a model failure, excluded from the mean but counted in `Completed`. A model with 0 scored tasks did not complete any task under this harness.

## Charts

### Cost vs. quality (Pareto frontier)

![Cost vs quality, pi harness](images/cost-quality-pi.png)

### Quality by dimension (radar)

![Quality radar, pi harness](images/quality-radar-pi.png)
