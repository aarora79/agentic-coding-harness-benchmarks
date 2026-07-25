# GitHub Issue: Remove FAISS Dependency and Replace with DocumentDB Hybrid Search

## Title
Remove FAISS dependency and replace with DocumentDB native hybrid search implementation

## Labels
- refactor
- search
- dependencies
- tech-debt

## Description

### Problem Statement
FAISS is an obsolete dependency in this repository that complicates deployment and adds unnecessary complexity. The registry already has a robust DocumentDB-based hybrid search implementation that provides the same semantic search capabilities without requiring FAISS as a dependency.

### Proposed Solution
Completely remove FAISS from the codebase and rely solely on the existing DocumentDB native hybrid search functionality. This includes:
- Removing FAISS imports and code paths
- Removing the FAISS dependency from pyproject.toml
- Updating documentation to reference DocumentDB hybrid search instead
- Ensuring all search functionality continues to work as expected

### User Stories
- As an operator, I want to simplify deployment by removing unnecessary native library dependencies
- As a developer, I want to work with a simpler, more maintainable codebase without FAISS complexities
- As an end-user, I want search functionality to continue working exactly as before

### Acceptance Criteria
- [ ] All FAISS imports removed from codebase
- [ ] FAISS dependency removed from pyproject.toml
- [ ] FAISS-related Docker build steps removed
- [ ] FAISS-related tests removed or migrated
- [ ] Documentation updated to reference DocumentDB hybrid search
- [ ] All existing search behavior preserved and working
- [ ] No breaking changes to search API

### Out of Scope
- Changing the underlying search algorithm or behavior
- Modifying the DocumentDB hybrid search implementation
- Adding new search features

### Dependencies
- Existing DocumentDB hybrid search implementation must be fully functional

### Related Issues
- None
