# Benchmark run summary: qwen3-coder-30b on Hello-World

- Model: qwen3-coder-30b
- Agent (harness): omp
- Skill: swe3
- Provider: endpoint
- Dataset scope: Hello-World (1 tasks, ref master)
- Serving: instance_type=g6e.12xlarge, context_window=200000
- Run date: 2026-08-29

1 of 1 tasks scored; no failures.

## Results

| Task | Artifacts | Turns | Prefix-cache | Cost (est $) | Judge score |
|---|---|---|---|---|---|
| add-contributing-guide | 6/6 | 33 | 97.1% | -- | 59.0 |

Mean over the 1 completed tasks: 59.0 (mean cost $None). A 0-score task is a model failure (missing artifacts) and is excluded from the means, pending investigation. Cost is a token-based estimate for self-hosted models.
