# Testing Plan: Remove EFS from Terraform AWS ECS Deployment

*Created: 2026-07-25*
*Related LLD: `./lld.md`*
*Related Issue: `./github-issue.md`*

## Overview
### Scope of Testing
This testing plan covers the removal of EFS (Elastic File System) from the MCP Gateway Registry Terraform AWS ECS deployment. The change involves removing all EFS resources, volume mounts, and related configuration while ensuring services continue to function using S3/DocumentDB for storage.

### Prerequisites
- [ ] AWS account with appropriate permissions for ECS, EFS, DocumentDB, and S3
- [ ] Terraform CLI installed and configured
- [ ] Existing MCP Gateway Registry deployment with EFS enabled
- [ ] Access to DocumentDB and S3 buckets used for persistence
- [ ] Auth0, Okta, or Entra ID credentials for authentication testing (if applicable)

### Shared Variables
```bash
export AWS_REGION="us-west-2"
export TF_VAR_aws_region="us-west-2"
export MCP_GATEWAY_DIR="/tmp/swe-clone-remove-efs-from-terraform-aws-ecs/mcp-gateway-registry/terraform/aws-ecs"
```

## 1. Functional Tests
### 1.1 Terraform Tests
Test that Terraform can successfully plan and apply the changes without EFS.

```bash
# Navigate to the terraform directory
cd $MCP_GATEWAY_DIR

# Initialize terraform
terraform init

# Validate the configuration
terraform validate

# Plan the changes (should show EFS resources being destroyed)
terraform plan -out=tfplan

# Check that EFS resources are marked for destruction
terraform show -json tfplan | jq '.planned_values.root_module.resources[] | select(.type | startswith("aws_efs"))' || echo "No EFS resources found in plan - this is expected"

# Apply the changes
terraform apply tfplan

# Verify that no EFS resources exist
terraform state list | grep efs || echo "No EFS resources in state - this is expected"
```

### 1.2 Service Deployment Tests
Test that all ECS services deploy successfully without EFS volumes.

```bash
# Check that all ECS services are running
cd $MCP_GATEWAY_DIR
terraform output

# Verify ECS service statuses
CLUSTER_NAME=$(terraform output -raw ecs_cluster_name)
aws ecs list-services --cluster $CLUSTER_NAME

# Check service status for each service
for service in $(aws ecs list-services --cluster $CLUSTER_NAME --query 'serviceArns[].split(`/`, @)[1]' --output text); do
  echo "Checking service: $service"
  aws ecs describe-services --cluster $CLUSTER_NAME --services $service --query 'services[0].{serviceName:serviceName,status:status,runningCount:runningCount,pendingCount:pendingCount}'
done
```

## 2. Backwards Compatibility Tests
Since this is a removal of infrastructure rather than a change to APIs, backwards compatibility is not directly applicable. However, we need to verify that the application continues to function the same way.

### 2.1 Configuration Persistence Tests
Test that configuration settings that were previously stored in EFS are now properly stored in DocumentDB.

```bash
# Get the registry URL
REGISTRY_URL=$(terraform output -raw mcp_gateway_url)

# Test that scopes configuration is accessible (was previously in EFS)
curl -s -f "$REGISTRY_URL/api/config" | jq '.' || echo "Failed to get config from DocumentDB"

# Test authentication (if enabled)
# This would depend on the specific IdP configuration
echo "Manual verification needed: Ensure authentication works with DocumentDB-stored scopes"
```

### 2.2 Environment Variable Tests
Verify that environment variables no longer reference EFS paths.

```bash
# Get ECS cluster and service information
CLUSTER_NAME=$(terraform output -raw ecs_cluster_name)
AUTH_SERVICE_NAME=$(terraform output -json ecs_service_names | jq -r '.auth')

# Check environment variables for auth service
TASK_DEFINITION_ARN=$(aws ecs describe-services --cluster $CLUSTER_NAME --services $AUTH_SERVICE_NAME --query 'services[0].taskDefinition' --output text)
aws ecs describe-task-definition --task-definition $TASK_DEFINITION_ARN --query 'taskDefinition.containerDefinitions[0].environment[].name' | grep SCOPES_CONFIG_PATH && echo "ERROR: SCOPES_CONFIG_PATH still exists" || echo "SUCCESS: SCOPES_CONFIG_PATH removed"

# Verify no EFS mount points exist
aws ecs describe-task-definition --task-definition $TASK_DEFINITION_ARN --query 'taskDefinition.containerDefinitions[0].mountPoints' | grep -i efs && echo "ERROR: EFS mount points still exist" || echo "SUCCESS: No EFS mount points found"
```

