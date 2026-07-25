# Low-Level Design: Remove EFS from Terraform AWS ECS Deployment

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
EFS (Elastic File System) is no longer needed in the MCP Gateway Registry Terraform AWS ECS deployment as the application now uses S3/DocumentDB for all persistent storage. EFS adds unnecessary cost and complexity to the infrastructure without providing value. All services that previously used EFS-mounted volumes have been migrated to use DocumentDB for structured data and S3 for unstructured data.

The goal is to remove all EFS-related resources from the Terraform AWS ECS deployment to reduce infrastructure costs and simplify the architecture while ensuring continued functionality of all services.

### Goals
- Remove all EFS resources from Terraform (file system, mount targets, security groups)
- Eliminate EFS volume mounts from ECS task definitions
- Clean up EFS-related variables, outputs, and configuration
- Ensure terraform validate and terraform plan still succeed
- Maintain application functionality using only S3/DocumentDB for storage

### Non-Goals
- Changing the application code to remove EFS references (assumed already migrated)
- Modifying the storage logic in services (already using S3/DocumentDB)
- Updating documentation or README files
- Addressing any application-level data migration issues

## Codebase Analysis

### Key Files Reviewed

| File/Directory | Purpose | Relevance to This Change |
|----------------|---------|--------------------------|
| `terraform/aws-ecs/modules/mcp-gateway/storage.tf` | Defines EFS resources using terraform-aws-modules/efs/aws | Primary file to remove EFS implementation |
| `terraform/aws-ecs/modules/mcp-gateway/ecs-services.tf` | ECS service definitions with EFS volume mounts | Need to remove volume mounts and mountPoints |
| `terraform/aws-ecs/modules/mcp-gateway/variables.tf` | Module variables including EFS settings | Remove EFS-related variables |
| `terraform/aws-ecs/modules/mcp-gateway/outputs.tf` | Module outputs including EFS details | Remove EFS-related outputs |
| `terraform/aws-ecs/variables.tf` | Root module variables | Remove EFS-related variables |
| `terraform/aws-ecs/terraform.tfvars.example` | Example variables file | Remove EFS-related examples |
| `terraform/aws-ecs/outputs.tf` | Root module outputs | Remove EFS-related outputs |
| `terraform/aws-ecs/main.tf` | Root module configuration | Remove EFS module references |

### Existing Patterns Identified
1. **Modular Terraform Structure**: Clean separation between root module and mcp-gateway submodule
   - Files: `terraform/aws-ecs/main.tf`, `terraform/aws-ecs/modules/mcp-gateway/`
   - How a future implementer should follow this: Maintain consistency with existing patterns when removing EFS resources

2. **Consistent Variable Management**: Variables defined with defaults, validation, and descriptions
   - Files: `variables.tf` in both root and module directories
   - How a future implementer should follow this: Remove EFS variables following the same pattern used for defining them

3. **Secret Management Pattern**: AWS Secrets Manager integration with IAM policies
   - Files: Secret definitions in storage.tf and IAM policies
   - How a future implementer should follow this: Ensure no dangling IAM policies reference EFS resources

### Integration Points

| Component | Integration Type | Details |
|-----------|------------------|---------|
| ECS Services | Volume Mounts | Auth Server and MCPGW services currently mount EFS volumes |
| Security Groups | Network Rules | EFS security group allows NFS access from VPC |
| IAM Policies | Permissions | Task execution roles require EFS permissions |
| Outputs | Exports | EFS identifiers exported for external consumption |
| Variables | Configuration | EFS throughput settings configurable via variables |

### Constraints and Limitations Discovered
- **Service Dependencies**: Auth Server and MCPGW services currently depend on EFS volumes
- **Environment Variables**: Services reference EFS paths in environment variables (e.g., SCOPES_CONFIG_PATH)
- **Deployment Verification**: Need to ensure `terraform validate` and `terraform plan` still succeed

## Architecture

### System Context Diagram
```
Before:
[Internet] → [ALB] → [ECS Services]
                    ├── Auth Server ←→ [EFS]
                    ├── Registry
                    └── MCPGW ←→ [EFS]
                             ←→ [DocumentDB]
                             ←→ [S3]

After:
[Internet] → [ALB] → [ECS Services]
                    ├── Auth Server
                    ├── Registry
                    └── MCPGW ←→ [DocumentDB]
                             ←→ [S3]
```

### Sequence Diagram
```
Before EFS Removal:
1. Terraform Apply
2. EFS Creation
3. ECS Services Creation with EFS Mounts
4. Service Startup with EFS Access

After EFS Removal:
1. Terraform Apply
2. ECS Services Creation without EFS Mounts
3. Service Startup using DocumentDB/S3
```

