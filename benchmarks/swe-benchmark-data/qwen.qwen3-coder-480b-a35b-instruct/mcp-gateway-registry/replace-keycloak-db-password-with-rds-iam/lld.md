# Low-Level Design: Replace Keycloak Database Password Authentication with RDS IAM Authentication

*Created: 2026-07-25*
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
Currently, Keycloak connects to its Aurora MySQL database using static username/password credentials stored in AWS Secrets Manager. This approach requires manual password rotation and presents security risks associated with long-lived credentials. To improve security posture and align with AWS best practices, we should migrate to RDS IAM database authentication which provides short-lived, automatically rotated credentials.

### Goals
- Enable IAM database authentication on the Aurora MySQL cluster
- Modify Keycloak ECS task to generate short-lived IAM auth tokens
- Remove static database credentials from Secrets Manager
- Maintain backward compatibility with password authentication as a feature-flagged fallback
- Improve security by eliminating static database credentials

### Non-Goals
- Changing the Keycloak version
- Modifying other database configurations beyond the authentication mechanism
- Supporting Helm/EKS deployments (focus on ECS/RDS/Terraform only)

## Codebase Analysis

### Key Files Reviewed

| File/Directory | Purpose | Relevance to This Change |
|----------------|---------|--------------------------|
| `terraform/aws-ecs/keycloak-database.tf` | Defines Aurora MySQL cluster and RDS proxy | Need to enable IAM database authentication |
| `terraform/aws-ecs/keycloak-ecs.tf` | Defines ECS task definition and IAM roles | Need to modify IAM policies and task secrets |
| `terraform/aws-ecs/variables.tf` | Defines Terraform variables | May need new variables for IAM auth |
| `keycloak/` | Keycloak setup and documentation | Understanding current auth mechanism |

### Existing Patterns Identified
1. **Secrets Management Pattern**: Currently using AWS Secrets Manager to store database credentials with ECS injecting them as environment variables
   - Files: `keycloak-database.tf`, `keycloak-ecs.tf`
   - How a future implementer should follow this: Continue using Secrets Manager for feature flag but add IAM auth as alternative

2. **Feature Flag Pattern**: Using boolean flags to toggle functionality
   - Files: Various Terraform configurations use conditional blocks
   - How a future implementer should follow this: Add a new variable to enable/disable IAM authentication

### Integration Points

| Component | Integration Type | Details |
|-----------|------------------|---------|
| Aurora MySQL Cluster | Modified | Enable IAM database authentication property |
| RDS Proxy | Modified | Update IAM authentication settings |
| ECS Task Definition | Modified | Change how database credentials are sourced |
| IAM Policies | Added | Grant `rds:GenerateDBAuthToken` permission |
| Secrets Manager | Modified | Conditionally used based on feature flag |

### Constraints and Limitations Discovered
- Keycloak must support MySQL IAM authentication (supported in Keycloak 25+)
- Cannot break existing deployments during transition
- ECS tasks need appropriate IAM permissions to generate auth tokens
- Aurora MySQL version must support IAM authentication

## Architecture

### System Context Diagram
```
┌─────────────────────────────────────────────────────────────────┐
│                        AWS Environment                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────┐    ┌──────────────┐    ┌──────────────────┐   │
│  │   Keycloak  │    │     ECS      │    │  IAM Auth Token  │   │
│  │   Service   │◄──►│    Task      │◄──►│   Generation     │   │
│  │             │    │              │    │                  │   │
│  └─────────────┘    └──────────────┘    └──────────────────┘   │
│                         │                            │         │
│                         ▼                            ▼         │
│                 ┌──────────────┐    ┌─────────────────────┐    │
│                 │ RDS Database │    │  IAM Authentication │    │
│                 │  (Aurora)    │◄──►│     Policies        │    │
│                 │              │    │                     │    │
│                 └──────────────┘    └─────────────────────┘    │
│                         │                            │         │
│                         ▼                            │         │
│                 ┌──────────────┐                     │         │
│                 │ Secrets Mgr  │                     │         │
│                 │  (fallback)  │◄────────────────────┘         │
│                 │              │                               │
│                 └──────────────┘                               │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Sequence Diagram
```
1. ECS Task Starts
   │
   ├─ Check feature flag: iam_auth_enabled
   │
   ├─ If True:
   │  ├─ Assume IAM role with rds:GenerateDBAuthToken permission
   │  ├─ Generate temporary auth token for database user
   │  ├─ Connect to Aurora MySQL using IAM token
   │  └─ Proceed with Keycloak startup
   │
   └─ If False (fallback):
      ├─ Retrieve username/password from Secrets Manager
      ├─ Connect to Aurora MySQL using traditional auth
      └─ Proceed with Keycloak startup
