# Benchmark run summary: us.anthropic.claude-opus-5-5 on Hello-World

- Model: us.anthropic.claude-opus-5-5
- Agent (harness): omp
- Skill: swe3
- Provider: bedrock
- Dataset scope: Hello-World (1 tasks, ref master)
- Serving: instance_type=g6e.4xlarge
- Run date: 2026-10-10

1 of 1 tasks scored; no failures.

## Results

| Task | Artifacts | Turns | Prefix-cache | Cost (est $) | Judge score |
|---|---|---|---|---|---|
| add-contributing-guide | 6/6 | 18 | -- | 1.19 | 91.6 |

Mean over the 1 completed tasks: 91.6 (mean cost $1.19). A 0-score task is a model failure (missing artifacts) and is excluded from the means, pending investigation. Cost is a token-based estimate for self-hosted models.
