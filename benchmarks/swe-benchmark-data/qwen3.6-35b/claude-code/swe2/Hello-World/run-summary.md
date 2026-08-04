# Benchmark run summary: qwen3.6-35b on Hello-World

- Model: qwen3.6-35b
- Agent (harness): claude
- Skill: swe2
- Provider: endpoint
- Dataset scope: Hello-World (1 tasks, ref master)
- Serving: instance_type=g6e.12xlarge, context_window=200000

1 of 1 tasks scored; no failures.

## Results

| Task | Artifacts | Turns | Prefix-cache | Cost (est $) | Judge score |
|---|---|---|---|---|---|
| add-contributing-guide | 6/6 | 41 | 83.5% | 11.53 | 73.8 |

Mean over the 1 completed tasks: 73.8 (mean cost $11.53). A 0-score task is a model failure (missing artifacts) and is excluded from the means, pending investigation. Cost is a token-based estimate for self-hosted models.