### Component Diagram
```
Before:
┌─────────────────────────────────────┐
│           VPC                       │
│  ┌─────────────────┐    ┌────────┐ │
│  │   ECS Cluster   │    │  EFS   │ │
│  │  ┌───────────┐  │    │        │ │
│  │  │ Auth SVC  │←─┼────┤        │ │
│  │  ├───────────┤  │    │        │ │
│  │  │Registry   │  │    │        │ │
│  │  ├───────────┤  │    │        │ │
│  │  │ MCPGW SVC │←─┼────┤        │ │
│  │  └───────────┘  │    │        │ │
│  └─────────────────┘    └────────┘ │
│            ↓                       │
│      ┌───────────┐                 │
│      │DocumentDB │                 │
│      └───────────┘                 │
└─────────────────────────────────────┘

After:
┌─────────────────────────────────────┐
│           VPC                       │
│  ┌─────────────────┐               │
│  │   ECS Cluster   │               │
│  │  ┌───────────┐  │               │
│  │  │ Auth SVC  │  │               │
│  │  ├───────────┤  │               │
│  │  │Registry   │  │               │
│  │  ├───────────┤  │               │
│  │  │ MCPGW SVC │  │               │
│  │  └───────────┘  │               │
│  └─────────────────┘               │
│            ↓                       │
│      ┌───────────┐                 │
│      │DocumentDB │                 │
│      └───────────┘                 │
└─────────────────────────────────────┘
```

## Data Models

### New Models
No new models required as this change removes infrastructure rather than adding it.

### Model Changes
No existing data models are directly affected by this change as it's purely infrastructure-related.

## API / CLI Design

### New Endpoints / Commands
No new endpoints or CLI commands are required.

### Modified Endpoints / Commands
No existing endpoints or CLI commands are directly modified, though services will operate differently without EFS.

## Configuration Parameters

### Removed Environment Variables

| Variable Name | Service | Description |
|---------------|---------|-------------|
| `SCOPES_CONFIG_PATH` | Auth Server | Path was set to `/efs/auth_config/auth_config/scopes.yml` but should be updated to use DocumentDB |

### Settings / Config Class Updates

Several settings related to EFS configuration need to be removed:

```hcl
# Remove these from variables.tf
variable "efs_throughput_mode" {
  description = "Throughput mode for EFS (bursting or provisioned)"
  type        = string
  default     = "bursting"
  validation {
    condition     = contains(["bursting", "provisioned"], var.efs_throughput_mode)
    error_message = "EFS throughput mode must be either 'bursting' or 'provisioned'."
  }
}

variable "efs_provisioned_throughput" {
  description = "Provisioned throughput in MiB/s for EFS (only used if throughput_mode is provisioned)"
  type        = number
  default     = 100
}
```

### Deployment Surface Checklist
Need to remove EFS-related configuration from all deployment surfaces:
- [ ] `terraform/aws-ecs/variables.tf` - Remove EFS variables
- [ ] `terraform/aws-ecs/terraform.tfvars.example` - Remove EFS variable examples
- [ ] Documentation references (outside scope of this change)
- [ ] Any CI/CD pipeline references (outside scope of this change)

## New Dependencies

No new dependencies are required.

If no new dependencies are required, explicitly state: "This change uses only existing dependencies."

This change actually removes dependencies rather than adding them.

## Implementation Details

### Step-by-Step Plan (for a future implementer)

#### Step 1: Remove EFS Module in storage.tf
**File:** `terraform/aws-ecs/modules/mcp-gateway/storage.tf`
**Lines:** All lines (entire file content related to EFS)

Remove the entire EFS module definition:
```hcl
module "efs" {
  source  = "terraform-aws-modules/efs/aws"
  version = "~> 2.0"
  # ... all EFS configuration
}

resource "aws_vpc_security_group_egress_rule" "efs_all_outbound" {
  # ... egress rule configuration
}
```

#### Step 2: Remove EFS Volume Mounts from ECS Services
**File:** `terraform/aws-ecs/modules/mcp-gateway/ecs-services.tf`

For Auth Server service:
- Remove `volume` block containing EFS volumes
- Remove `mountPoints` from container definitions

For MCPGW service:
- Remove `volume` block containing EFS volumes
- Remove `mountPoints` from container definitions

Registry service already has no EFS mounts.

#### Step 3: Remove EFS Variables
**File:** `terraform/aws-ecs/modules/mcp-gateway/variables.tf`

Remove these variable definitions:
```hcl
variable "efs_throughput_mode" {
  # ... description and validation
}

variable "efs_provisioned_throughput" {
  # ... description and default
}
```

**File:** `terraform/aws-ecs/variables.tf`

Remove the same variable definitions at the root level.

#### Step 4: Update Environment Variables
**File:** `terraform/aws-ecs/modules/mcp-gateway/ecs-services.tf`

