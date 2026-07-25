# Low-Level Design: Migrate Sensitive ECS Environment Variables to AWS Secrets Manager

*Created: 2026-07-24*
*Author: Claude*
*Status: Draft*

## Table of Contents
1. [Overview](#overview)
2. [Codebase Analysis](#codebase-analysis)
3. [Architecture](#architecture)
4. [Data Models](#data-models)
5. [API / CLI Design](#api--cli-design)
6. [Configuration Parameters](#configuration-parameters)
7. [New Dependencies](#new-dependencies)
8. [Implementation Details](#implementation-details)
9. [Observability](#observability)
10. [Scaling Considerations](#scaling-considerations)
11. [File Changes](#file-changes)
12. [Testing Strategy](#testing-strategy)
13. [Alternatives Considered](#alternatives-considered)
14. [Rollout Plan](#rollout-plan)

## Overview
### Problem Statement
Currently, sensitive environment variables containing secrets (such as database passwords, API keys, OAuth client secrets, and admin passwords) are stored as plaintext in ECS task definitions via Terraform. This poses a security risk as these values are visible in the AWS console and Infrastructure as Code templates. Moving these sensitive values to AWS Secrets Manager will provide encryption at rest, enable rotation capabilities, and maintain an audit trail of access.

The migration affects multiple services in the mcp-gateway-registry deployment:
- Auth Server
- Registry (primary service)
- MCP Gateway
- Demo services (if enabled)

### Goals
- Identify all sensitive environment variables in ECS task definitions
- Create AWS Secrets Manager resources for each identified secret
- Update ECS task definitions to pull secrets from Secrets Manager
- Update IAM task execution roles to grant read access to new Secrets Manager resources
- Maintain backward compatibility with plaintext environment variables as fallback during migration
- Follow established patterns in the codebase

### Non-Goals
- Rotating existing secrets during migration
- Changing the underlying services to support dynamic secret reloading
- Migrating non-sensitive environment variables
- Automating the initial secret population process

## Codebase Analysis

### Key Files Reviewed

| File/Directory | Purpose | Relevance to This Change |
|----------------|---------|--------------------------|
| `terraform/aws-ecs/modules/mcp-gateway/ecs-services.tf` | ECS service definitions with container environment variables and secrets | Core implementation of where environment variables/secrets are defined |
| `terraform/aws-ecs/modules/mcp-gateway/secrets.tf` | Secrets Manager and KMS configuration | Existing secret management patterns to follow |
| `terraform/aws-ecs/modules/mcp-gateway/iam.tf` | IAM policies for ECS task roles | Existing access control patterns for secrets |
| `terraform/aws-ecs/keycloak-ecs.tf` | Keycloak ECS service (external example) | Example of proper secret management implementation |
| `terraform/aws-ecs/keycloak-database.tf` | Keycloak database secrets (external example) | Example of proper secret management implementation |

### Existing Patterns Identified
1. **Dual Secret Management Approach**: The codebase already uses both AWS Systems Manager (SSM) Parameter Store and AWS Secrets Manager depending on the nature of the secret:
   - Static configuration secrets: SSM Parameter Store
   - Rotating credentials: Secrets Manager

   Files: `keycloak-ecs.tf`, `keycloak-database.tf`

2. **Principle of Least Privilege**: IAM policies are precisely scoped to only allow access to specific secrets/parameters.
   Files: `iam.tf`

3. **Comprehensive Environment Variable Organization**: Environment variables are categorized into:
   - Non-sensitive environment variables in the `environment` block
   - Sensitive variables in the `secrets` block with references to `valueFrom`

   Files: `ecs-services.tf`

4. **Proper Secret Value Referencing**: Secrets Manager values are referenced using ARN formats with field specification:
   ```
   valueFrom = "${aws_secretsmanager_secret.name.arn}:field::"
   ```

   Files: `ecs-services.tf`

### Integration Points
| Component | Integration Type | Details |
|-----------|------------------|---------|
| ECS Task Definitions | Extends | Environment variables and secrets blocks need updating |
| IAM Policies | Depends on | Need to grant access to new Secrets Manager resources |
| Secrets Manager | Creates/Depends on | Will store new secrets, accessed by ECS containers |
| KMS Keys | Depends on | Existing key used to encrypt Secrets Manager resources |

### Constraints and Limitations Discovered
- Secrets referenced in the container definition's `secrets` block are limited to a single line of text (not structured objects)
- Some secrets must be maintained temporarily in both forms (plaintext and Secrets Manager) for migration purposes
- Rotation support needs coordination with services consuming the secrets

## Architecture

### System Context Diagram
```
┌─────────────────┐       ┌─────────────────────┐       ┌─────────────────────┐
│  ECS Container  │──────▶│  AWS Secrets Mgr    │◀─────▶│   Configuration     │
│                 │       │                     │       │       Code          │
│   (Registry)    │       │  Encrypted Secrets  │       │   (Terraform)       │
└─────────────────┘       └─────────────────────┘       └─────────────────────┘
         │                           │                              │
         ▼                           ▼                              ▼
┌─────────────────┐       ┌─────────────────────┐       ┌─────────────────────┐
│  ECS Container  │       │  IAM Execution      │       │   KMS Encryption    │
│    (Auth)       │       │       Role          │       │                     │
└─────────────────┘       └─────────────────────┘       └─────────────────────┘
```

### Component Diagram
```
                                 ┌─────────────────────────────┐
                                 │                             │
                                 │   ECS Task Definition       │
                                 │                             │
                                 │  environment: [             │
                                 │    { name: "VAR1"         ◀─┼─── Plaintext (retain during migration)
                                 │      value: "value" }       │
                                 │  ]                          │
                                 │                             │
                                 │  secrets: [                 │
                                 │    { name: "DB_USER"      ◀─┼─── From Secrets Manager
                                 │      valueFrom: "arn:..."   │
                                 │    }                        │
                                 │  ]                          │
                                 │                             │
                                 └─────────────┬───────────────┘
                                               │
                             ┌─────────────────┴─────────────────┐
                             │                                   │
                             ▼                                   ▼
         ┌────────────────────────────┐     ┌────────────────────────────┐
         │                            │     │                            │
         │    IAM Role Policy         │     │     Secrets Manager        │
         │                            │     │                            │
         │ permissions: [             │     │  aws_secretsmanager_secret │
         │   "secretsmanager:Get..."  │     │  {                         │
         │ ]                          │     │    secret_string = json    │
         │                            │     │  }                         │
         │ resource: [                │     │  aws_secretsmanager_secret_│
         │   aws_sm_secret.arn        │     │  version                   │
         │ ]                          │     │  {                         │
         │                            │     │    secret_id               │
         │                            │     │    secret_string           │
         │                            │     │  }                         │
         └────────────────────────────┘     └────────────────────────────┘
                                                            │
                                            ┌─────────────────┴─────────────────┐
                                            │                                   │
                                            ▼                                   ▼
                                ┌─────────────────────┐         ┌─────────────────────┐
                                │                     │         │                     │
                                │   KMS Key           │         │   Application       │
                                │                     │         │   Containers        │
                                │ aws_kms_key.secrets │         │                     │
                                │                     │         │ Can now reference   │
                                │  encryption         │         │ secrets directly    │
                                │                     │         │ without plaintext   │
                                └─────────────────────┘         └─────────────────────┘
```

## Data Models

This change primarily affects infrastructure configuration rather than application data models. However, it modifies how secrets are structured in Terraform.

## API / CLI Design

No API or CLI changes are required as this is an infrastructure-level change that affects deployment rather than runtime behavior.

## Configuration Parameters

This change primarily involves infrastructure configuration rather than introducing new application configuration parameters.

### Deployment Surface Checklist
List every surface where configuration changes must be made:
- [ ] terraform/aws-ecs/modules/mcp-gateway/ecs-services.tf
- [ ] terraform/aws-ecs/modules/mcp-gateway/secrets.tf
- [ ] terraform/aws-ecs/modules/mcp-gateway/iam.tf

## New Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| AWS Secrets Manager | N/A (existing AWS service) | Secure storage of sensitive environment variables |
| AWS KMS | N/A (existing AWS service) | Encryption of secrets at rest |

If no new dependencies are required, explicitly state: "This change uses only existing AWS services and Terraform providers."

## Implementation Details

### Step-by-Step Plan (for a future implementer)

Note: Some sensitive environment variables are already properly managed through AWS Secrets Manager in the codebase. The implementation will focus on the remaining plaintext secrets that need to be migrated.

#### Step 1: Identify Secrets to Migrate

Based on the code analysis, we need to migrate the following sensitive environment variables:

**Auth Server Service:**
1. `REGISTRY_API_TOKEN` - Move to AWS Secrets Manager
2. `REGISTRY_API_KEYS` - Move to AWS Secrets Manager
3. `FEDERATION_STATIC_TOKEN` - Move to AWS Secrets Manager
4. `FEDERATION_ENCRYPTION_KEY` - Move to AWS Secrets Manager
5. `ANS_API_KEY` - Move to AWS Secrets Manager
6. `ANS_API_SECRET` - Move to AWS Secrets Manager
7. `GITHUB_APP_PRIVATE_KEY` - Move to AWS Secrets Manager
8. `REGISTRATION_WEBHOOK_AUTH_TOKEN` - Move to AWS Secrets Manager
9. `REGISTRATION_GATE_OAUTH2_CLIENT_SECRET` - Move to AWS Secrets Manager

**Registry Service:**
1. `REGISTRY_API_TOKEN` - Move to AWS Secrets Manager
2. `REGISTRY_API_KEYS` - Move to AWS Secrets Manager
3. `FEDERATION_STATIC_TOKEN` - Move to AWS Secrets Manager
4. `FEDERATION_ENCRYPTION_KEY` - Move to AWS Secrets Manager
5. `ANS_API_KEY` - Move to AWS Secrets Manager
6. `ANS_API_SECRET` - Move to AWS Secrets Manager
7. `GITHUB_APP_PRIVATE_KEY` - Move to AWS Secrets Manager
8. `REGISTRATION_WEBHOOK_AUTH_TOKEN` - Move to AWS Secrets Manager
9. `REGISTRATION_GATE_OAUTH2_CLIENT_SECRET` - Move to AWS Secrets Manager

#### Step 2: Create AWS Secrets Manager Resources (secrets.tf)

For each service requiring secret migration, we'll follow the pattern established in the codebase. Here's an implementation example for one secret:

```terraform
# Secrets Manager resource for Registry API Token
resource "aws_secretsmanager_secret" "registry_api_token" {
  name_prefix             = "${local.name_prefix}-registry-api-token-"
  description             = "Registry API token for authentication"
  recovery_window_in_days = 0
  kms_key_id              = aws_kms_key.secrets.id
  tags                    = local.common_tags
}

resource "aws_secretsmanager_secret_version" "registry_api_token" {
  secret_id     = aws_secretsmanager_secret.registry_api_token.id
  secret_string = var.registry_api_token

  lifecycle {
    ignore_changes = [secret_string]
  }
}
```

#### Step 3: Update IAM Policies (iam.tf)

We'll need to update the existing IAM policy to include the new secrets:

```terraform
resource "aws_iam_policy" "ecs_secrets_access" {
  name_prefix = "${local.name_prefix}-ecs-secrets-"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = concat(
          [
            aws_secretsmanager_secret.secret_key.arn,
            aws_secretsmanager_secret.keycloak_client_secret.arn,
            aws_secretsmanager_secret.keycloak_m2m_client_secret.arn,
            aws_secretsmanager_secret.embeddings_api_key.arn,
            aws_secretsmanager_secret.keycloak_admin_password.arn,
            # New secrets to be added here:
            aws_secretsmanager_secret.registry_api_token.arn,
            aws_secretsmanager_secret.federation_static_token.arn,
            # Additional new secrets will be added below
          ],
          var.documentdb_credentials_secret_arn != "" ? [var.documentdb_credentials_secret_arn] : [],
          var.entra_enabled ? [aws_secretsmanager_secret.entra_client_secret[0].arn] : [],
          var.okta_enabled ? [
            aws_secretsmanager_secret.okta_client_secret[0].arn,
            aws_secretsmanager_secret.okta_m2m_client_secret[0].arn,
            aws_secretsmanager_secret.okta_api_token[0].arn
          ] : [],
          var.auth0_enabled ? [
            aws_secretsmanager_secret.auth0_client_secret[0].arn,
            aws_secretsmanager_secret.auth0_m2m_client_secret[0].arn
          ] : [],
          var.enable_observability ? [aws_secretsmanager_secret.metrics_api_key[0].arn] : [],
          var.enable_observability && var.otel_otlp_endpoint != "" ? [aws_secretsmanager_secret.otlp_exporter_headers[0].arn] : []
        )
      },
      {
        Effect = "Allow"
        Action = [
          "kms:Decrypt",
          "kms:DescribeKey"
        ]
        Resource = [
          aws_kms_key.secrets.arn
        ]
      }
    ]
  })

  tags = local.common_tags
}
```

#### Step 4: Update ECS Task Definitions (ecs-services.tf)

We'll need to modify the container definitions to reference the new Secrets Manager resources instead of using plaintext environment variables:

Current approach (plaintext):
```terraform
{
  name  = "REGISTRY_API_TOKEN"
  value = var.registry_api_token
}
```

New approach (using Secrets Manager):
```terraform
{
  name      = "REGISTRY_API_TOKEN"
  valueFrom = aws_secretsmanager_secret.registry_api_token.arn
}
```

We'll initially keep both approaches to ensure backward compatibility during migration, then remove the plaintext approach once the migration is complete.

### Error Handling
Since this is an infrastructure change, errors will manifest as Terraform apply failures:
1. IAM policy errors due to incorrect ARNs - validate all ARNs before apply
2. Secret creation errors - ensure proper KMS key access
3. Secret reference errors in container definitions - verify syntax matches existing patterns

### Logging
Terraform plan/apply operations will provide visibility into changes. No specific logging is required during runtime as this is an infrastructure-level change.

## Observability
Infrastructure changes like this are typically observed through:
1. Terraform execution logs
2. AWS CloudTrail audit logs for Secrets Manager and IAM changes
3. Infrastructure drift detection

Application-level observability is not affected by this change.

## Scaling Considerations
- Secrets Manager has generous service limits that should accommodate the number of secrets in this deployment
- IAM policies have a practical limit on the number of resources listed - the current approach of concatenating lists should handle the number of secrets needed
- No performance impact on the application containers as secret retrieval is handled transparently by the ECS agent

## File Changes

### New Files

| File Path | Description |
|-----------|-------------|
| None | This change updates existing files rather than creating new ones |

### Modified Files

| File Path | Lines | Change Description |
|-----------|-------|--------------------|
| `terraform/aws-ecs/modules/mcp-gateway/secrets.tf` | Various | Add AWS Secrets Manager resources for each identified secret |
| `terraform/aws-ecs/modules/mcp-gateway/iam.tf` | Lines 15-36 | Update IAM policy to grant access to new Secrets Manager resources |
| `terraform/aws-ecs/modules/mcp-gateway/ecs-services.tf` | Lines 97-411,698-1308 | Update environment/secrets blocks to reference AWS Secrets Manager instead of plaintext values |

### Estimated Lines of Code

| Category | Lines |
|----------|-------|
| New code (secrets.tf additions) | ~100 |
| New code (iam.tf modifications) | ~10 |
| Modified code (ecs-services.tf) | ~50 |
| **Total** | **~160** |

Note that during a transition period, both plaintext and Secrets Manager approaches might coexist, adding some temporary complexity.

## Testing Strategy
See `testing.md` for the detailed testing plan.

## Alternatives Considered

### Alternative 1: Continue Using SSM Parameter Store
**Description:** Continue using SSM Parameter Store with SecureString type for all sensitive values
**Pros:**
- Less disruption to current architecture
- Simpler implementation for some values
- Consistent with existing Keycloak approach for some secrets
**Cons:**
- Does not fully address the requirement (which specifies Secrets Manager)
- Missing advanced Secrets Manager features like automated rotation triggers
- Inconsistent with established best practices for container-based workloads

**Why Rejected:** This approach would not fulfill the core requirement of moving to Secrets Manager, which offers superior rotation capabilities and more appropriate features for container-based environments.

### Alternative 2: Use External Secrets Operator
**Description:** Implement Kubernetes External Secrets or AWS Secrets and Configuration Provider (ASCP) for ECS
**Pros:**
- Centralized secret management
- Better integration with external secret stores
- Advanced synchronization capabilities
**Cons:**
- Adds operational complexity
- Not suitable for pure ECS deployments (External Secrets is Kubernetes-focused)
- Would require additional infrastructure

**Why Rejected:** The current deployment is pure ECS-based, and adding additional secret management layers would increase complexity unnecessarily.

### Alternative 3: Move All Secrets to Secrets Manager
**Description:** Consolidate all secrets into Secrets Manager regardless of rotation requirements
**Pros:**
- Complete consistency in secret management approach
- Unified auditing and access control
- Future-proof for any secrets that might eventually need rotation
**Cons:**
- Some complexity in accessing simple configuration values
- Potentially higher costs for secrets that don't benefit from rotation features

**Why Rejected:** The current hybrid approach of SSM for static configuration and Secrets Manager for rotating credentials is already well-established and appropriate for the use case.

### Comparison Matrix

| Criteria | Chosen Approach | Alt 1 (SSM) | Alt 2 (External Secrets) | Alt 3 (All Secrets Manager) |
|----------|-----------------|-------------|--------------------------|------------------------------|
| Security | High | High | Very High | High |
| Complexity | Low-Medium | Low | High | Low |
| Cost | Moderate | Low | High | Moderate |
| Rotation Support | Excellent (targeted) | Limited | Excellent | Excellent |
| Consistency with Current Architecture | High | Very High | Low | Medium-High |
| Alignment with Requirements | Perfect | Poor | Moderate | High |

## Rollout Plan
1. **Phase 1:** Infrastructure Changes
   - Add AWS Secrets Manager resources for identified secrets
   - Update IAM policies to grant access to new secrets
   - Modify ECS task definitions to reference new secrets

2. **Phase 2:** Verification
   - Execute Terraform plan to validate changes
   - Perform test deployment in staging environment
   - Validate secret access from containers

3. **Phase 3:** Production Deployment
   - Apply changes to production environment
   - Monitor for any access issues
   - Remove temporary plaintext environment variables after validation

## Open Questions
1. Should we provide a migration script to populate Secrets Manager from existing environment variables?
2. How should we handle secrets that currently have no Terraform variables defined but are passed via tfvars?

## References
- [AWS Secrets Manager Documentation](https://docs.aws.amazon.com/secretsmanager/latest/userguide/intro.html)
- [ECS Secrets Documentation](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/specifying-sensitive-data.html)
