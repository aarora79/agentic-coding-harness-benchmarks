# Expert Review: Remove EFS from Terraform AWS ECS Deployment

*Created: 2026-07-25*
*Related LLD: `./lld.md`*
*Related Issue: `./github-issue.md`*

## Frontend Engineer (Pixel) Review

## Strengths
1. **Clear migration strategy**: The infrastructure is moving from EFS-based persistence to DocumentDB, which aligns with modern, scalable database architectures. The separation of services also makes the system more maintainable.

2. **Minimal frontend impact**: The EFS removal primarily affects backend storage layers and doesn't fundamentally change how the frontend interacts with the API. Most existing functionality should remain unaffected.

3. **Backward compatibility maintained**: Existing API endpoints and response formats appear to be preserved, ensuring frontend components can continue to function without major modifications.

## Concerns
1. **Scope configuration transition**: The system is moving from EFS-based scope configuration (`/efs/auth_config/scopes.yml`) to DocumentDB storage. This change requires updating the initialization process and could introduce deployment inconsistencies during the transition period.

2. **Persistent data handling**: Components like the MCP Gateway data directory (`/app/data` in mcpgw container) still rely on EFS for persistence. If these are moved to ephemeral storage without proper alternatives, it could lead to data loss or inconsistent user experiences.

3. **Deployment complexity**: The hybrid approach with some services using DocumentDB and others still potentially depending on EFS volumes could complicate deployment and troubleshooting processes for frontend developers.

## New libraries / infra dependencies required
None for frontend. The EFS removal appears to be a backend infrastructure change that doesn't require frontend library updates. However, developers may need to understand the new DocumentDB-based data access patterns.

## Better alternatives considered
1. **Gradual migration approach**: Instead of completely removing EFS, a phased approach could migrate services one by one, reducing deployment risk and allowing for rollback capabilities.

2. **EFS to EFS-like abstraction**: Creating an abstraction layer that can support both EFS and DocumentDB backends would allow for easier switching between storage mechanisms based on deployment requirements.

3. **Hybrid storage approach**: Keep EFS for truly file-based operations while using DocumentDB for structured data, maintaining the benefits of both systems.

## Recommendations
1. **Implement thorough testing during transition**: Ensure all scope management and user permission features are thoroughly tested during the migration from EFS to DocumentDB storage to prevent authorization issues.

2. **Update documentation for developers**: Clearly document the new storage architecture so frontend developers understand data persistence patterns and can troubleshoot issues effectively.

3. **Monitor deployment stability**: Implement monitoring for data consistency and access patterns during and after the transition to catch any issues early and ensure smooth operation.

## Questions for author
1. How will the existing EFS data be migrated to DocumentDB during the transition? Is there a data migration plan in place?

2. Are there any expected downtime or service interruptions during the EFS removal process that frontend users should be aware of?

## Verdict
APPROVED WITH CHANGES

## Backend Engineer (Byte) Review

## Strengths
1. Clear separation of concerns with dedicated EFS module that encapsulates all EFS-related resources
2. Well-defined mount points and access points for different services (auth-config, logs, mcpgw-data)
3. Proper use of EFS security groups with specific ingress rules limiting NFS access to VPC CIDR

## Concerns
1. Multiple services depend on EFS for critical data persistence including auth server configuration, logs, and mcpgw data
2. The post-deployment setup scripts heavily rely on EFS for scopes initialization which affects application startup
3. Removing EFS without proper data migration strategy could result in data loss for critical application configuration

## New libraries / infra dependencies required
Any replacement for EFS would require:
1. Alternative persistent storage solution (likely DocumentDB/S3 for config, CloudWatch for logs)
2. Potential application code changes to handle new storage mechanisms
3. Updated IAM policies for new storage services
4. Modified container images or initialization scripts to work with new storage

## Better alternatives considered
1. **Gradual migration approach**: Instead of immediate removal, migrate services one-by-one to DocumentDB/S3 while maintaining EFS temporarily
2. **Hybrid approach**: Keep EFS for logs only and move configuration to DocumentDB
3. **Enhanced ephemeral storage**: For development environments where persistence isn't critical, use larger ephemeral storage with backup/restore mechanisms

## Recommendations
1. Ensure all EFS-mounted data has a clear migration path to DocumentDB or S3 before removal, particularly the auth server scopes configuration file
2. Update container definitions to remove mountPoints and volume configurations referencing EFS
3. Modify post-deployment scripts to eliminate EFS-dependent initialization tasks and replace with DocumentDB/S3 equivalents

## Questions for author
1. What is the migration strategy for existing data in EFS, particularly the auth server scopes configuration?
2. Which services currently depending on EFS can safely switch to ephemeral storage without data loss?

