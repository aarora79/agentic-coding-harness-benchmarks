# Testing Plan: Replace Keycloak Database Password Authentication with RDS IAM Authentication

*Created: 2026-07-25*
*Related LLD: `./lld.md`*
*Related Issue: `./github-issue.md`*

## Overview
### Scope of Testing
This testing plan covers the replacement of Keycloak database password authentication with RDS IAM authentication. The tests will verify that IAM authentication works correctly, fallback to password authentication functions properly, and all deployment surfaces are correctly configured.

### Prerequisites
- [ ] AWS account with permissions to create RDS clusters, ECS services, and IAM roles
- [ ] Terraform installed and configured
- [ ] AWS CLI configured with appropriate credentials
- [ ] Docker installed for building custom Keycloak image
- [ ] Existing Keycloak deployment for comparison

### Shared Variables
```bash
export AWS_REGION="us-west-2"
export KEYCLOAK_CLUSTER_NAME="keycloak-test"
export TF_VAR_keycloak_database_iam_auth_enabled="true"
```

## 1. Functional Tests
### 1.1 Terraform Configuration Tests
Verify Terraform configurations for IAM database authentication:

```bash
# Navigate to Terraform directory
cd /tmp/swe-clone-replace-keycloak-db-password-with-rds-iam/mcp-gateway-registry/terraform/aws-ecs

# Test that Terraform plan includes IAM auth enabled
terraform plan -var="keycloak_database_iam_auth_enabled=true" | grep -q "enable_iam_database_authentication.*true"

# Verify IAM policy includes rds:GenerateDBAuthToken permission
terraform plan -var="keycloak_database_iam_auth_enabled=true" | grep -q "rds:GenerateDBAuthToken"

# Test that RDS proxy IAM auth is set to REQUIRED when enabled
terraform plan -var="keycloak_database_iam_auth_enabled=true" | grep -q "iam_auth.*REQUIRED"

# Test that Terraform plan works with IAM auth disabled (fallback mode)
terraform plan -var="keycloak_database_iam_auth_enabled=false" | grep -q "enable_iam_database_authentication.*false"
```

Expected results:
- IAM database authentication should be enabled on the RDS cluster
- IAM policy should include `rds:GenerateDBAuthToken` permission
- RDS proxy should require IAM authentication when enabled
- Configuration should work with IAM auth disabled for fallback

### 1.2 Custom Keycloak Image Tests
Verify the custom Keycloak image with IAM auth support:

```bash
# Build the custom Keycloak image
cd /tmp/swe-clone-replace-keycloak-db-password-with-rds-iam/mcp-gateway-registry
docker build -f docker/keycloak/Dockerfile -t keycloak-iam-test .

# Verify AWS CLI is installed in the image
docker run --rm keycloak-iam-test aws --version

# Verify custom startup script exists
docker run --rm keycloak-iam-test ls -la /opt/keycloak/bin/start-keycloak.sh

# Test script execution with IAM auth enabled
docker run --rm -e KEYCLOAK_DB_IAM_AUTH_ENABLED=true -e AWS_REGION=us-west-2 keycloak-iam-test /bin/bash -c "echo '#!/bin/bash\necho \"DB_HOST=test.host\"' > /tmp/script.sh && chmod +x /tmp/script.sh && source /opt/keycloak/bin/start-keycloak.sh"

# Test script execution with IAM auth disabled (fallback)
docker run --rm -e KEYCLOAK_DB_IAM_AUTH_ENABLED=false keycloak-iam-test /bin/bash -c "source /opt/keycloak/bin/start-keycloak.sh; echo \$KEYCLOAK_DB_IAM_AUTH_ENABLED"
```

Expected results:
- AWS CLI should be installed and accessible
- Custom startup script should exist and be executable
- Script should handle both IAM auth enabled and disabled modes
- Environment variables should be correctly processed

## 2. Backwards Compatibility Tests
Ensure password authentication fallback works correctly:

```bash
# Test Terraform with IAM auth disabled
cd /tmp/swe-clone-replace-keycloak-db-password-with-rds-iam/mcp-gateway-registry/terraform/aws-ecs
terraform plan -var="keycloak_database_iam_auth_enabled=false" | grep -q "iam_auth.*DISABLED"

# Verify Secrets Manager credentials are still passed when IAM auth is disabled
terraform plan -var="keycloak_database_iam_auth_enabled=false" | grep -A5 -B5 "KC_DB_PASSWORD" | grep -q "valueFrom.*password"

# Verify Secrets Manager credentials are NOT passed when IAM auth is enabled
terraform plan -var="keycloak_database_iam_auth_enabled=true" | grep -A10 -B10 "keycloak_container_secrets" | grep -c "KC_DB_PASSWORD" | grep -q "1"  # Only username should be passed

# Test that feature flag variable works correctly
terraform plan -var="keycloak_database_iam_auth_enabled=false" | grep -q "KEYCLOAK_DB_IAM_AUTH_ENABLED.*false"
terraform plan -var="keycloak_database_iam_auth_enabled=true" | grep -q "KEYCLOAK_DB_IAM_AUTH_ENABLED.*true"
```

Expected results:
- When IAM auth is disabled: RDS proxy IAM auth is DISABLED, both username and password are passed from Secrets Manager
- When IAM auth is enabled: RDS proxy IAM auth is REQUIRED, only username is passed from Secrets Manager, password is generated dynamically
- Feature flag environment variable correctly reflects the configuration

## 3. UX Tests
**Not Applicable** - This is an infrastructure-level change that does not directly affect user interfaces.

## 4. Deployment Surface Tests
### 4.1 Terraform Wiring
```bash
# Test variables.tf includes new variable
grep -q "keycloak_database_iam_auth_enabled" /tmp/swe-clone-replace-keycloak-db-password-with-rds-iam/mcp-gateway-registry/terraform/aws-ecs/variables.tf

# Test terraform.tfvars.example includes example
grep -q "keycloak_database_iam_auth_enabled" /tmp/swe-clone-replace-keycloak-db-password-with-rds-iam/mcp-gateway-registry/terraform/aws-ecs/terraform.tfvars.example

# Verify RDS cluster configuration includes enable_iam_database_authentication
grep -A10 -B5 "enable_iam_database_authentication" /tmp/swe-clone-replace-keycloak-db-password-with-rds-iam/mcp-gateway-registry/terraform/aws-ecs/keycloak-database.tf | grep -q "var.keycloak_database_iam_auth_enabled"

# Verify RDS proxy configuration includes conditional iam_auth
grep -A10 -B5 "iam_auth" /tmp/swe-clone-replace-keycloak-db-password-with-rds-iam/mcp-gateway-registry/terraform/aws-ecs/keycloak-database.tf | grep -q "var.keycloak_database_iam_auth_enabled.*REQUIRED.*DISABLED"

# Verify ECS IAM policy includes rds:GenerateDBAuthToken
grep -A10 -B5 "rds:GenerateDBAuthToken" /tmp/swe-clone-replace-keycloak-db-password-with-rds-iam/mcp-gateway-registry/terraform/aws-ecs/keycloak-ecs.tf | grep -q "aws_rds_cluster.keycloak.arn"
```

Expected results:
- All deployment surfaces correctly reference the new configuration
- Conditional logic works for both enabled and disabled states

### 4.2 Deploy and Verify
**Not Applicable for benchmark** - Full deployment testing would require actual AWS resources and is out of scope for the design phase.

### 4.3 Rollback Verification
**Not Applicable for benchmark** - Rollback testing would require actual deployment and is out of scope for the design phase.

## 5. End-to-End API Tests
**Not Applicable** - This is an infrastructure change that doesn't add new API endpoints.

## 6. Test Execution Checklist
- [ ] Section 1 (Functional) tests pass
- [ ] Section 2 (Backwards Compat) verified
- [ ] Section 3 (UX) marked Not Applicable
- [ ] Section 4 (Deployment) tests pass
- [ ] Section 5 (E2E) marked Not Applicable
- [ ] Unit tests would be added for custom startup script logic (if implemented)
- [ ] Integration tests would be added for Terraform configurations (if implemented)
