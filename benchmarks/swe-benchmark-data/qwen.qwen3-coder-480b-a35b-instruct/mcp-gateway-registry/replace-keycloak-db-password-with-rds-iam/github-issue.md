# GitHub Issue: Replace Keycloak Database Password Authentication with RDS IAM Authentication

## Title
Replace Keycloak Database Password Authentication with RDS IAM Authentication

## Labels
- enhancement
- infra
- security

## Description

### Problem Statement
Currently, Keycloak connects to its Aurora MySQL database using static username/password credentials stored in AWS Secrets Manager. This approach requires manual password rotation and presents security risks associated with long-lived credentials. To improve security posture and align with AWS best practices, we should migrate to RDS IAM database authentication which provides short-lived, automatically rotated credentials.

### Proposed Solution
1. Enable IAM database authentication on the Aurora MySQL cluster
2. Modify the Keycloak ECS task to generate short-lived IAM auth tokens via `rds:GenerateDBAuthToken`
3. Update IAM roles/policies to grant the necessary permissions
4. Remove static database credentials from AWS Secrets Manager configuration
5. Maintain backward compatibility with password authentication as a feature-flagged fallback

### User Stories
- As an operator deploying on AWS ECS + RDS (Terraform), I want to use IAM authentication for Keycloak database connections to improve security.
- As a security engineer, I want to eliminate static database credentials to reduce the attack surface.
- As an operator, I want the ability to fall back to password authentication if needed during migration.

### Acceptance Criteria
- [ ] IAM database authentication is enabled on the Aurora MySQL cluster
- [ ] Keycloak ECS task generates short-lived IAM auth tokens for database connections
- [ ] IAM roles/policies are updated to allow `rds:GenerateDBAuthToken`
- [ ] Static database password is removed from Secrets Manager configuration
- [ ] Password authentication remains available as a feature-flagged fallback
- [ ] Backward compatibility is maintained during transition

### Out of Scope
- Changing the Keycloak version
- Modifying other database configurations beyond the authentication mechanism
- Helm/EKS deployment configurations (focus on ECS/RDS/Terraform only)

### Dependencies
- AWS RDS Aurora MySQL cluster
- Keycloak ECS service
- Existing Terraform infrastructure

### Related Issues
- None
