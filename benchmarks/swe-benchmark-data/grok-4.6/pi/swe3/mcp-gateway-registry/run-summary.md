# Benchmark run summary: us.xai.grok-4.6 on mcp-gateway-registry

- Model: us.xai.grok-4.6
- Agent (harness): pi
- Skill: swe3
- Provider: bedrock
- Dataset scope: mcp-gateway-registry (5 tasks, ref 1.24.4)
- Serving: instance_type=t3.medium
- Run date: 2026-08-21

5 of 5 tasks scored; no failures.

## Results

| Task | Artifacts | Turns | Prefix-cache | Cost (est $) | Judge score |
|---|---|---|---|---|---|
| ssrf-hardening-outbound-url-validation | 6/6 | 26 | -- | 12.46 | 65.0 |
| remove-faiss | 6/6 | 21 | -- | 14.62 | 58.6 |
| remove-efs-from-terraform-aws-ecs | 6/6 | 18 | -- | 8.15 | 56.2 |
| replace-keycloak-db-password-with-rds-iam | 6/6 | 25 | -- | 9.34 | 52.4 |
| migrate-ecs-env-vars-to-secrets-manager | 6/6 | 33 | -- | 22.15 | 49.2 |

Mean over the 5 completed tasks: 56.28 (mean cost $13.34). A 0-score task is a model failure (missing artifacts) and is excluded from the means, pending investigation. Cost is a token-based estimate for self-hosted models.
