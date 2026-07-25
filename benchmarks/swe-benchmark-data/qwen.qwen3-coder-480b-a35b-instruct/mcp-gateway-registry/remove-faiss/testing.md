# Testing Plan: Remove FAISS Dependency

## Overview

This document outlines the comprehensive testing strategy for removing the FAISS dependency from the MCP Gateway Registry while ensuring all semantic search functionality continues to work correctly with the DocumentDB hybrid search implementation.

## Test Categories

### 1. Unit Testing

#### Factory Pattern Tests
- **Objective**: Verify that `get_search_repository()` always returns `DocumentDBSearchRepository`
- **Test Cases**:
  - Factory returns correct implementation type
  - Factory returns singleton instance on subsequent calls
  - Proper logging occurs during instantiation
- **Files**: `tests/unit/test_repository_factory.py`

#### Search Repository Interface Tests
- **Objective**: Ensure `DocumentDBSearchRepository` implements all required interface methods
- **Test Cases**:
  - All interface methods are implemented
  - Method signatures match interface expectations
  - Return types are correct
- **Files**: `tests/unit/test_search_repository_interface.py`

#### Configuration Tests
- **Objective**: Verify that FAISS-specific configuration has been removed properly
- **Test Cases**:
  - FAISS-specific properties are removed from settings
  - Storage backend validation works correctly
  - Default behavior is preserved
- **Files**: `tests/unit/test_config.py`

### 2. Integration Testing

#### Semantic Search API Tests
- **Objective**: Validate that semantic search endpoints work correctly
- **Test Cases**:
  - `/api/search/semantic` endpoint accepts queries and returns results
  - Various query types are handled (simple text, complex phrases)
  - Query parameters are processed correctly
  - Error handling for malformed requests
- **Files**: `tests/integration/test_search_api.py`

#### Entity-Specific Search Tests
- **Objective**: Ensure search works for all entity types
- **Test Cases**:
  - Server search functionality
  - Agent search functionality
  - Skill search functionality
  - Mixed entity type results
- **Files**: `tests/integration/test_entity_search.py`

#### Index Operations Tests
- **Objective**: Validate search index management operations
- **Test Cases**:
  - Indexing new servers/agents/skills
  - Updating existing entities in the index
  - Removing entities from the index
  - Bulk indexing operations
- **Files**: `tests/integration/test_index_operations.py`

#### Hybrid Search Tests
- **Objective**: Verify hybrid search (vector + keyword) functionality
- **Test Cases**:
  - Pure vector search results
  - Pure keyword search results
  - Combined hybrid search results
  - Reciprocal Rank Fusion (RRF) scoring
- **Files**: `tests/integration/test_hybrid_search.py`

### 3. Performance Testing

#### Search Response Time Tests
- **Objective**: Ensure search performance meets requirements
- **Test Cases**:
  - Single query response times (< 500ms target)
  - Concurrent query handling (10, 50, 100 concurrent users)
  - Large result set performance
  - Complex query performance
- **Tools**: Locust, Apache Bench, or custom performance test suite

#### Index Operation Performance Tests
- **Objective**: Validate indexing operations are efficient
- **Test Cases**:
  - Bulk indexing throughput
  - Incremental update performance
  - Index rebuild time (if applicable)
  - Memory usage during operations
- **Tools**: Custom benchmark scripts

#### Startup Performance Tests
- **Objective**: Confirm improved startup times without FAISS rebuild
- **Test Cases**:
  - Cold start time measurement
  - Warm start time measurement
  - Comparison with pre-change baseline
- **Tools**: Timing scripts, application metrics

### 4. Regression Testing

#### Existing Feature Tests
- **Objective**: Ensure no existing features are broken
- **Test Cases**:
  - All CRUD operations for servers/agents/skills
  - Authentication and authorization flows
  - Federation functionality
  - Health check endpoints
  - API compatibility with existing clients
- **Files**: Full existing test suite (`tests/regression/`)

#### Search Quality Tests
- **Objective**: Verify search result quality equivalence
- **Test Cases**:
  - Result relevance comparison with baseline
  - Ranking consistency validation
  - Edge case query handling
  - Special character and unicode support
- **Files**: `tests/regression/test_search_quality.py`

### 5. Deployment Testing

#### Build Process Tests
- **Objective**: Verify container builds succeed without FAISS
- **Test Cases**:
  - Docker image builds successfully
  - Image size reduction verification
  - Dependency installation completeness
  - No FAISS-related build errors or warnings
- **Tools**: CI/CD pipeline validation

#### Runtime Environment Tests
- **Objective**: Confirm service operates correctly in target environments
- **Test Cases**:
  - Container starts without errors
  - All endpoints are accessible
  - Health checks pass
  - Logging functions correctly
- **Environments**: Development, staging, and production-like environments

#### Configuration Tests
- **Objective**: Validate configuration handling without FAISS
- **Test Cases**:
  - Environment variable handling
  - Configuration file parsing
  - Default value assignments
  - Error messages for invalid configurations