Update or remove environment variables that reference EFS paths:
- `SCOPES_CONFIG_PATH` in Auth Server should be updated to use DocumentDB instead of `/efs/auth_config/auth_config/scopes.yml`

#### Step 5: Remove EFS Outputs
**File:** `terraform/aws-ecs/modules/mcp-gateway/outputs.tf`

Remove these output definitions:
```hcl
output "efs_id" {
  # ... description and value
}

output "efs_arn" {
  # ... description and value
}

output "efs_access_points" {
  # ... description and value
}
```

**File:** `terraform/aws-ecs/outputs.tf`

Remove these output definitions:
```hcl
output "mcp_gateway_efs_id" {
  # ... description and value
}

output "mcp_gateway_efs_arn" {
  # ... description and value
}

output "mcp_gateway_efs_access_points" {
  # ... description and value
}
```

#### Step 6: Update terraform.tfvars.example
**File:** `terraform/aws-ecs/terraform.tfvars.example`

Remove any EFS-related variable examples.

### Error Handling
Since this is an infrastructure change, Terraform will handle error detection during `terraform plan` and `terraform apply`. Key validations include:
- Ensuring no resources reference removed EFS volumes
- Verifying that all services can start without EFS mounts

### Logging
No specific logging changes are required as this is an infrastructure change.

## Observability
### Tracing / Metrics / Logging Points
Monitor the following during and after deployment:
- ECS service deployment success/failure
- Task startup times without EFS mounts
- Application logs to ensure services function properly without EFS
- Cost metrics to verify EFS cost reduction

## Scaling Considerations
- Removing EFS eliminates a potential bottleneck for file-based operations
- Services now rely solely on DocumentDB and S3 for persistence, which are more scalable
- Reduced infrastructure complexity improves overall system reliability

## File Changes

### Deleted Files

| File Path | Description |
|-----------|-------------|
| `terraform/aws-ecs/modules/mcp-gateway/storage.tf` | Remove EFS implementation (can be deleted or emptied) |

### Modified Files

| File Path | Lines | Change Description |
|-----------|-------|--------------------|
| `terraform/aws-ecs/modules/mcp-gateway/ecs-services.tf` | ~500 | Remove EFS volume definitions and container mountPoints for Auth Server and MCPGW services |
| `terraform/aws-ecs/modules/mcp-gateway/variables.tf` | ~20 | Remove EFS-related variable definitions |
| `terraform/aws-ecs/modules/mcp-gateway/outputs.tf` | ~15 | Remove EFS-related output definitions |
| `terraform/aws-ecs/variables.tf` | ~20 | Remove EFS-related variable definitions at root level |
| `terraform/aws-ecs/outputs.tf` | ~15 | Remove EFS-related output definitions at root level |
| `terraform/aws-ecs/terraform.tfvars.example` | ~10 | Remove EFS-related variable examples |

### Estimated Lines of Code

| Category | Lines |
|----------|-------|
| Removed code | ~600 |
| New code | ~0 |
| Modified code | ~60 |
| **Net change** | **~540 fewer lines** |

## Testing Strategy
See `./testing.md` for the detailed testing plan.

## Alternatives Considered

### Alternative 1: Keep EFS But Reduce Throughput
**Description:** Instead of removing EFS entirely, reduce its throughput settings to minimize costs.
**Pros / Cons:**
- Pro: Preserves existing functionality
- Con: Still incurs EFS costs and complexity
**Why Rejected:** Doesn't meet the goal of eliminating EFS entirely to reduce complexity and cost.

### Alternative 2: Gradual Migration
**Description:** Migrate services one by one to eliminate EFS dependence before removing infrastructure.
**Pros / Cons:**
- Pro: Lower risk of service disruption
- Con: Requires longer timeline and coordination
**Why Rejected:** Assumption is that services have already been migrated to S3/DocumentDB.

### Comparison Matrix

| Criteria | Chosen (Remove EFS) | Alt 1 (Reduce Throughput) | Alt 2 (Gradual Migration) |
|----------|---------------------|---------------------------|---------------------------|
| Complexity | Medium | Low | High |
| Risk | Medium | Low | Low |
| Cost Savings | High | Low | Medium |
| Timeline | Short | Immediate | Long |

## Rollout Plan
- Phase 1: Implementation (out of scope for this skill)
- Phase 2: Testing
- Phase 3: Deployment

## Open Questions
- Have all services been fully migrated to use S3/DocumentDB instead of EFS?
- Are there any external systems that depend on the EFS outputs?
- Should the terraform.tfvars.example be updated to reflect the configuration changes?

## References
- AWS EFS Documentation: https://docs.aws.amazon.com/efs/latest/ug/whatis.html
- Terraform AWS EFS Module: https://registry.terraform.io/modules/terraform-aws-modules/efs/aws/latest
- DocumentDB Documentation: https://docs.aws.amazon.com/documentdb/latest/developerguide/
