# Testing Plan: Add CONTRIBUTING.md

*Created: 2026-08-24*
*Related LLD: `./lld.md`*
*Related Issue: `./github-issue.md`*

## Overview

### Scope of Testing
This test plan verifies that the CONTRIBUTING.md file exists, is properly formatted, contains all required sections, and is discoverable in the repository. Since this is a documentation-only change with no code execution, testing focuses on content validation and GitHub platform integration.

### Prerequisites
- Repository cloned locally at the specified tag/branch
- Ability to view rendered Markdown in GitHub's web interface
- Text editor or IDE for manual content review

### Shared Variables
```bash
REPO_ROOT="/path/to/Hello-World"
CONTRIBUTING_FILE="$REPO_ROOT/CONTRIBUTING.md"
```

---

## 1. Functional Tests

### 1.1 File Existence Test
**Objective:** Verify CONTRIBUTING.md exists in the repository root

**Steps:**
```bash
# Check file exists
test -f "$CONTRIBUTING_FILE" && echo "PASS: File exists" || echo "FAIL: File missing"

# Check file is readable
test -r "$CONTRIBUTING_FILE" && echo "PASS: File is readable" || echo "FAIL: File not readable"

# Check file is not empty
test -s "$CONTRIBUTING_FILE" && echo "PASS: File has content" || echo "FAIL: File is empty"

# Show file size
wc -l "$CONTRIBUTING_FILE"
```

**Expected Result:**
- File exists at repository root
- File is readable
- File contains content (target: 150-200 lines)

---

### 1.2 Markdown Syntax Validation

**Objective:** Verify the file is valid Markdown and renders without errors

**Steps:**

1. **Visual Inspection on GitHub:**
   - Navigate to the repository on github.com
   - Click on CONTRIBUTING.md in the file browser
   - Verify: All sections render correctly, no syntax errors, formatting looks clean

2. **Markdown Structure Check:**
   ```bash
   # Check for proper heading hierarchy (H1, then H2 sections)
   grep -E "^#{1,2} " "$CONTRIBUTING_FILE" | head -10
   
   # Expected output:
   # # Contributing to Hello-World
   # ## Welcome!
   # ## How to Report Issues
   # etc.
   ```

3. **Special Characters Check:**
   ```bash
   # Verify no broken links or incomplete markdown
   grep -E "\[.*\]\(" "$CONTRIBUTING_FILE"  # External links
   grep -E "\*\*.*\*\*" "$CONTRIBUTING_FILE"  # Bold text
   ```

**Expected Result:**
- File renders correctly on GitHub without errors
- Proper heading hierarchy (H1 title, H2 sections)
- All markdown formatting renders as intended

---

### 1.3 Required Content Sections Test

**Objective:** Verify all required sections are present in the document

**Steps:**

For each section, run:
```bash
# Welcome section
grep -i "welcome" "$CONTRIBUTING_FILE" && echo "PASS: Welcome section found"

# Issues reporting section
grep -i "report.*issue\|issues" "$CONTRIBUTING_FILE" && echo "PASS: Issue reporting section found"

# Pull request section
grep -i "pull request\|submit.*pr" "$CONTRIBUTING_FILE" && echo "PASS: PR submission section found"

# Review workflow section
grep -i "review workflow\|review process" "$CONTRIBUTING_FILE" && echo "PASS: Review workflow section found"

# Security reporting section (REQUIRED per review)
grep -i "security\|vulnerability" "$CONTRIBUTING_FILE" && echo "PASS: Security reporting section found"

# Code of conduct section
grep -i "code of conduct\|conduct" "$CONTRIBUTING_FILE" && echo "PASS: Code of conduct section found"

# Questions/support section
grep -i "question\|support\|help" "$CONTRIBUTING_FILE" && echo "PASS: Support section found"
```

**Expected Result:**
- All 7 sections are present in the document
- Each section has relevant keywords

---

### 1.4 Key Content Details Test

**Objective:** Verify specific important information is included

**Steps:**

1. **PR Review Timeline:**
   ```bash
   grep -i "2.*3.*business.*day\|business.*day\|review.*time" "$CONTRIBUTING_FILE"
   # Should mention "2-3 business days" or similar
   ```

2. **Security Contact Information:**
   ```bash
   grep -i "security@\|security.*email\|report.*security" "$CONTRIBUTING_FILE"
   # Should provide contact method for security issues
   ```

3. **Merge Criteria:**
   ```bash
   grep -i "approval\|merge criteria\|approved\|maintainer" "$CONTRIBUTING_FILE"
   # Should explain when PRs are merged
   ```

4. **Issue Reporting Instructions:**
   ```bash
   grep -i "describe\|steps\|reproduce\|issue format" "$CONTRIBUTING_FILE"
   # Should explain how to write a good issue
   ```

