# Low-Level Design: Remove FAISS Dependency

## Overview

This document details the technical approach for removing the FAISS dependency from the MCP Gateway Registry while maintaining all existing search functionality through the DocumentDB hybrid search implementation.

## Current Architecture

### Search Repository Factory Pattern

The current architecture uses a factory pattern to instantiate search repositories based on the configured storage backend:

```python
# registry/repositories/factory.py
def get_search_repository() -> SearchRepositoryBase:
    global _search_repo

    if _search_repo is not None:
        return _search_repo

    backend = settings.storage_backend
    logger.info(f"Creating search repository with backend: {backend}")

    if backend in MONGODB_BACKENDS:
        from .documentdb.search_repository import DocumentDBSearchRepository
        _search_repo = DocumentDBSearchRepository()
    else:  # file backend
        from .file.search_repository import FaissSearchRepository
        _search_repo = FaissSearchRepository()

    return _search_repo
```

### FAISS Implementation Details

The FAISS implementation (`registry/search/service.py` and `registry/repositories/file/search_repository.py`) includes:
- In-memory FAISS index management with `IndexIDMap` and `IndexFlatIP`
- Manual index rebuilding on startup for persistence
- Custom embedding model loading and normalization
- Semantic search with keyword boosting
- Metadata storage in JSON files

### DocumentDB Implementation Details

The DocumentDB implementation (`registry/repositories/documentdb/search_repository.py`) includes:
- Native MongoDB vector search with HNSW indexes
- Automatic index creation with cosine similarity
- Hybrid search combining vector and keyword queries
- Reciprocal Rank Fusion (RRF) for result ranking
- Persistent storage that survives service restarts

## Target Architecture

After removing FAISS, the architecture will be simplified to use only the DocumentDB search repository:

```python
# registry/repositories/factory.py (after changes)
def get_search_repository() -> SearchRepositoryBase:
    global _search_repo

    if _search_repo is not None:
        return _search_repo

    # Always use DocumentDB implementation
    from .documentdb.search_repository import DocumentDBSearchRepository
    _search_repo = DocumentDBSearchRepository()
    logger.info("Created DocumentDB search repository")

    return _search_repo
```

## Detailed Changes

### 1. Dependency Removal

**File**: `pyproject.toml`
- Remove `"faiss-cpu>=1.7.4"` from dependencies

**Impact**: Reduces container image size and eliminates a complex native dependency

### 2. Configuration Cleanup

**File**: `registry/core/config.py`
- Remove FAISS-specific properties:
  - `faiss_index_path`
  - `faiss_metadata_path`

**Impact**: Cleans up unused configuration options

### 3. Code Implementation Removal

**Files to Delete**:
- `registry/search/service.py` - FAISS service implementation
- `registry/repositories/file/search_repository.py` - FAISS repository implementation

**Files to Modify**:
- `registry/repositories/factory.py` - Simplify to always return DocumentDB implementation
- `registry/main.py` - Remove FAISS-specific index rebuilding logic

### 4. Factory Pattern Simplification

**Before**:
```python
if backend in MONGODB_BACKENDS:
    from .documentdb.search_repository import DocumentDBSearchRepository
    _search_repo = DocumentDBSearchRepository()
else:
    from .file.search_repository import FaissSearchRepository
    _search_repo = FaissSearchRepository()
```

**After**:
```python
# Always use DocumentDB implementation
from .documentdb.search_repository import DocumentDBSearchRepository
_search_repo = DocumentDBSearchRepository()
```

### 5. Startup Logic Simplification

**Before**:
```python
# For DocumentDB, embeddings are persisted in the collection and survive
# restarts. Only FAISS (in-memory) needs a full re-index on every boot.
if settings.storage_backend not in MONGODB_BACKENDS:
    # FAISS re-indexing logic for servers, agents, and skills
    # ... extensive re-indexing code
else:
    logger.info("✅ DocumentDB search index is persistent, skipping startup re-index")
```

