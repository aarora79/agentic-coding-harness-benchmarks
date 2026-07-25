# GitHub Issue: Migrate Sensitive ECS Environment Variables to AWS Secrets Manager

## Title
Migrate sensitive ECS environment variables to AWS Secrets Manager for enhanced security

## Labels
- security
- enhancement
- terraform
- aws

## Description

### Problem Statement
Currently, sensitive environment variables containing secrets (such as database passwords, API keys, OAuth client secrets, and admin passwords) are stored as plaintext in ECS task definitions via Terraform. This poses a security risk as these values are visible in the AWS console and Infrastructure as Code templates. Moving these sensitive values to AWS Secrets Manager will provide encryption at rest, enable rotation capabilities, and maintain an audit trail of access.

### Proposed Solution
1. Identify all sensitive environment variables across all ECS services in the Terraform configuration
2. Create AWS Secrets Manager resources for each secret
3. Update ECS task definitions to pull secrets from Secrets Manager instead of using plaintext environment variables
4. Update IAM task execution roles to grant read access to the appropriate Secrets Manager resources
5. Maintain backward compatibility by keeping the plaintext environment variable path as a fallback during migration

### User Stories
- As an operator deploying the registry on AWS ECS with Terraform, I want sensitive credentials to be securely stored so that I can meet security compliance requirements
- As a DevOps engineer, I want to enable secret rotation without redeploying applications so that I can improve operational security
- As a security engineer, I want to maintain audit trails of secret access so that I can monitor for unauthorized access

### Acceptance Criteria
- [ ] All sensitive environment variables are migrated to AWS Secrets Manager
- [ ] ECS task definitions pull secrets from Secrets Manager via the `secrets` block
- [ ] IAM task execution roles are updated to allow reading the new Secrets Manager resources
- [ ] Plaintext environment variable path remains as a fallback during migration
- [ ] All affected services continue to function correctly after migration
- [ ] Documentation is updated to reflect the new secret management approach

### Out of Scope
- Rotating existing secrets
- Changing the underlying services to support dynamic secret reloading
- Migrating non-sensitive environment variables

### Dependencies
- Terraform AWS provider version that supports Secrets Manager resources
- Existing IAM role structure in the Terraform codebase

### Related Issues
- #1134