```

### Component Diagram
```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Terraform Module                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────┐    ┌─────────────────────┐    ┌─────────────────┐ │
│  │   Aurora MySQL      │    │     RDS Proxy       │    │  ECS Task Def   │ │
│  │   Cluster           │    │                     │    │                 │ │
│  │                     │    │                     │    │  ┌────────────┐ │ │
│  │ ┌─────────────────┐ │    │ ┌─────────────────┐ │    │  │ Keycloak   │ │ │
│  │ │ IAM Auth: True  │ │◄──►│ │ IAM Auth: True  │ │◄──►│  │ Container  │ │ │
│  │ └─────────────────┘ │    │ └─────────────────┘ │    │  └────────────┘ │ │
│  │                     │    │                     │    │                 │ │
│  └─────────────────────┘    └─────────────────────┘    └─────────────────┘ │
│                                  │                           │             │
│                                  ▼                           ▼             │
│                        ┌─────────────────────┐    ┌─────────────────────┐  │
│                        │  IAM Role/Policies  │    │  Secrets Manager    │  │
│                        │                     │    │  (fallback)         │  │
│                        │ ┌─────────────────┐ │    │                     │  │
│                        │ │ Generate Token  │ │    │ ┌─────────────────┐ │  │
│                        │ │ Permission      │ │    │ │ Username        │ │  │
│                        │ └─────────────────┘ │    │ │ Password        │ │  │
│                        └─────────────────────┘    │ └─────────────────┘ │  │
│                                                   └─────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Data Models

### New Models
No new data models required as this is an infrastructure-level change.

### Model Changes
No existing model changes required. This is a configuration and infrastructure change.

## API / CLI Design

### New Endpoints / Commands
Not applicable - this is an infrastructure change that affects how Keycloak connects to its database.

## Configuration Parameters

### New Environment Variables

| Variable Name | Type | Default | Required | Description |
|---------------|------|---------|----------|-------------|
| `KEYCLOAK_DB_IAM_AUTH_ENABLED` | bool | `false` | No | Enable IAM database authentication for Keycloak |

### Settings / Config Class Updates
No new settings needed at the application level. This is handled entirely through Terraform and ECS configuration.

### Deployment Surface Checklist
List every surface where this parameter must appear (`.env.example`, `docker-compose.yml`, Terraform vars, Helm values, etc.) so an implementer can tick them off later.
- [ ] Terraform variables (`variables.tf`)
- [ ] Terraform terraform.tfvars.example
- [ ] Keycloak ECS task definition environment variables

## New Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| AWS CLI | Latest | Required for generating RDS IAM auth tokens |
| mysql-client | Latest | Required for Keycloak to connect with IAM tokens |

If no new dependencies are required, explicitly state: "This change uses only existing dependencies."

## Implementation Details

### Step-by-Step Plan (for a future implementer)

#### Step 1: Enable IAM Database Authentication on Aurora MySQL
**File:** `terraform/aws-ecs/keycloak-database.tf`
**Lines:** ~48 (in `aws_rds_cluster.keycloak` resource)

```hcl
resource "aws_rds_cluster" "keycloak" {
  # ... existing configuration ...

  # Enable IAM database authentication
  enable_iam_database_authentication = var.keycloak_database_iam_auth_enabled

  # ... rest of existing configuration ...
}
```

Also update the RDS proxy configuration to support IAM authentication:
**Lines:** ~14 (in `aws_db_proxy.keycloak` resource)

```hcl
resource "aws_db_proxy" "keycloak" {
  # ... existing configuration ...

  auth {
    auth_scheme               = "SECRETS"
    secret_arn                = aws_secretsmanager_secret.keycloak_db_secret.arn
    client_password_auth_type = "MYSQL_CACHING_SHA2_PASSWORD"
    iam_auth                  = var.keycloak_database_iam_auth_enabled ? "REQUIRED" : "DISABLED"
  }

  # ... rest of existing configuration ...
}
```

#### Step 2: Add New Terraform Variable
**File:** `terraform/aws-ecs/variables.tf`

