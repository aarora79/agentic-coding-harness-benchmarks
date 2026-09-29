# Testing Plan: Add Contributing Guide

*Created: 2024*
*Related LLD: `./lld.md`*
*Related Issue: `./github-issue.md`*

## Overview

### Scope of Testing
This testing plan verifies that the CONTRIBUTING.md file and README update are correctly implemented. Since this is a documentation-only change, testing focuses on file existence, content completeness, Markdown validity, and user discoverability.

### Prerequisites
- [ ] Repository cloned locally at the master branch
- [ ] Ability to view files in text editor or terminal
- [ ] Ability to view repository on GitHub.com
- [ ] Git commands available (`git status`, `git diff`)

### Shared Variables
```bash
export REPO_ROOT="path/to/Hello-World"
export CONTRIBUTING_FILE="$REPO_ROOT/CONTRIBUTING.md"
export README_FILE="$REPO_ROOT/README"
```

---

## 1. Functional Tests

### 1.1 File Existence Test

**Test Case:** Verify CONTRIBUTING.md exists at repository root

**Steps:**
```bash
ls -la "$REPO_ROOT/CONTRIBUTING.md"
```

**Expected Result:**
```
-rw-r--r-- 1 user group NNNN DATE TIME CONTRIBUTING.md
```

**Assertion:**
- File exists at `$REPO_ROOT/CONTRIBUTING.md`
- File is readable (has `r` permission)
- File size > 500 bytes (contains substantial content)

**Negative Case:**
```bash
test ! -f "$REPO_ROOT/CONTRIBUTING.md" && echo "FAIL: File does not exist"
```

---

### 1.2 Content Completeness Test

**Test Case:** Verify CONTRIBUTING.md contains all required sections

**Steps:**
```bash
# Check for presence of required sections
echo "=== Checking for required sections ==="
for section in "Welcome" "Report Issues" "Submit Pull Requests" "Expectations" "Questions"; do
  if grep -qi "$section" "$CONTRIBUTING_FILE"; then
    echo "OK: '$section' section found"
  else
    echo "FAIL: '$section' section not found"
  fi
done
```

**Expected Result:**
```
OK: 'Welcome' section found
OK: 'Report Issues' section found
OK: 'Submit Pull Requests' section found
OK: 'Expectations' section found
OK: 'Questions' section found
```

**Assertions:**
- All five required sections present
- Sections are labeled clearly (headers or descriptive text)
- Content under each section is non-empty

---

### 1.3 Markdown Syntax Test

**Test Case:** Verify CONTRIBUTING.md is valid Markdown

**Steps:**
```bash
# Check for common Markdown issues
echo "=== Checking Markdown syntax ==="

# 1. Check for headers (at least 2)
HEADER_COUNT=$(grep -c "^#" "$CONTRIBUTING_FILE")
echo "Headers found: $HEADER_COUNT"
test "$HEADER_COUNT" -ge 2 && echo "OK: Multiple headers present" || echo "FAIL: Insufficient headers"

# 2. Check for balanced brackets and code blocks
UNCLOSED_BACKTICKS=$(grep -c '```$' "$CONTRIBUTING_FILE" | awk '{ if ($1 % 2 != 0) print "FAIL"; else print "OK" }')

# 3. Check for common Markdown patterns
if grep -qE "^\-\s+|^\*\s+|^\d+\." "$CONTRIBUTING_FILE"; then
  echo "OK: List formatting found"
else
  echo "Note: No bullet/numbered lists found (acceptable for minimal doc)"
fi

# 4. Verify no obviously broken links (URLs should start with http)
if grep -q "\[.*\](http" "$CONTRIBUTING_FILE"; then
  echo "OK: Valid links present"