## Verdict
NEEDS REVISION

The design needs revision to address data migration concerns and ensure no critical functionality is lost when removing EFS. A detailed migration plan for existing EFS data to alternative storage systems (DocumentDB/S3) is essential before proceeding with the removal.

## SRE/DevOps Engineer (Circuit) Review

## Strengths
1. **Cost Reduction & Simplification**: The design effectively removes unused infrastructure (EFS), which directly reduces costs and simplifies the architecture by eliminating unnecessary components.
2. **Clear Implementation Plan**: The step-by-step approach for removing EFS resources is well-documented, making it easy for implementers to follow and reducing the risk of missing components.
3. **Comprehensive Scope Coverage**: The plan addresses all aspects of EFS removal, including variables, outputs, volume mounts, and security groups, ensuring a complete cleanup.

## Concerns
1. **Application Dependency Validation**: The design assumes all services have been migrated to S3/DocumentDB, but there's no verification plan to confirm that no service still depends on EFS paths or data. This could lead to service disruptions post-deployment.
2. **Rollback Strategy**: There's no defined rollback plan if issues arise after EFS removal. Since EFS contained persistent data, the ability to quickly restore functionality is critical.
3. **Monitoring Transition**: The design doesn't specify how to monitor the transition from EFS-based to S3/DocumentDB-based operations, which is essential for detecting performance issues or failures.

## New libraries / infra dependencies required
No new dependencies are required. This change actually removes infrastructure dependencies rather than adding them.

## Better alternatives considered
An alternative approach would be a phased migration where EFS dependency is gradually removed service by service while maintaining the infrastructure until all services are confirmed to work without it. However, this approach would take longer and increase operational overhead.

## Recommendations
1. **Implement Pre-Deployment Validation**: Create a validation script that checks all services and configurations to ensure no remaining references to EFS paths or mounts before proceeding with removal.
2. **Add Observability for Migration**: Implement specific metrics and alerts to monitor service health, latency, and error rates during and after the transition to ensure S3/DocumentDB operations perform adequately.
3. **Create Rollback Documentation**: Develop a clear rollback procedure that includes how to quickly restore EFS if critical issues are discovered post-deployment, even if it's just for emergency data recovery.

## Questions for author
1. How will you verify that all application services have completely migrated away from EFS and no longer require any file system data that might have been stored there?
2. What monitoring and alerting will be implemented to detect any performance degradation or failures after switching from EFS to S3/DocumentDB storage?

## Verdict
APPROVED WITH CHANGES

The design is sound for removing EFS infrastructure, but should include validation steps to ensure no service dependencies remain and should enhance observability around the transition. The concerns about rollback strategy and dependency validation should be addressed before implementation.

## Security Engineer (Cipher) Review

## Strengths
1. **Clear Migration Strategy**: The design correctly identifies that all services have been migrated from EFS to S3/DocumentDB, ensuring data persistence is maintained through more appropriate storage mechanisms.
2. **Comprehensive Removal Approach**: The plan addresses all aspects of EFS removal, including infrastructure resources, volume mounts, variables, and outputs, reducing the attack surface by eliminating unused components.
3. **Encryption Continuity**: By moving to DocumentDB (which supports encryption) and S3 (which also supports encryption), the design maintains strong data protection practices.

## Concerns
1. **Authentication Path Transition**: The Auth Server currently relies on `/efs/auth_config/auth_config/scopes.yml` for scope configuration. The transition to DocumentDB for this configuration needs careful validation to ensure authorization policies are correctly enforced.
2. **Data Residue Risk**: Complete removal of EFS should be verified to ensure no sensitive data remains accessible through snapshots or backups that might still exist after resource deletion.
3. **IAM Permission Cleanup**: While EFS resources are removed, associated IAM permissions and policies may still exist and should be cleaned up to prevent privilege creep.

## New libraries / infra dependencies required
None. This change removes infrastructure dependencies rather than adding new ones.

## Better alternatives considered
An alternative approach could involve keeping EFS but reducing its throughput settings to minimize costs while maintaining availability for any unforeseen dependencies. However, this wouldn't achieve the goal of simplifying the architecture.

## Recommendations
1. **Verify Scope Configuration Migration**: Ensure the Auth Server's scope configuration is correctly migrated from the EFS file path to DocumentDB, validating that all authorization policies continue to function as expected.
2. **Implement Complete IAM Cleanup**: Beyond removing EFS resources, thoroughly audit and remove any IAM policies, roles, or permissions that were specifically granted for EFS access to prevent security misconfigurations.
3. **Validate EFS Backup/Snapshot Deletion**: Implement a verification step to ensure that any EFS snapshots or backups are also deleted to prevent data residue that could be accessed later.