- **Files**: `tests/deployment/test_configuration.py`

### 6. Security Testing

#### Dependency Vulnerability Tests
- **Objective**: Verify reduced attack surface
- **Test Cases**:
  - Dependency scan shows FAISS is removed
  - No new vulnerabilities introduced
  - Security scanning tools pass
- **Tools**: Snyk, OWASP Dependency Check, or similar

#### Input Validation Tests
- **Objective**: Confirm search input validation is maintained
- **Test Cases**:
  - SQL injection prevention
  - XSS protection in search results
  - Input length restrictions
  - Malformed query handling
- **Files**: `tests/security/test_input_validation.py`

## Test Execution Phases

### Phase 1: Pre-Implementation Baseline
- Run full existing test suite to establish baseline
- Capture performance metrics with current FAISS implementation
- Document current behavior for regression comparison

### Phase 2: Implementation Verification
- Run unit tests for factory pattern and configuration changes
- Verify build process works with FAISS dependencies removed
- Execute integration tests for basic search functionality

### Phase 3: Comprehensive Testing
- Run full integration test suite
- Execute performance tests and compare with baseline
- Validate deployment in staging environment
- Run security scans and vulnerability assessments

### Phase 4: Production Validation
- Canary deployment with limited traffic
- Monitor metrics and error rates
- Gradual rollout with continuous monitoring
- Full roll-forward confirmation

## Test Data Requirements

### Sample Entities
- **Servers**: 100+ sample MCP servers with varying descriptions
- **Agents**: 50+ sample A2A agents with different capabilities
- **Skills**: 75+ sample skills with diverse metadata

### Query Types
- **Simple Queries**: Single words, common phrases
- **Complex Queries**: Multi-word phrases, technical terms
- **Edge Cases**: Empty queries, very long queries, special characters
- **Negative Cases**: Malformed input, injection attempts

### Performance Test Data
- **Volume**: Large dataset for stress testing
- **Variety**: Diverse entity types and content
- **Velocity**: High-concurrency simulation

## Automation Strategy

### CI/CD Pipeline Integration
- Unit tests integrated in every build
- Integration tests run on pull requests
- Performance tests triggered for major changes
- Security scans run weekly or on dependency updates

### Monitoring During Deployment
- Real-time metric monitoring
- Automated alerting for anomalies
- Gradual rollout with rollback capability
- User impact monitoring

## Success Criteria

### Functional Requirements
- [ ] All existing search functionality works identically
- [ ] No regression in API response formats
- [ ] Error handling behaves consistently
- [ ] Authentication and authorization are preserved

### Performance Requirements
- [ ] Search response times ≤ baseline +/- 10%
- [ ] Indexing operations complete within acceptable timeframes
- [ ] Startup time is improved (no FAISS rebuild required)
- [ ] Memory usage is within acceptable limits

### Deployment Requirements
- [ ] Container builds successfully without errors
- [ ] All environments deploy without issues
- [ ] Health checks pass in all environments
- [ ] No runtime errors related to missing dependencies

### Quality Requirements
- [ ] Test coverage maintained or improved
- [ ] No critical or high-severity bugs introduced
- [ ] Security scan passes with reduced vulnerabilities
- [ ] Documentation accuracy verified

## Rollback Validation

### Pre-Change Preparation
- [ ] Backup current working implementation
- [ ] Document rollback procedure
- [ ] Validate rollback mechanism in test environment

### Rollback Testing
- [ ] Verify rollback process is smooth and reliable
- [ ] Confirm functionality is restored exactly as before
- [ ] Validate no data loss during rollback
- [ ] Test rollback speed meets SLA requirements

## Monitoring and Observability

### Key Metrics to Monitor
1. **Search Performance**: Response time, throughput, error rate
2. **Index Operations**: Indexing success rate, operation duration
3. **Resource Usage**: CPU, memory, disk I/O patterns
4. **Availability**: Uptime, health check pass rate
5. **User Impact**: API success rate, latency percentiles

### Alerting Thresholds
- Search response time > 1000ms (critical)
- Search response time > 500ms (warning)
- Indexing failure rate > 1% (warning)
- 5xx errors from search endpoints > 0.1% (warning)

### Dashboard Updates
- Update existing dashboards to remove FAISS-specific metrics
- Focus dashboards on DocumentDB search performance
- Maintain comparative views where useful

## Test Deliverables

### Documentation Outputs
1. **Test Report**: Comprehensive results from all test phases
2. **Performance Benchmark**: Before/after comparison with metrics
3. **Deployment Guide**: Updated procedures for deploying without FAISS
4. **Monitoring Guide**: Updated observability configuration

### Code Outputs
1. **Unit Tests**: Updated test suite for factory and configuration
2. **Integration Tests**: Complete test coverage for search functionality
3. **Performance Tests**: Scripts for ongoing performance validation
4. **Regression Tests**: Ensuring continued functionality

This comprehensive testing plan ensures that the FAISS removal is thoroughly validated while maintaining all existing functionality and quality standards.
