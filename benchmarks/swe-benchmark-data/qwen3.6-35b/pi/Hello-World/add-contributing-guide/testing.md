# Testing Plan: Add CONTRIBUTING.md Guide

*Created: 2025-01-31*
*Related LLD: `./lld.md`*
*Related Issue: `./github-issue.md`*

## Overview
### Scope of Testing
Verify that the new `CONTRIBUTING.md` file exists at the repository root, contains all required sections (issue filing, PR process, basic expectations), renders correctly as Markdown, and that no existing files were modified.

### Prerequisites
- [ ] Access to the Hello-World repository at `/tmp/swe-clone-add-contributing-guide/Hello-World`

### Shared Variables
```bash
REPO="/tmp/swe-clone-add-contributing-guide/Hello-World"
```

## 1. Functional Tests

### 1.1 File Existence
```bash
test -f "$REPO/CONTRIBUTING.md" && echo "PASS: CONTRIBUTING.md exists" || echo "FAIL: CONTRIBUTING.md missing"
```

### 1.2 File Content Checks
```bash
# Check that CONTRIBUTING.md contains required sections
grep -qi "issue" "$REPO/CONTRIBUTING.md" && echo "PASS: Issue section present" || echo "FAIL: Missing issue section"
grep -qi "pull.request\|fork" "$REPO/CONTRIBUTING.md" && echo "PASS: PR section present" || echo "FAIL: Missing PR section"
grep -qi "expectation\|contribution" "$REPO/CONTRIBUTING.md" && echo "PASS: Expectations section present" || echo "FAIL: Missing expectations section"
```

### 1.3 Markdown Validity
```bash
# Check that the file uses valid Markdown syntax (basic sanity check)
head -1 "$REPO/CONTRIBUTING.md" | grep -q "^#" && echo "PASS: File starts with heading" || echo "FAIL: No top-level heading"
```

## 2. Backwards Compatibility Tests
**Not Applicable** — the change adds a new file only; no existing functionality, schema, or behavior is modified.

## 3. UX Tests

### 3.1 Rendering Preview (GitHub)
On GitHub, a `CONTRIBUTING.md` at the root is automatically detected. The following should be true:
- [ ] The file renders as properly formatted Markdown (not raw text)
- [ ] Headings, bullet lists, and paragraphs are rendered correctly
- [ ] The file is readable and visually clean at a reasonable screen width

### 3.2 Clarity of Instructions
- [ ] A first-time contributor can understand how to file an issue by reading the document
- [ ] A first-time contributor can understand how to open a pull request by reading the document
- [ ] The document sets a welcoming, respectful tone

## 4. Deployment Surface Tests
**Not Applicable** — no deployment infrastructure, configuration files, or environment variables are affected.

## 5. End-to-End Tests

### 5.1 Full File Review
```bash
echo "=== Contents of CONTRIBUTING.md ==="
cat "$REPO/CONTRIBUTING.md"
echo ""
echo "=== Line count ==="
wc -l "$REPO/CONTRIBUTING.md"
```

Expected:
- The file should be between 40 and 100 lines (appropriate length for a minimal repo)
- All three required sections are present and clearly separated by headings
- No broken Markdown syntax (unclosed lists, malformed headings, etc.)

## 6. Test Execution Checklist
- [ ] Section 1 (File existence and content) passes
- [ ] Section 2 (Backwards Compat) verified as Not Applicable
- [ ] Section 3 (UX) verified — document is readable and well-formatted
- [ ] Section 4 (Deployment) verified as Not Applicable
- [ ] Section 5 (Full file review) — file looks correct at a glance
- [ ] No existing files (README, .git/) were modified: `git -C "$REPO" diff --stat` shows only `CONTRIBUTING.md` as added