```hcl
variable "keycloak_database_iam_auth_enabled" {
  description = "Enable IAM database authentication for Keycloak"
  type        = bool
  default     = false
}
```

#### Step 3: Update IAM Policies for ECS Task
**File:** `terraform/aws-ecs/keycloak-ecs.tf`
**Lines:** ~173 (in `aws_iam_role_policy.keycloak_task_exec_ssm_policy` resource)

```hcl
resource "aws_iam_role_policy" "keycloak_task_exec_ssm_policy" {
  name = "keycloak-task-exec-ssm-policy"
  role = aws_iam_role.keycloak_task_exec_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # ... existing statements ...
      {
        # Allow generation of RDS IAM auth tokens when IAM auth is enabled
        Effect = "Allow"
        Action = [
          "rds:GenerateDBAuthToken"
        ],
        Resource = [
          aws_rds_cluster.keycloak.arn
        ]
      }
    ]
  })
}
```

#### Step 4: Modify ECS Task Definition for Conditional Credential Handling
**File:** `terraform/aws-ecs/keycloak-ecs.tf`
**Lines:** ~15-106 (in `locals` block)

Update the local variables to conditionally handle credentials:

```hcl
locals {
  # ... existing configuration ...

  # Conditionally determine database credentials based on IAM auth setting
  keycloak_container_secrets = concat([
    {
      name      = "KEYCLOAK_ADMIN"
      valueFrom = aws_ssm_parameter.keycloak_admin.arn
    },
    {
      name      = "KEYCLOAK_ADMIN_PASSWORD"
      valueFrom = aws_ssm_parameter.keycloak_admin_password.arn
    },
    {
      name      = "KC_DB_URL"
      valueFrom = aws_ssm_parameter.keycloak_database_url.arn
    }
  ], var.keycloak_database_iam_auth_enabled ? [
    # When IAM auth is enabled, only pass the username
    {
      name      = "KC_DB_USERNAME"
      valueFrom = "${aws_secretsmanager_secret.keycloak_db_secret.arn}:username::"
    }
    # Password will be generated dynamically by Keycloak
  ] : [
    # When IAM auth is disabled, pass both username and password (legacy mode)
    {
      name      = "KC_DB_USERNAME"
      valueFrom = "${aws_secretsmanager_secret.keycloak_db_secret.arn}:username::"
    },
    {
      name      = "KC_DB_PASSWORD"
      valueFrom = "${aws_secretsmanager_secret.keycloak_db_secret.arn}:password::"
    }
  ])

  # Add feature flag environment variable
  keycloak_container_env = concat(local._keycloak_container_env_base, [
    {
      name  = "KEYCLOAK_DB_IAM_AUTH_ENABLED"
      value = var.keycloak_database_iam_auth_enabled ? "true" : "false"
    }
  ])

  # Store base environment variables separately to avoid circular references
  _keycloak_container_env_base = [
    {
      name  = "AWS_REGION"
      value = var.aws_region
    },
    # ... rest of existing environment variables ...
  ]
}
```

#### Step 5: Create Custom Keycloak Image with IAM Auth Support
Since Keycloak needs additional tools to generate IAM auth tokens, we'll need a custom image:

**File:** `docker/keycloak/Dockerfile` (new file)

```dockerfile
FROM quay.io/keycloak/keycloak:25.0

# Install AWS CLI for IAM auth token generation
USER root
RUN microdnf install -y python3 python3-pip && \
    pip3 install awscli && \
    microdnf clean all

# Copy custom startup script
COPY docker/keycloak/scripts/start-keycloak.sh /opt/keycloak/bin/start-keycloak.sh
RUN chmod +x /opt/keycloak/bin/start-keycloak.sh

USER keycloak
ENTRYPOINT ["/opt/keycloak/bin/start-keycloak.sh"]
CMD ["start"]
```

**File:** `docker/keycloak/scripts/start-keycloak.sh` (new file)

```bash
#!/bin/bash

# If IAM auth is enabled, generate temporary auth token
if [ "$KEYCLOAK_DB_IAM_AUTH_ENABLED" = "true" ]; then
  echo "Generating RDS IAM authentication token..."

  # Extract DB host from JDBC URL
  DB_HOST=$(echo "$KC_DB_URL" | sed -E 's/jdbc:mysql:\/\/([^:]+):.*/\1/')

  # Generate auth token
  KC_DB_PASSWORD=$(aws rds generate-db-auth-token \
    --hostname $DB_HOST \
    --port 3306 \
    --region $AWS_REGION \
    --username $KC_DB_USERNAME)

  export KC_DB_PASSWORD
fi

# Start Keycloak
exec /opt/keycloak/bin/kc.sh "$@"
```

