# Testing Plan: Migrate Sensitive ECS Environment Variables to AWS Secrets Manager

*Created: 2026-07-24*
*Related LLD: `./lld.md`*
*Related Issue: `./github-issue.md`*

## Overview
### Scope of Testing
This testing plan covers the migration of sensitive ECS environment variables to AWS Secrets Manager. The tests will verify that:
1. All sensitive environment variables are properly migrated to AWS Secrets Manager
2. ECS task definitions correctly reference AWS Secrets Manager resources
3. IAM policies grant appropriate access to Secrets Manager resources
4. Applications continue to function correctly with secrets retrieved from AWS Secrets Manager
5. Backward compatibility is maintained during the migration process

### Prerequisites
- [ ] AWS account with appropriate permissions for Secrets Manager, IAM, and ECS
- [ ] Existing mcp-gateway-registry deployment with Terraform
- [ ] Test environment that mirrors production setup
- [ ] Access to AWS CLI and Terraform CLI

### Shared Variables
```bash
export AWS_REGION="us-west-2"
export TERRAFORM_DIR="/path/to/terraform/aws-ecs"
export TEST_ENVIRONMENT="staging"
```

## 1. Functional Tests

### 1.1 Terraform Plan Tests
Test that Terraform plans correctly with the new Secrets Manager resources and IAM policy updates.

```bash
cd $TERRAFORM_DIR
terraform init
terraform plan -out=tfplan
terraform show -json tfplan | jq '.planned_values.root_module.resources[] | select(.type=="aws_secretsmanager_secret") | .name' | grep -q "registry-api-token" && echo "PASS: New Secrets Manager resources planned"
```

**Expected Result:** Terraform plan should include new AWS Secrets Manager resources and updated IAM policies without errors.

### 1.2 Secret Creation Tests
Test that AWS Secrets Manager resources are created correctly with proper encryption.

```bash
# After terraform apply, verify secrets exist and are encrypted
aws secretsmanager list-secrets --region $AWS_REGION | jq '.SecretList[].Name' | grep -q "registry-api-token" && echo "PASS: Secrets created"
aws secretsmanager list-secrets --region $AWS_REGION | jq '.SecretList[] | select(.Name | contains("registry-api-token")) | .KmsKeyId' | grep -q "arn:aws:kms" && echo "PASS: Secrets encrypted with KMS"
```

**Expected Result:** Secrets should be created with proper KMS encryption and accessible via AWS CLI.

### 1.3 IAM Policy Tests
Test that IAM policies are updated to grant access to new Secrets Manager resources.

```bash
# Get the IAM policy ARN from Terraform outputs or state
POLICY_ARN=$(terraform output -raw ecs_secrets_access_policy_arn)
aws iam get-policy-version --policy-arn $POLICY_ARN --version-id v1 | jq '.PolicyVersion.Document.Statement[].Resource[]' | grep -q "arn:aws:secretsmanager" && echo "PASS: IAM policy grants Secrets Manager access"
```

**Expected Result:** IAM policies should include references to the new Secrets Manager resources.

## 2. Backwards Compatibility Tests

### 2.1 Environment Variable Fallback Tests
Test that services continue to function when using plaintext environment variables as fallback.

```bash
# Temporarily disable secrets access to force fallback to environment variables
aws iam detach-role-policy --role-name test-task-exec-role --policy-arn $POLICY_ARN
# Restart ECS service
aws ecs update-service --cluster test-cluster --service test-service --force-new-deployment
# Monitor service health
aws ecs describe-services --cluster test-cluster --services test-service | jq '.services[].runningCount' | grep -q "1" && echo "PASS: Service running with fallback"
```

**Expected Result:** Services should continue to function using plaintext environment variables when Secrets Manager access is unavailable.

### 2.2 Gradual Migration Tests
Test that services can be migrated gradually from environment variables to Secrets Manager.

```bash
# Migrate one service at a time
# Verify each service functions correctly after migration
for service in auth-server registry mcpgw; do
  echo "Testing $service migration..."
  # Apply partial Terraform configuration
  # Verify service health
  aws ecs describe-services --cluster test-cluster --services $service | jq '.services[].runningCount' | grep -q "1" && echo "PASS: $service running after migration"
done
```

**Expected Result:** Individual services should be migratable without affecting other services.

## 3. UX Tests

### 3.1 Configuration Documentation Tests
**Not Applicable** - This change primarily affects infrastructure configuration rather than user interface elements.

### 3.2 Error Message Clarity Tests
Test that error messages are clear when secret access fails.

```bash
# Intentionally misconfigure IAM policy
# Attempt to deploy service
# Check CloudWatch logs for error messages
aws logs filter-log-events --log-group-name "/ecs/test-service" --start-time $(($(date +%s)-300)*1000) | grep -q "AccessDeniedException" && echo "PASS: Clear error message for access denial"
```

**Expected Result:** Error messages should clearly indicate when secret access is denied and provide guidance for resolution.

## 4. Deployment Surface Tests

### 4.1 Terraform Module Wiring Tests
Test that Terraform modules correctly wire in the new Secrets Manager resources.

