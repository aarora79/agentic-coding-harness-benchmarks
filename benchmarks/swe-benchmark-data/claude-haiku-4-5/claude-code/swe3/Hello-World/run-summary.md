# Benchmark run summary: us.anthropic.claude-haiku-4-5-20251001-v1:0 on Hello-World

- Model: us.anthropic.claude-haiku-4-5-20251001-v1:0
- Agent (harness): claude
- Skill: swe3
- Provider: bedrock
- Dataset scope: Hello-World (1 tasks, ref master)
- Serving: instance_type=g6e.12xlarge

1 of 1 tasks scored; no failures.

## Results

| Task | Artifacts | Turns | Prefix-cache | Cost (est $) | Judge score |
|---|---|---|---|---|---|
| add-contributing-guide | 6/6 | 18 | -- | 0.24 | 61.0 |

Mean over the 1 completed tasks: 61.0 (mean cost $0.24). A 0-score task is a model failure (missing artifacts) and is excluded from the means, pending investigation. Cost is a token-based estimate for self-hosted models.