#### Step 6: Update Keycloak Image URI in Terraform
**File:** `terraform/aws-ecs/variables.tf`

```hcl
variable "keycloak_image_uri" {
  description = "Container image URI for Keycloak. Defaults to custom image with IAM auth support."
  type        = string
  default     = ""  # Will be set to custom ECR image
}
```

### Error Handling
1. IAM authentication token generation failures should fall back to password authentication
2. Log appropriate error messages when IAM auth fails
3. Ensure graceful degradation to password authentication when needed

### Logging
1. Log when IAM authentication is enabled/disabled
2. Log successful token generation
3. Log fallback to password authentication
4. Log any errors during token generation

## Observability
### Tracing / Metrics / Logging Points
- Log IAM authentication status at startup
- Log successful token generation events
- Log fallback to password authentication
- Monitor database connection success/failure rates
- Track authentication method usage in metrics

## Scaling Considerations
- Current load assumptions: Keycloak generates one token per container startup
- Horizontal scaling: Each ECS task instance will generate its own auth token
- Bottlenecks: RDS IAM token generation service limits (default: 5000 requests/sec)
- Caching strategy: Tokens are short-lived (15 minutes), so no caching needed

## File Changes

### New Files

| File Path | Description |
|-----------|-------------|
| `docker/keycloak/Dockerfile` | Custom Keycloak image with AWS CLI for IAM auth |
| `docker/keycloak/scripts/start-keycloak.sh` | Custom startup script for dynamic token generation |

### Modified Files

| File Path | Lines | Change Description |
|-----------|-------|--------------------|
| `terraform/aws-ecs/keycloak-database.tf` | ~14, ~48 | Enable IAM database authentication on RDS cluster and proxy |
| `terraform/aws-ecs/keycloak-ecs.tf` | ~15-106, ~173 | Update IAM policies and conditional credential handling |
| `terraform/aws-ecs/variables.tf` | ~90, ~115 | Add new variable for IAM auth flag |
| `terraform/aws-ecs/terraform.tfvars.example` | ~90 | Add example for new IAM auth variable |

### Estimated Lines of Code

| Category | Lines |
|----------|-------|
| New code | ~80 |
| New tests | ~0 (infrastructure change) |
| Modified code | ~30 |
| **Total** | **~110** |

## Testing Strategy
See `./testing.md` for the complete testing plan.

## Alternatives Considered

### Alternative 1: Continue Using Password Authentication
**Description:** Keep the current password-based authentication with Secrets Manager
**Pros:**
- No changes required
- Proven approach
- Simpler implementation
**Cons:**
- Security risks with static credentials
- Manual rotation overhead
- Doesn't follow AWS security best practices
**Why Rejected:** Security improvements are a key goal of this initiative.

### Alternative 2: Use IAM Database Authentication Without Fallback
**Description:** Implement IAM auth but remove password authentication entirely
**Pros:**
- Stronger security posture
- Simpler configuration
- Eliminates password management entirely
**Cons:**
- Higher risk of breaking existing deployments
- No fallback during issues
- Harder rollback if problems occur
**Why Rejected:** Backward compatibility and safe rollout are requirements.

### Comparison Matrix

| Criteria | Chosen | Alt 1 | Alt 2 |
|----------|--------|-------|-------|
| Security | High | Medium | High |
| Complexity | Medium | Low | Low |
| Backward Compatibility | Excellent | Excellent | Poor |
| Risk | Low | Low | High |
| Maintenance | Low | Medium | Low |

## Rollout Plan
- Phase 1: Implementation (out of scope for this skill)
- Phase 2: Testing in development environment
- Phase 3: Gradual rollout with feature flag
- Phase 4: Monitoring and validation
- Phase 5: Decommission password authentication (future)

## Open Questions
- Does Keycloak 25 officially support MySQL IAM authentication?
- Are there any performance implications of generating auth tokens at startup?
- Should we implement connection pooling for auth tokens?

## References
- [AWS RDS IAM Database Authentication](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/UsingWithRDS.IAMDBAuth.html)
- [Keycloak Database Configuration](https://www.keycloak.org/server/db)
- [Amazon Aurora MySQL IAM Authentication](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/AuroraMySQL.Security.html)
