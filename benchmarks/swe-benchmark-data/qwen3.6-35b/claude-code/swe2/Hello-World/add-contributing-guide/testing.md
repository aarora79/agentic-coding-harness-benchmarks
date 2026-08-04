# Testing Plan: Add CONTRIBUTING.md Guide

*Created: 2026-07-31*
*Related LLD: `./lld.md`*
*Related Issue: `./github-issue.md`*

## Overview

### Scope of Testing
This testing plan covers verification of the new CONTRIBUTING.md file added to the Hello-World repository root. Since the change is a single new documentation file with no code, the tests focus on file existence, content correctness, and Markdown validity.

### Prerequisites
- [ ] The CONTRIBUTING.md file is present at the repository root
- [ ] The file is committed to the repository (or staged for commit)

### Shared Variables

```bash
REPO_DIR="/tmp/swe-clone-add-contributing-guide/Hello-World"
```

## 1. Functional Tests

### 1.1 File Existence

**Test:** Verify CONTRIBUTING.md exists at the repository root.

```bash
test -f "$REPO_DIR/CONTRIBUTING.md" && echo "PASS: CONTRIBUTING.md exists" || echo "FAIL: CONTRIBUTING.md missing"
```

**Expected:** File exists.

### 1.2 Content Section Tests

**Test:** Verify the file contains the required sections.

```bash
# Check for issue filing guidance
grep -qi "issue" "$REPO_DIR/CONTRIBUTING.md" && echo "PASS: Issue filing section present" || echo "FAIL: Missing issue filing section"

# Check for pull request steps
grep -qi "pull request" "$REPO_DIR/CONTRIBUTING.md" && echo "PASS: Pull request section present" || echo "FAIL: Missing pull request section"

# Check for expectations
grep -qi "expectation\|respectful\|constructive\|focused" "$REPO_DIR/CONTRIBUTING.md" && echo "PASS: Expectations section present" || echo "FAIL: Missing expectations section"
```

**Expected:** All three sections are present.

### 1.3 Negative Case

**Test:** Verify the file is not empty.

```bash
test -s "$REPO_DIR/CONTRIBUTING.md" && echo "PASS: CONTRIBUTING.md is non-empty" || echo "FAIL: CONTRIBUTING.md is empty"
```

**Expected:** File has content (more than 0 bytes).

## 2. Backwards Compatibility Tests

**Not Applicable** - This is a new file that does not modify any existing file. There are no backwards compatibility concerns.

## 3. UX Tests

### 3.1 Markdown Rendering

**Test:** Verify the file is valid Markdown with no broken formatting.

```bash
# Check for unclosed code blocks
open=$(grep -c '^```' "$REPO_DIR/CONTRIBUTING.md" || true)
if [ $((open % 2)) -eq 0 ]; then
    echo "PASS: Code blocks are balanced"
else
    echo "FAIL: Unclosed code block detected"
fi

# Check for major heading structure
grep -c '^#' "$REPO_DIR/CONTRIBUTING.md" | { read count; test "$count" -gt 0 && echo "PASS: File contains headings ($count)" || echo "FAIL: No headings found"; }
```

**Expected:** Code blocks are balanced, file has proper heading structure.

### 3.2 Readability

**Test:** Verify the file is human-readable and well-organized.

```bash
# Check that the file uses proper line lengths (no extremely long lines)
long_lines=$(awk 'length > 200' "$REPO_DIR/CONTRIBUTING.md" | wc -l)
if [ "$long_lines" -eq 0 ]; then
    echo "PASS: No excessively long lines"
else
    echo "WARN: $long_lines lines exceed 200 characters"
fi
```

**Expected:** File is readable with no extremely long lines.

## 4. Deployment Surface Tests

**Not Applicable** - This change adds a documentation file. There are no Docker, Helm, Terraform, or other deployment surfaces involved.

## 5. End-to-End Tests

### 5.1 GitHub Auto-Detection

**Test:** Verify that GitHub will auto-detect CONTRIBUTING.md from the repository root.

```bash
# GitHub auto-detects CONTRIBUTING.md from root or .github/ directory
# Verify it is at root (as designed in the LLD)
ls "$REPO_DIR/CONTRIBUTING.md" && echo "PASS: GitHub will auto-detect CONTRIBUTING.md" || echo "FAIL: File not at expected root location"
```

**Expected:** File is at the repository root where GitHub auto-detects it.

## 6. Test Execution Checklist

- [ ] Section 1.1 (File Existence) passes
- [ ] Section 1.2 (Content Sections) passes
- [ ] Section 1.3 (Non-Empty) passes
- [ ] Section 2 (Backwards Compatibility) verified as Not Applicable
- [ ] Section 3.1 (Markdown Validity) passes
- [ ] Section 3.2 (Readability) passes
- [ ] Section 4 (Deployment Surface) verified as Not Applicable
- [ ] Section 5 (GitHub Auto-Detection) passes