## Questions for author
1. Has the migration of the Auth Server's scope configuration from `/efs/auth_config/auth_config/scopes.yml` to DocumentDB been tested to ensure authentication and authorization continue to function correctly?
2. Are there any backup or disaster recovery procedures that might still reference EFS resources that need to be updated or removed?

## Verdict
APPROVED WITH CHANGES

## SMTS (Sage) Review

## Strengths
1. **Clear problem identification and solution approach**: The design clearly articulates why EFS should be removed (unnecessary cost and complexity) and identifies exactly what needs to be changed in the Terraform configuration.
2. **Well-structured LLD**: The document follows a comprehensive format covering all aspects of the change from codebase analysis to rollout plan, making it easy for implementers to understand and execute.
3. **Thorough impact analysis**: The design carefully identifies all files that need to be modified and considers dependencies like IAM policies, environment variables, and service integrations.

## Concerns
1. **Potential service disruption risk**: While the design assumes services have been migrated to S3/DocumentDB, there's no verification plan in place to confirm this assumption before removing EFS, which could lead to service outages if incorrect.
2. **Incomplete handling of environment variables**: The design mentions that SCOPES_CONFIG_PATH needs to be updated to use DocumentDB instead of EFS, but doesn't provide specifics on how that migration will occur, potentially leaving services non-functional.
3. **Missing validation of downstream dependencies**: The design doesn't address whether any external systems depend on the EFS outputs that will be removed, which could break dependent systems.

## New libraries / infra dependencies required
This change removes infrastructure dependencies rather than adding them. Specifically, it eliminates the need for:
- AWS EFS resources (file systems, mount targets, access points)
- Related security groups and network configurations for EFS
- IAM policies granting EFS access to ECS services

## Better alternatives considered
The design considered two alternatives:
1. **Reducing EFS throughput**: While this would maintain compatibility, it doesn't fully address the complexity concerns and still incurs ongoing costs.
2. **Gradual migration**: Although safer, this approach wasn't selected because the design assumes services have already been migrated.

A hybrid approach could have been considered - temporarily keeping EFS with very low throughput while monitoring service health during the transition, providing a rollback option with minimal cost impact.

## Recommendations
1. **Add explicit validation steps**: Before removing EFS, add verification that all services function correctly with S3/DocumentDB by running integration tests that specifically check storage operations.
2. **Implement a phased rollout strategy**: Instead of removing EFS entirely at once, consider disabling EFS mounting in services first while keeping the infrastructure, verifying functionality, then completely removing the infrastructure.
3. **Document rollback procedures**: Include specific steps to quickly restore EFS if post-deployment issues are discovered, including how to migrate any new data that might have been written to S3/DocumentDB back to EFS if needed.

## Questions for author
1. How will you verify that all services have truly been migrated away from EFS dependency before removing the infrastructure? Is there a testing plan to confirm services function correctly without EFS?
2. What is the specific migration path for the SCOPES_CONFIG_PATH environment variable currently pointing to EFS - how will services access this configuration data after EFS removal?

## Verdict
NEEDS REVISION

## Review Summary

| Reviewer | Verdict | Blockers | Key Recommendations |
|----------|---------|----------|---------------------|
| Frontend (Pixel) | APPROVED WITH CHANGES | 2 | Implement thorough testing during transition; Update documentation for developers |
| Backend (Byte) | NEEDS REVISION | 3 | Ensure migration path for EFS data to DocumentDB/S3; Update container definitions to remove EFS mounts |
| SRE (Circuit) | APPROVED WITH CHANGES | 3 | Implement pre-deployment validation; Add observability for migration |
| Security (Cipher) | APPROVED WITH CHANGES | 3 | Verify scope configuration migration; Implement complete IAM cleanup |
| SMTS (Sage) | NEEDS REVISION | 3 | Add explicit validation steps; Implement phased rollout strategy |

Overall, the design to remove EFS from the Terraform AWS ECS deployment is generally well-structured and addresses the core goal of reducing infrastructure complexity and cost. However, several reviewers have identified critical concerns that need to be addressed before implementation:

1. **Data Migration Strategy**: A clear plan is needed for migrating existing EFS data to DocumentDB/S3, particularly for the auth server scopes configuration.
2. **Dependency Validation**: Verification is required to ensure no services still depend on EFS before removal.
3. **Rollback Procedures**: Documentation and procedures should be established for quickly restoring EFS if post-deployment issues arise.

The design should be revised to address these concerns, particularly the data migration strategy and dependency validation, before proceeding with implementation.
