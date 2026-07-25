# GitHub Issue: Remove EFS from Terraform AWS ECS Deployment

## Title
Remove EFS from Terraform AWS ECS Deployment

## Labels
- enhancement
- infra
- terraform

## Description

### Problem Statement
EFS (Elastic File System) is no longer needed in this deployment as the application now uses S3/DocumentDB for all persistent storage. EFS adds unnecessary cost and complexity to the infrastructure without providing value. All services that previously used EFS-mounted volumes have been migrated to use DocumentDB for structured data and S3 for unstructured data.

### Proposed Solution
Remove all EFS-related resources from the Terraform AWS ECS deployment:
1. Delete the EFS file system, mount targets, and security groups
2. Remove volume mounts from ECS task definitions
3. Update variables.tf and terraform.tfvars.example to remove EFS configuration
4. Update module wiring and outputs to remove EFS references
5. Ensure terraform validate and terraform plan still succeed after changes

### User Stories
- As an operator, I want to deploy the MCP Gateway Registry without EFS to reduce infrastructure costs
- As a developer, I want a simplified deployment that uses only S3/DocumentDB for storage
- As an SRE, I want to eliminate unnecessary infrastructure components to reduce complexity and potential failure points

### Acceptance Criteria
- [ ] All EFS resources (file system, mount targets, security groups) are removed from Terraform
- [ ] Volume mounts referencing EFS are removed from ECS task definitions
- [ ] EFS-related variables are removed from variables.tf and terraform.tfvars.example
- [ ] Module wiring is updated to remove EFS dependencies
- [ ] Output variables related to EFS are removed
- [ ] terraform validate succeeds without errors
- [ ] terraform plan succeeds without errors
- [ ] All services continue to function correctly using S3/DocumentDB for storage

### Out of Scope
- Changing the application code to remove EFS references
- Modifying the storage logic in services (assumed to already use S3/DocumentDB)
- Updating documentation or README files

### Dependencies
- Confirmation that all services have been successfully migrated to S3/DocumentDB
- Verification that no service still depends on the EFS mount

### Related Issues
- #1286