## 3. UX Tests
**Not Applicable** - This infrastructure change does not modify any user interface elements.

## 4. Deployment Surface Tests
### 4.1 Terraform Wiring Tests
Test that all Terraform variables and outputs related to EFS have been removed.

```bash
# Check that EFS variables are no longer defined
cd $MCP_GATEWAY_DIR
grep -r "efs_" variables.tf && echo "ERROR: EFS variables still exist" || echo "SUCCESS: No EFS variables found"

# Check that EFS outputs are no longer defined
grep -r "efs_" outputs.tf && echo "ERROR: EFS outputs still exist" || echo "SUCCESS: No EFS outputs found"

# Check terraform.tfvars.example
grep -i "efs" terraform.tfvars.example && echo "ERROR: EFS references still exist in example file" || echo "SUCCESS: No EFS references in example file"
```

### 4.2 ECS Wiring Tests
Test that ECS task definitions no longer include EFS volumes or mount points.

```bash
# Check that module.mcp_gateway no longer has EFS outputs
cd $MCP_GATEWAY_DIR
terraform output mcp_gateway_efs_id && echo "ERROR: EFS output still exists" || echo "SUCCESS: EFS output removed"
terraform output mcp_gateway_efs_arn && echo "ERROR: EFS output still exists" || echo "SUCCESS: EFS output removed"
```

### 4.3 Deploy and Verify Tests
Test that a fresh deployment works without EFS.

```bash
# Create a test directory for fresh deployment
TEST_DEPLOY_DIR="/tmp/mcp-gateway-test-deploy"
mkdir -p $TEST_DEPLOY_DIR
cp -r $MCP_GATEWAY_DIR/* $TEST_DEPLOY_DIR/
cd $TEST_DEPLOY_DIR

# Create a minimal terraform.tfvars for testing
cat > terraform.tfvars <<EOF
ingress_cidr_blocks = ["0.0.0.0/0"]
storage_backend = "documentdb"
EOF

# Initialize and validate
terraform init
terraform validate

# Plan and check for EFS resources
terraform plan -out=testplan
terraform show -json testplan | jq '.planned_values.root_module.resources[] | select(.type | startswith("aws_efs"))' && echo "ERROR: EFS resources planned for new deployment" || echo "SUCCESS: No EFS resources planned"

# Clean up
cd /
rm -rf $TEST_DEPLOY_DIR
```

### 4.4 Rollback Verification Tests
**Not Applicable** - Since this is a removal of infrastructure, traditional rollback testing is not applicable. However, we should verify that a redeployment with EFS re-enabled would still work.

```bash
echo "Note: Rollback verification requires a separate test with EFS re-enabled, which is outside the scope of this change"
```

## 5. End-to-End API Tests
### 5.1 Registry API Tests
Test that the registry API continues to function properly without EFS.

```bash
# Get the registry URL
REGISTRY_URL=$(terraform output -raw mcp_gateway_url)

# Test basic registry endpoints
curl -s -f "$REGISTRY_URL/health" | jq '.' && echo "SUCCESS: Health check passed" || echo "ERROR: Health check failed"

curl -s -f "$REGISTRY_URL/api/status" | jq '.' && echo "SUCCESS: Status endpoint works" || echo "ERROR: Status endpoint failed"

# Test that API configuration is accessible from DocumentDB (formerly EFS)
curl -s -f "$REGISTRY_URL/api/config" | jq '.' && echo "SUCCESS: Config endpoint works" || echo "ERROR: Config endpoint failed"
```

### 5.2 Authentication Tests
Test that authentication continues to work with DocumentDB-based scope configuration.

```bash
echo "Manual verification needed: Test authentication flows with the deployed system"
echo "1. Navigate to $REGISTRY_URL"
echo "2. Attempt to log in with configured IdP"
echo "3. Verify that user permissions are correctly applied from DocumentDB"
```

## 6. Test Execution Checklist
- [ ] Section 1 (Functional) passes
- [ ] Section 2 (Backwards Compat) verified
- [ ] Section 3 (UX) marked Not Applicable
- [ ] Section 4 (Deployment) passes
- [ ] Section 5 (E2E) passes
- [ ] Manual verification of authentication flows completed
- [ ] terraform validate passes with no errors
- [ ] terraform plan shows EFS resources being destroyed
- [ ] All ECS services deploy and run successfully
- [ ] No EFS-related variables, outputs, or mount points remain