fi
```

**Expected Result:**
- Multiple headers present (at least 2)
- Code blocks properly closed (if any)
- List formatting follows Markdown conventions
- Links (if present) are properly formatted

---

### 1.4 Process Clarity Test

**Test Case:** Verify issue reporting process is clearly documented

**Steps:**
```bash
# Extract and display issue-related content
echo "=== Issue Reporting Section ==="
sed -n '/[Ii]ssue/,/Pull[Rr]equest/p' "$CONTRIBUTING_FILE" | head -20
```

**Expected Result:**
- Section mentions "issue", "bug", or "problem report"
- Includes guidance on what information to provide
- Mentions checking for existing issues
- Clear actionable steps (e.g., "Click Issues tab" or "Use issue template")

**Assertions:**
- Issue section exists and contains at least 3 sentences
- Mentions key concepts: reproduction steps, expected behavior, actual behavior
- Tone is welcoming

---

### 1.5 Pull Request Clarity Test

**Test Case:** Verify PR submission process is clearly documented

**Steps:**
```bash
# Extract PR-related content
echo "=== Pull Request Section ==="
sed -n '/[Pp]ull [Rr]equest/,/[Ee]xpectation/p' "$CONTRIBUTING_FILE" | head -20
```

**Expected Result:**
- Section mentions "pull request", "fork", or "branch"
- Includes fork workflow steps
- Mentions branch creation
- Describes PR description requirements
- Mentions linking related issues

**Assertions:**
- PR section exists and contains at least 5 sentences
- Key workflow steps present: fork → branch → commit → PR
- Tone is encouraging about review process

---

## 2. Backwards Compatibility Tests

**Not Applicable** - This is a new file addition with no backwards compatibility concerns. The README may be updated, but existing README content is preserved and extended, not modified.

---

## 3. UX Tests

### 3.1 GitHub Discoverability Test

**Test Case:** Verify CONTRIBUTING.md is discoverable on GitHub

**Steps:**
1. Push changes to a test branch on GitHub
2. Navigate to repository main page: https://github.com/{owner}/{repo}
3. Look for "Contributing" link or indicator

**Expected Result:**
- GitHub displays a "Contributing" section on the repository page
- Clicking "Contributing" or similar link navigates to CONTRIBUTING.md
- File is rendered with proper Markdown formatting

**Manual Verification (if GitHub access available):**
```
✓ Repository page shows "Contributing" option
✓ Clicking navigates to CONTRIBUTING.md
✓ Content displays correctly formatted
✓ Markdown links are clickable
```

---

### 3.2 README Integration Test

**Test Case:** Verify README mentions CONTRIBUTING.md or includes link

**Steps:**
```bash
echo "=== Checking README for Contributing reference ==="
if grep -qi "contribut\|contributing\|guidelines" "$README_FILE"; then
  echo "OK: README mentions contributing"
  grep -i "contribut" "$README_FILE"
else
  echo "Note: README does not explicitly mention contributing (acceptable if relying on GitHub discovery)"
fi
```

**Expected Result:**
- README is unchanged OR
- README includes a "Contributing" section with link to CONTRIBUTING.md

**Assertion:**
- At minimum, GitHub will auto-discover CONTRIBUTING.md without README changes
- If README is updated, link is properly formatted: `[Contributing](CONTRIBUTING.md)` or similar

---

### 3.3 Content Accessibility Test

**Test Case:** Verify text is beginner-friendly and non-technical

**Steps:**
```bash
echo "=== Analyzing tone and complexity ==="

# Check for welcoming language
for phrase in "welcome" "grateful" "thank" "help" "appreciate"; do
  if grep -qi "$phrase" "$CONTRIBUTING_FILE"; then
    echo "✓ Found welcoming phrase: $phrase"
  fi
done

# Check for overly technical language (should be minimal)
TECH_WORDS=$(grep -ioc "\(algorithm\|architecture\|deployment\|infrastructure\)" "$CONTRIBUTING_FILE")
echo "Technical terms found: $TECH_WORDS (should be low)"
```

**Expected Result:**
- At least 2-3 welcoming phrases present
- Minimal technical jargon
- Instructions use simple verbs (create, add, commit, push)
- Tone is warm and inclusive

---

## 4. Deployment Surface Tests

### 4.1 Git Repository Structure Test

**Test Case:** Verify files are in correct repository locations

**Steps:**
```bash
echo "=== Repository Structure Verification ==="

# Verify CONTRIBUTING.md location
test -f "$REPO_ROOT/CONTRIBUTING.md" && echo "✓ CONTRIBUTING.md in root" || echo "✗ Missing root CONTRIBUTING.md"

# Verify no duplicate files in subdirectories
DUPLICATES=$(find "$REPO_ROOT" -name "CONTRIBUTING.md" -not -path "*/.git/*" | wc -l)
test "$DUPLICATES" -eq 1 && echo "✓ Exactly one CONTRIBUTING.md file" || echo "✗ Multiple CONTRIBUTING.md files found"

# Verify README still exists
test -f "$README_FILE" && echo "✓ README preserved" || echo "✗ README missing"