**Expected Result:**
- PR review timeline (2-3 business days) is documented
- Security contact/reporting method is provided
- Merge approval criteria are explained
- Issue reporting best practices are included

---

### 1.5 GitHub Integration Test

**Objective:** Verify GitHub recognizes and displays the file

**Steps:**

1. **GitHub Sidebar Detection:**
   - Navigate to the repository homepage on GitHub
   - Look for "Contribute" button or similar
   - Verify: Clicking it shows a link or reference to CONTRIBUTING.md

2. **Direct File Access:**
   - Visit: `https://github.com/{owner}/{repo}/blob/{branch}/CONTRIBUTING.md`
   - Verify: File renders correctly with proper formatting

3. **File Discovery:**
   ```bash
   # In the repo, check if file appears in root
   cd "$REPO_ROOT"
   ls -la | grep -i contributing
   
   # Expected output shows CONTRIBUTING.md in listing
   ```

**Expected Result:**
- File is discoverable via GitHub's UI
- Direct link to file works
- File renders in GitHub's markdown viewer

---

## 2. Backwards Compatibility Tests

**Not Applicable** - This is a new file addition with no impact on existing functionality, documentation, or code. There are no backwards compatibility concerns.

---

## 3. UX Tests

### 3.1 Content Clarity Test

**Objective:** Verify the content is clear and helpful to new contributors

**Steps:**

1. **Readability Check:**
   - Read the document as a new contributor would
   - Verify: Instructions are clear, not ambiguous
   - Verify: Each section flows logically

2. **Actionability Check:**
   - Can a reader follow the PR submission steps?
   - Can a reader understand how to report an issue?
   - Can a reader understand the review timeline?

3. **Tone Check:**
   - Is the tone welcoming and encouraging?
   - Are there no condescending or negative statements?
   - Does it feel like the project wants contributions?

**Expected Result:**
- Content is clear and easy to understand
- A new contributor could follow the instructions
- Tone is welcoming and professional

---

### 3.2 Error Message Clarity Test

**Objective:** Verify error/edge case guidance is present

**Steps:**

1. **Search for security guidance:**
   ```bash
   grep -A 3 "security" "$CONTRIBUTING_FILE"
   # Should explain NOT to post security issues publicly
   ```

2. **Search for timeline expectations:**
   ```bash
   grep -i "review.*time\|may vary\|busy" "$CONTRIBUTING_FILE"
   # Should set realistic expectations
   ```

**Expected Result:**
- Security issues are directed to private email, not public tracker
- Review timelines are realistic and set expectations

---

## 4. Deployment Surface Tests

**Not Applicable** - CONTRIBUTING.md is a static file served directly by GitHub. No Docker, Terraform, Helm, or infrastructure configuration is involved.

The file will be deployed automatically when merged to the repository, as GitHub provides built-in CONTRIBUTING.md rendering.

---

## 5. End-to-End Tests

### 5.1 New Contributor Workflow Test

**Objective:** Verify a hypothetical new contributor could follow the guidelines

**Scenario 1: Reporting a Bug**

1. New contributor finds CONTRIBUTING.md
2. Reads "How to Report Issues" section
3. Follows the guidelines (provides description, steps, impact)
4. Submits issue on GitHub
5. **Verification:** Issue contains required information

**Scenario 2: Submitting a Pull Request**

1. New contributor reads PR submission section
2. Forks repository
3. Creates feature branch
4. Makes changes per guidelines
5. Submits PR with proper description
6. **Verification:** PR follows the suggested format

**Scenario 3: Security Issue Discovery**

1. Contributor discovers a security vulnerability
2. Reads "Reporting Security Issues" section
3. Emails security@example.com instead of filing public issue
4. **Verification:** Security issue was reported privately

---

## 6. Content Validation Checklist

- [ ] File exists at `./CONTRIBUTING.md`
- [ ] File has no syntax errors (GitHub renders correctly)
- [ ] File size is appropriate (~150-200 lines)
- [ ] Welcome/overview section present
- [ ] Issue reporting section present and clear
- [ ] PR submission section present and clear
- [ ] Review workflow section present with 2-3 day timeline
- [ ] Security reporting section present with email contact
- [ ] Code of conduct section present
- [ ] Support/questions section present
- [ ] All required information is included (per review.md findings)
- [ ] Tone is welcoming and encouraging
- [ ] No broken links or incomplete formatting
- [ ] File is discoverable on GitHub
- [ ] New contributor could follow the guidelines

---

## Notes

- This test plan focuses on **validation only** - actual execution (running tests against the target repo) is out of scope for this skill
- GitHub automatically renders and discovers CONTRIBUTING.md, so no special deployment steps are required
- The CONTRIBUTING.md file should be reviewed by project maintainers before merging to ensure it matches their preferences and policies
- Maintainers should periodically review and update this file as the project evolves

---

## Exit Criteria

All items in the Content Validation Checklist must be satisfied before the change is considered complete.
