# Benchmark run summary: qwen3.6-35b on Hello-World

- Model: qwen3.6-35b
- Agent (harness): pi
- Skill: swe2
- Provider: endpoint
- Dataset scope: Hello-World (1 tasks, ref master)
- Serving: instance_type=g6e.12xlarge

1 of 1 tasks scored; no failures.

## Results

| Task | Artifacts | Turns | Prefix-cache | Cost (est $) | Judge score |
|---|---|---|---|---|---|
| add-contributing-guide | 6/6 | 20 | 92.5% | -- | 68.2 |

Mean over the 1 completed tasks: 68.2 (mean cost $None). A 0-score task is a model failure (missing artifacts) and is excluded from the means, pending investigation. Cost is a token-based estimate for self-hosted models.