# List all files in repo root
echo "=== Files in repository root ==="
ls -la "$REPO_ROOT" | grep -v "^\." | grep -v "^total"
```

**Expected Result:**
```
✓ CONTRIBUTING.md in root
✓ Exactly one CONTRIBUTING.md file
✓ README preserved
=== Files in repository root ===
README
CONTRIBUTING.md
```

---

### 4.2 Git Status and Diff Test

**Test Case:** Verify changes are properly tracked by Git

**Steps:**
```bash
cd "$REPO_ROOT"

echo "=== Git Status ==="
git status

echo ""
echo "=== New or Modified Files ==="
git diff --name-only HEAD

echo ""
echo "=== File Changes Summary ==="
git diff --stat HEAD
```

**Expected Result:**
```
Changes to be committed (or Untracked files):
  new file:   CONTRIBUTING.md
  [optional] modified: README
```

**Assertions:**
- CONTRIBUTING.md appears as new file (status: "A" or "??")
- README appears as modified (status: "M") if updated, or unchanged (status: "")
- No unexpected files changed

---

### 4.3 Deployment Readiness Test

**Test Case:** Verify patch can be applied cleanly

**Steps:**
```bash
# Assuming patch.diff has been generated
cd "$REPO_ROOT"

echo "=== Patch Validation ==="
git apply --check patch.diff && echo "✓ Patch applies cleanly" || echo "✗ Patch application failed"

# Show what the patch would add/remove
echo ""
echo "=== Patch Summary ==="
git diff --stat patch.diff
```

**Expected Result:**
- Patch applies without conflicts
- Summary shows CONTRIBUTING.md as new file (~100 lines added)
- No files deleted or unexpectedly modified

---

## 5. End-to-End API Tests

**Not Applicable** - This is a documentation-only change with no API endpoints, CLI commands, or programmatic interfaces to test.

---

## 6. Test Execution Checklist

### Core Functional Tests
- [ ] **1.1** CONTRIBUTING.md file exists at repository root
- [ ] **1.2** All five required sections present in CONTRIBUTING.md
- [ ] **1.3** CONTRIBUTING.md is valid Markdown with proper syntax
- [ ] **1.4** Issue reporting process is clearly documented with actionable steps
- [ ] **1.5** Pull request process is clearly documented with workflow steps

### Backwards Compatibility
- [ ] **Section 2** Marked Not Applicable (confirmed: no breaking changes)

### UX Tests
- [ ] **3.1** GitHub displays CONTRIBUTING.md in discovery UI (manual verification)
- [ ] **3.2** README is preserved and optionally linked
- [ ] **3.3** Content uses beginner-friendly, welcoming language

### Deployment Surface
- [ ] **4.1** Correct file locations in repository root
- [ ] **4.2** Git status shows expected file changes
- [ ] **4.3** Patch applies cleanly and contains only expected changes

### E2E Tests
- [ ] **Section 5** Marked Not Applicable (no API/CLI/integration endpoints)

### Manual Verification (if applicable)
- [ ] Repository pushed to GitHub
- [ ] GitHub displays "Contributing" indicator on repository page
- [ ] Clicking "Contributing" displays CONTRIBUTING.md with correct formatting
- [ ] Links in CONTRIBUTING.md (if any) are functional

---

## Success Criteria

**All tests must pass for the implementation to be considered complete:**

1. ✓ CONTRIBUTING.md exists with 4+ sections covering issues, PRs, and expectations
2. ✓ Valid Markdown with proper formatting
3. ✓ Beginner-friendly and welcoming tone
4. ✓ Clear, actionable instructions for contributors
5. ✓ File placement correct (repository root)
6. ✓ Git integration clean (tracked as new file)
7. ✓ GitHub displays file in UI (auto-discovery)

**Optional (nice-to-have):**
- [ ] README includes reference to CONTRIBUTING.md
- [ ] Examples provided (e.g., sample commit messages)
- [ ] Links to external resources included

---

## Notes for Implementer

- This document assumes local testing. For GitHub UI testing (Section 3.1, manual verification), the changes must be pushed to a real GitHub repository.
- The Markdown validation in 1.3 uses basic regex; for strict validation, use a tool like `markdownlint` (execution of external tools not required for this skill).
- Keep in mind that GitHub's `CONTRIBUTING.md` discovery is automatic and requires no configuration - just having the file in the repository root is sufficient.
