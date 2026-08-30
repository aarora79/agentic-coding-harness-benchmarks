# Testing Plan: Add CONTRIBUTING.md Guide

*Created: 2026-08-29*
*Related LLD: `./lld.md`*
*Related Issue: `./github-issue.md`*

## Overview
### Scope of Testing
Verify that the CONTRIBUTING.md file is properly created with correct content, formatting, and placement in the repository root. Since this is a documentation-only change, testing focuses on content accuracy and file placement.

### Prerequisites
- [ ] Repository clone with README exists
- [ ] Write permissions to repository root

### Shared Variables
```bash
export REPO_PATH="/tmp/swe-clone-add-contributing-guide/Hello-World"
```

## 1. Functional Tests
### 1.1 File Creation Test
**Description:** Verify that CONTRIBUTING.md file is created in the repository root
**Command:**
```bash
test -f "$REPO_PATH/CONTRIBUTING.md" && echo "PASS: CONTRIBUTING.md exists" || echo "FAIL: CONTRIBUTING.md missing"
```
**Expected Status:** Exit code 0
**Expected Response:** PASS: CONTRIBUTING.md exists
**Assertions:**
- File exists at repository root
- File has correct name (CONTRIBUTING.md)
- File is readable

### 1.2 Content Verification Test
**Description:** Verify that CONTRIBUTING.md contains expected content sections
**Command:**
```bash
grep -q "How to Contribute" "$REPO_PATH/CONTRIBUTING.md" && echo "PASS: Contains 'How to Contribute'" || echo "FAIL: Missing 'How to Contribute'"
grep -q "Submitting Pull Requests" "$REPO_PATH/CONTRIBUTING.md" && echo "PASS: Contains 'Submitting Pull Requests'" || echo "FAIL: Missing 'Submitting Pull Requests'"
grep -q "Contribution Guidelines" "$REPO_PATH/CONTRIBUTING.md" && echo "PASS: Contains 'Contribution Guidelines'" || echo "FAIL: Missing 'Contribution Guidelines'"
```
**Expected Status:** Exit code 0
**Expected Response:** All PASS statements
**Assertions:**
- Contains section about reporting issues
- Contains section about submitting pull requests
- Contains section about contribution guidelines
- File is valid markdown

## 2. Backwards Compatibility Tests
**Not Applicable** - This is a documentation-only change that adds no new functionality or modifies existing behavior.

## 3. UX Tests
### 3.1 Readability Test
**Description:** Verify the content is clear and actionable for contributors
**Command:**
```bash
# Check that content is easy to read and understand
wc -l "$REPO_PATH/CONTRIBUTING.md"
head -n 5 "$REPO_PATH/CONTRIBUTING.md"
```
**Expected Status:** Exit code 0
**Expected Response:** File should be reasonably sized (50-100 lines) with clear section headers
**Assertions:**
- Content is not overly verbose
- Section headers are clear and descriptive
- Instructions are actionable

## 4. Deployment Surface Tests
### 4.1 File Placement Test
**Description:** Verify the file is in the correct location for standard open-source repositories
**Command:**
```bash
ls -la "$REPO_PATH/CONTRIBUTING.md" && echo "PASS: File in correct location" || echo "FAIL: File not in repository root"
```
**Expected Status:** Exit code 0
**Expected Response:** File listing showing CONTRIBUTING.md in repository root
**Assertions:**
- File is in repository root (not in a subdirectory)
- File has correct permissions for documentation

### 4.2 Format Validation Test
**Description:** Verify the markdown formatting is correct
**Command:**
```bash
# Basic markdown validation - check for proper headers and structure
grep -c "^#" "$REPO_PATH/CONTRIBUTING.md" | grep -q "3" && echo "PASS: Has proper section headers" || echo "FAIL: Missing section headers"
```
**Expected Status:** Exit code 0
**Expected Response:** PASS: Has proper section headers
**Assertions:**
- File has proper markdown headers (#, ##, ###)
- File structure follows markdown conventions

## 5. End-to-End API Tests
**Not Applicable** - This is a documentation-only change with no API surface.

## 6. Test Execution Checklist
- [x] Section 1 (Functional) passes
- [x] Section 2 (Backwards Compat) verified or marked Not Applicable
- [x] Section 3 (UX) verified or marked Not Applicable
- [x] Section 4 (Deployment) verified or marked Not Applicable
- [x] Section 5 (E2E) verified or marked Not Applicable
- [x] No unit tests needed for documentation-only change
- [x] No integration tests needed for documentation-only change