**After**:
```python
# DocumentDB search index is persistent, skipping startup re-index
logger.info("✅ DocumentDB search index is persistent, skipping startup re-index")
```

### 6. Search Routes Endpoint

The search endpoint in `registry/api/search_routes.py` remains unchanged since it already works with the abstract `SearchRepositoryBase` interface.

## Migration Path

### Phase 1: Safe Removal
1. Verify that DocumentDB implementation provides all required functionality
2. Remove FAISS dependencies from `pyproject.toml`
3. Remove unused configuration properties
4. Update factory to always return DocumentDB repository
5. Remove FAISS-specific startup re-indexing logic

### Phase 2: Code Cleanup
1. Delete FAISS service and repository implementation files
2. Remove any remaining FAISS imports or references
3. Update documentation and examples

### Phase 3: Validation
1. Run full test suite with DocumentDB backend
2. Verify search functionality works correctly
3. Confirm reduced deployment complexity

## Risk Mitigation

### Potential Issues

1. **Missing Features**: Ensure DocumentDB implementation covers all FAISS features
   - **Mitigation**: Thorough comparison of interfaces and functionality

2. **Performance Degradation**: DocumentDB might be slower than in-memory FAISS
   - **Mitigation**: DocumentDB native vector search is optimized and persistent

3. **Deployment Issues**: Dependencies on FAISS might be deeper than expected
   - **Mitigation**: Comprehensive search for imports and references

### Rollback Strategy

If issues are discovered after deployment:
1. Reintroduce FAISS dependencies in `pyproject.toml`
2. Restore factory logic to conditionally instantiate FAISS or DocumentDB repositories
3. Reinstate FAISS service and repository implementation files
4. This provides a rapid rollback path while root cause is investigated

## Testing Approach

### Unit Tests
- Verify factory always returns DocumentDBSearchRepository
- Confirm all search repository interface methods work correctly
- Test search functionality with various query types

### Integration Tests
- Test semantic search API endpoints
- Verify hybrid search with keyword and vector queries
- Confirm result ranking and scoring work as expected

### Performance Tests
- Compare search response times before and after changes
- Validate that DocumentDB implementation meets performance requirements

### Deployment Tests
- Test container build process without FAISS
- Verify reduced image size and build time
- Confirm no runtime errors related to missing FAISS

## Expected Outcomes

### Positive Impacts
- **Reduced Complexity**: Single search implementation to maintain
- **Simplified Deployment**: Smaller container images, fewer dependencies
- **Improved Reliability**: Persistent indexes that survive restarts
- **Better Maintainability**: Leverage database-native vector search capabilities

### Neutral Impacts
- **Functionality**: Equivalent search capabilities through DocumentDB
- **API Compatibility**: No changes to existing search endpoints
- **Performance**: Comparable or improved search performance

### Potential Negative Impacts
- **Initial Deployment Risk**: Possibility of undiscovered FAISS dependencies
- **Compatibility**: Risk of subtle differences in search behavior
- **Rollback Complexity**: Need to coordinate rollback if issues arise

## Success Metrics

1. **Build Success**: Container builds without FAISS dependency
2. **Deployment Success**: Service starts without FAISS-related errors
3. **Functional Parity**: All search functionality works identically
4. **Performance Maintenance**: Search response times remain acceptable
5. **Test Coverage**: All existing tests pass with DocumentDB backend
6. **Documentation Accuracy**: Updated docs reflect FAISS removal

## Timeline

### Estimate: 2-3 days

#### Day 1: Implementation
- Remove dependencies and configuration
- Update factory pattern
- Remove FAISS-specific startup logic
- Initial testing

#### Day 2: Code Cleanup and Testing
- Delete FAISS implementation files
- Remove remaining references
- Run full test suite
- Performance validation

#### Day 3: Documentation and Final Validation
- Update documentation
- Final integration testing
- Deployment validation
- Pull request preparation

This timeline assumes no major issues are discovered during implementation and testing phases.
