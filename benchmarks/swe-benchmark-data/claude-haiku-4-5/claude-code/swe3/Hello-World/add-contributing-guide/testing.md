# Testing Plan: Add CONTRIBUTING.md Guide

*Created: 2026-08-03*
*Related LLD: `./lld.md`*
*Related Issue: `./github-issue.md`*

## Overview

### Scope of Testing
Verification that CONTRIBUTING.md has been created, is readable, contains expected sections, and follows Markdown conventions. This is a documentation-only change, so testing focuses on file presence, content structure, and link validity.

### Prerequisites
- [ ] Repository cloned locally
- [ ] Read permissions on repository root
- [ ] Markdown viewer or terminal available

### Shared Variables
```bash
REPO_ROOT="."
CONTRIB_FILE="$REPO_ROOT/CONTRIBUTING.md"
```

## 1. Functional Tests

### 1.1 File Existence Test
**Objective:** Verify CONTRIBUTING.md exists at the repository root

**Test:**
```bash
test -f "$CONTRIB_FILE" && echo "✓ CONTRIBUTING.md exists" || echo "✗ CONTRIBUTING.md not found"
```

**Expected Output:**
```
✓ CONTRIBUTING.md exists
```

**Assertions:**
- File must be present at repository root
- File must be readable

---

### 1.2 File Content Structure Test
**Objective:** Verify the file contains all required sections

**Test:**
```bash
# Check for required section headers
for section in "How to File an Issue" "How to Open a Pull Request" "Contribution Expectations"; do
  grep -q "$section" "$CONTRIB_FILE" && echo "✓ Found: $section" || echo "✗ Missing: $section"
done
```

**Expected Output:**
```
✓ Found: How to File an Issue
✓ Found: How to Open a Pull Request
✓ Found: Contribution Expectations
```

**Assertions:**
- File must contain "How to File an Issue" section
- File must contain "How to Open a Pull Request" section
- File must contain "Contribution Expectations" section

---

### 1.3 Markdown Validation Test
**Objective:** Verify the file uses valid Markdown syntax

**Test:**
```bash
# Check for basic Markdown structure
if grep -q "^#" "$CONTRIB_FILE"; then
  echo "✓ Contains Markdown headers"
else
  echo "✗ No Markdown headers found"
fi

# Verify file is non-empty
if [ -s "$CONTRIB_FILE" ]; then
  LINES=$(wc -l < "$CONTRIB_FILE")
  echo "✓ File contains $LINES lines"
else
  echo "✗ File is empty"
fi
```

**Expected Output:**
```
✓ Contains Markdown headers
✓ File contains [N] lines (where N > 10)
```

**Assertions:**
- File must not be empty
- File must contain at least one Markdown header (#, ##, ###)
- File should contain at least 20 lines (a minimal guide)

---

### 1.4 Readability Test
**Objective:** Verify the file is readable and not corrupted

**Test:**
```bash
# Attempt to display the file and check for readable text
if head -1 "$CONTRIB_FILE" | grep -qE "[A-Za-z0-9]"; then
  echo "✓ File is readable with text content"
else
  echo "✗ File appears corrupted or empty"
fi
```

**Expected Output:**
```
✓ File is readable with text content
```

**Assertions:**
- File must be UTF-8 encoded (or ASCII)
- First few lines must contain readable text

---

## 2. Backwards Compatibility Tests

**Not Applicable** — This is a new file with no backwards-compatibility implications. Existing files (README, .git/) are untouched.

---

## 3. UX Tests

### 3.1 Manual Readability Check
**Objective:** Verify the guide is clear and beginner-friendly

**Test (Manual):**
```bash
# Display the file for visual inspection
cat "$CONTRIB_FILE"
```

**Verification Checklist:**
- [ ] Language is clear and not overly technical
- [ ] Sections are logically organized
- [ ] Examples are realistic and easy to follow
- [ ] No typos or grammatical errors
- [ ] Tone is welcoming and encouraging

---

### 3.2 GitHub UI Rendering Test
**Objective:** Verify the file displays correctly on GitHub

**Test (Manual):**
1. Push the repository to GitHub
2. Navigate to the repository main page
3. Verify "CONTRIBUTING" appears in the right sidebar (GitHub displays this for repositories with CONTRIBUTING.md)
4. Click "Contributing" to view the rendered Markdown
5. Verify all sections are readable and properly formatted

**Expected Rendering:**
- Markdown headers render correctly
- Bullet points display properly
- Code examples are formatted in monospace
- Links (if any) are clickable

---

## 4. Deployment Surface Tests

**Not Applicable** — This is a static documentation file. No deployment, Docker, Terraform, or Helm configuration is involved.

---

## 5. End-to-End Tests

### 5.1 New Contributor Workflow Test
**Objective:** Verify a new contributor can follow the guide to understand how to contribute

**Test (Manual):**
1. A new user reads README
2. User looks for contribution guidelines
3. User finds and reads CONTRIBUTING.md
4. User understands:
   - How to file an issue (what information to include, example format)
   - How to open a PR (step-by-step process)
   - What to expect in code review (expectations, turnaround time if mentioned)
5. User feels confident attempting a contribution

**Verification:**
- [ ] Guide is discoverable from the README or repository root
- [ ] Each section has a clear explanation
- [ ] Examples are sufficient for a newcomer to replicate the workflow

---

## 6. Test Execution Checklist

- [ ] Section 1.1: File Existence Test passes
- [ ] Section 1.2: File Content Structure Test passes (all sections found)
- [ ] Section 1.3: Markdown Validation Test passes (valid structure, non-empty)
- [ ] Section 1.4: Readability Test passes (file is readable)
- [ ] Section 2: Backwards Compatibility marked Not Applicable (no impacts)
- [ ] Section 3.1: Manual Readability Check passes (clear language, no errors)
- [ ] Section 3.2: GitHub UI Rendering Test passes (renders correctly on GitHub)
- [ ] Section 4: Deployment Surface marked Not Applicable (no deployment needed)
- [ ] Section 5.1: End-to-End Workflow Test passes (guide enables new contributor)

**Cumulative Pass Criteria:**
All non-N/A test sections must pass before the change is considered complete.

---

## Post-Implementation Verification Commands

Run these commands after implementation to verify success:

```bash
# Quick validation
test -f CONTRIBUTING.md && wc -l CONTRIBUTING.md && grep -c "^#" CONTRIBUTING.md

# Check for required sections
grep -E "(How to File|How to Open|Contribution Expectations)" CONTRIBUTING.md

# Display the file
cat CONTRIBUTING.md
```

Expected: File exists, contains multiple sections, has readable content.