```bash
# Check that secrets.tf contains new secret definitions
grep -q "registry_api_token" $TERRAFORM_DIR/modules/mcp-gateway/secrets.tf && echo "PASS: Secrets module updated"
# Check that iam.tf contains new policy statements
grep -q "aws_secretsmanager_secret.registry_api_token.arn" $TERRAFORM_DIR/modules/mcp-gateway/iam.tf && echo "PASS: IAM module updated"
```

**Expected Result:** Terraform modules should reference the new Secrets Manager resources in the correct locations.

### 4.2 ECS Task Definition Wiring Tests
Test that ECS task definitions correctly reference Secrets Manager resources.

```bash
# Get task definition
TASK_DEF_ARN=$(aws ecs describe-services --cluster test-cluster --services test-service | jq -r '.services[].taskDefinition')
aws ecs describe-task-definition --task-definition $TASK_DEF_ARN | jq '.taskDefinition.containerDefinitions[].secrets[].name' | grep -q "REGISTRY_API_TOKEN" && echo "PASS: Task definition references secrets"
```

**Expected Result:** ECS task definitions should reference Secrets Manager resources in the secrets block rather than environment block.

### 4.3 Deploy and Verify Tests
Test that services deploy correctly with secrets from AWS Secrets Manager.

```bash
# Deploy updated configuration
terraform apply -auto-approve
# Wait for deployment
sleep 60
# Verify service health
aws ecs describe-services --cluster test-cluster --services test-service | jq '.services[].runningCount' | grep -q "1" && echo "PASS: Service deployed with Secrets Manager"
# Verify secrets are being used
aws logs filter-log-events --log-group-name "/ecs/test-service" --start-time $(($(date +%s)-300)*1000) | grep -q "Successfully retrieved secret" && echo "PASS: Secrets retrieved from Secrets Manager"
```

**Expected Result:** Services should deploy successfully and retrieve secrets from AWS Secrets Manager.

### 4.4 Rollback Verification Tests
Test that rollback to environment variables works correctly.

```bash
# Revert Terraform changes
terraform plan -destroy
terraform destroy -auto-approve
# Redeploy original configuration
# terraform apply -auto-approve with original configuration
# Verify service health with environment variables
aws ecs describe-services --cluster test-cluster --services test-service | jq '.services[].runningCount' | grep -q "1" && echo "PASS: Service rolled back to environment variables"
```

**Expected Result:** Services should successfully roll back to using environment variables when Secrets Manager configuration is removed.

## 5. End-to-End API Tests

### 5.1 Secret Retrieval Workflow Tests
Test the end-to-end workflow of retrieving secrets from AWS Secrets Manager in a running container.

```bash
# Execute command in container to verify secret access
aws ecs execute-command --cluster test-cluster --task $(aws ecs list-tasks --cluster test-cluster | jq -r '.taskArns[0]') --container test-container --command "printenv | grep REGISTRY_API_TOKEN" --interactive
# Expected: Should show that REGISTRY_API_TOKEN is available
```

**Expected Result:** Applications should be able to retrieve secrets from AWS Secrets Manager at runtime.

### 5.2 Application Functionality Tests
Test that applications function correctly when using secrets from AWS Secrets Manager.

```bash
# For services that use secrets, test core functionality
# Example: Test registry API with authentication
curl -H "Authorization: Bearer $(aws secretsmanager get-secret-value --secret-id registry-api-token --query SecretString --output text)" https://test-registry.example.com/api/health | grep -q "healthy" && echo "PASS: Registry API working with Secrets Manager secrets"
```

**Expected Result:** Applications should function identically whether using secrets from AWS Secrets Manager or environment variables.

## 6. Test Execution Checklist
- [ ] Section 1 (Functional) passes
- [ ] Section 2 (Backwards Compat) verified
- [ ] Section 3 (UX) verified or marked Not Applicable
- [ ] Section 4 (Deployment) verified
- [ ] Section 5 (E2E) verified
- [ ] Unit tests added under `tests/unit/`
- [ ] Integration tests added under `tests/integration/`
- [ ] `terraform validate` passes with no errors
- [ ] All security scans pass with no new findings

## 7. Post-Migration Validation Tests

### 7.1 Secret Rotation Tests
Test that secrets can be rotated without service interruption.

```bash
# Update secret value
aws secretsmanager put-secret-value --secret-id registry-api-token --secret-string "new-test-token"
# Force ECS service update to refresh secrets
aws ecs update-service --cluster test-cluster --service test-service --force-new-deployment
# Wait for deployment
sleep 60
# Verify service is using new secret
# This would require application-specific validation
```

**Expected Result:** Services should seamlessly adopt new secret values after rotation.

### 7.2 Audit Trail Verification Tests
Test that secret access is properly audited.

```bash
# Check CloudTrail logs for secret access events
aws cloudtrail lookup-events --lookup-attributes AttributeKey=EventName,AttributeValue=GetSecretValue --max-results 10 | grep -q "secretsmanager" && echo "PASS: Secret access audited"
```

**Expected Result:** All secret access should be logged in CloudTrail for audit purposes.
