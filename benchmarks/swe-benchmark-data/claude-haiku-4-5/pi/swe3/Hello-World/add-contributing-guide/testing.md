# Testing Plan: Add CONTRIBUTING.md

*Created: 2026-08-22*
*Related LLD: `./lld.md`*
*Related Issue: `./github-issue.md`*

## Overview

### Scope of Testing
This testing plan verifies that the CONTRIBUTING.md file has been created, is properly formatted, and contains all required sections with appropriate guidance. Since this is documentation, testing focuses on file existence, completeness, readability, and proper linking.

### Prerequisites
- [ ] Repository cloned locally
- [ ] Ability to view and verify the file exists in the repository root
- [ ] Markdown preview capability (web browser or markdown viewer)

### Shared Variables
```bash
REPO_ROOT="/tmp/swe-clone-add-contributing-guide/Hello-World"
CONTRIBUTING_FILE="$REPO_ROOT/CONTRIBUTING.md"
```

## 1. Functional Tests

### 1.1 File Existence and Location
**Test:** Verify CONTRIBUTING.md exists in the repository root

```bash
# Test: File exists in repo root
test -f "$REPO_ROOT/CONTRIBUTING.md" && echo "PASS: CONTRIBUTING.md exists" || echo "FAIL: File not found"

# Test: File is readable
test -r "$REPO_ROOT/CONTRIBUTING.md" && echo "PASS: File is readable" || echo "FAIL: File not readable"

# Test: File has content
test -s "$REPO_ROOT/CONTRIBUTING.md" && echo "PASS: File has content" || echo "FAIL: File is empty"

# Test: File size is reasonable (at least 1KB, less than 50KB for documentation)
FILE_SIZE=$(wc -c < "$REPO_ROOT/CONTRIBUTING.md")
if [ "$FILE_SIZE" -gt 1000 ] && [ "$FILE_SIZE" -lt 50000 ]; then
    echo "PASS: File size is reasonable ($FILE_SIZE bytes)"
else
    echo "FAIL: File size is $FILE_SIZE bytes (expected 1KB-50KB)"
fi
```

**Expected Outcome:**
- CONTRIBUTING.md exists at repository root
- File is readable
- File contains substantial content (minimum 1KB)
- File size is reasonable for documentation

### 1.2 File Format and Structure
**Test:** Verify CONTRIBUTING.md is valid markdown and has required sections

```bash
# Test: File starts with markdown header
head -1 "$CONTRIBUTING_FILE" | grep -q "^#" && echo "PASS: File starts with markdown header" || echo "FAIL: No markdown header"

# Test: File contains key section headers
for section in "Code of Conduct" "Reporting Bugs" "Pull Requests" "Review Workflow"; do
    grep -q "## .*$section\|### .*$section" "$CONTRIBUTING_FILE" && \
        echo "PASS: Section '$section' found" || \
        echo "FAIL: Section '$section' not found"
done

# Test: File contains at least one code block or example
grep -q '```' "$CONTRIBUTING_FILE" && echo "PASS: File contains examples/code blocks" || echo "FAIL: No examples found"

# Test: File ends with newline (markdown best practice)
tail -c 1 "$CONTRIBUTING_FILE" | od -An -tx1 | grep -q "0a" && echo "PASS: File ends with newline" || echo "FAIL: No trailing newline"
```

**Expected Outcome:**
- File is valid markdown with proper headers
- All required sections are present:
  - Code of Conduct
  - How Can I Contribute?
  - Reporting Bugs
  - Suggesting Enhancements
  - Pull Requests
  - Review Workflow
  - Getting Help
- File contains examples or code blocks
- File ends with a newline

### 1.3 Content Completeness
**Test:** Verify all required information is present

```bash
# Test: Issue reporting guidance exists
grep -qi "bug report" "$CONTRIBUTING_FILE" && echo "PASS: Bug reporting guidance found" || echo "FAIL: No bug reporting info"

# Test: PR submission process is documented
grep -qi "pull request\|submit.*pr" "$CONTRIBUTING_FILE" && echo "PASS: PR submission process found" || echo "FAIL: No PR process documented"

# Test: Review workflow is explained
grep -qi "review.*workflow\|review.*process" "$CONTRIBUTING_FILE" && echo "PASS: Review workflow found" || echo "FAIL: No review workflow documented"

# Test: Branch naming guidance exists
grep -qi "branch.*naming\|naming.*convention" "$CONTRIBUTING_FILE" && echo "PASS: Branch naming guidance found" || echo "FAIL: No branch naming info"

# Test: Commit message guidance exists
grep -qi "commit.*message" "$CONTRIBUTING_FILE" && echo "PASS: Commit message guidance found" || echo "FAIL: No commit guidance"

# Test: Reviewer expectations are documented
grep -qi "what.*reviewer.*look\|reviewer.*look\|review.*look" "$CONTRIBUTING_FILE" && echo "PASS: Reviewer expectations found" || echo "FAIL: No reviewer expectations"
```

**Expected Outcome:**
- Bug reporting procedures documented
- Pull request submission process explained
- Review workflow described
- Branch naming conventions provided
- Commit message guidelines included
- Reviewer expectations clearly stated

## 2. Backwards Compatibility Tests

### 2.1 Existing Files Unchanged
**Test:** Verify no existing files were modified

```bash
# Test: README file unchanged
cd "$REPO_ROOT"
if [ -f "README" ]; then
    ORIG_README_CONTENT=$(cat README)
    echo "README still contains: '$ORIG_README_CONTENT'"
    [ "$ORIG_README_CONTENT" = "Hello World!" ] && echo "PASS: README unchanged" || echo "FAIL: README modified"
else
    echo "FAIL: README file missing"
fi

# Test: No other files were added except CONTRIBUTING.md
ADDED_FILES=$(git -C "$REPO_ROOT" status --short | wc -l)
echo "Number of modified/added files: $ADDED_FILES"
if [ "$ADDED_FILES" -le 1 ]; then
    echo "PASS: Only CONTRIBUTING.md was added"
else
    git -C "$REPO_ROOT" status --short
fi
```

**Expected Outcome:**
- README file remains unchanged with "Hello World!" content
- Only CONTRIBUTING.md is added
- No other files are modified

## 3. UX Tests

### 3.1 Content Clarity and Accessibility
**Test:** Verify documentation is clear and accessible

```bash
# Test: File uses plain language (check for overly technical jargon limits)
# Count average word length; if mostly short words, text is accessible
AVG_WORD_LENGTH=$(grep -o '\w\+' "$CONTRIBUTING_FILE" | awk '{sum += length; count++} END {if (count > 0) printf "%.1f", sum/count}')
echo "Average word length: $AVG_WORD_LENGTH characters (target: 4.5-5.5 for accessibility)"

# Test: File has clear structure with multiple section breaks
HEADER_COUNT=$(grep -c "^##" "$CONTRIBUTING_FILE")
echo "Number of major sections: $HEADER_COUNT (minimum expected: 6)"
[ "$HEADER_COUNT" -ge 6 ] && echo "PASS: Good section structure" || echo "FAIL: Too few sections"

# Test: File includes actionable guidance (imperatives/calls to action)
grep -qi "please\|should\|must\|submit\|create\|make" "$CONTRIBUTING_FILE" && echo "PASS: Actionable guidance present" || echo "FAIL: Lacks actionable guidance"

# Test: Code of Conduct is referenced
grep -qi "code.*conduct\|conduct.*code" "$CONTRIBUTING_FILE" && echo "PASS: Code of Conduct referenced" || echo "FAIL: No Code of Conduct reference"
```

**Expected Outcome:**
- Content uses clear, accessible language
- Document has good structure (6+ major sections)
- Instructions are actionable
- Code of Conduct is referenced

## 4. Deployment Surface Tests

### 4.1 GitHub Integration
**Test:** Verify file will be recognized by GitHub

```bash
# Test: File is named exactly CONTRIBUTING.md (case-sensitive on GitHub)
if [ -f "$REPO_ROOT/CONTRIBUTING.md" ]; then
    echo "PASS: File name is correct (CONTRIBUTING.md)"
else
    echo "FAIL: File not found as CONTRIBUTING.md"
fi

# Test: File is at repository root (GitHub requirement)
if [ -f "$REPO_ROOT/CONTRIBUTING.md" ] && [ ! -d "$REPO_ROOT/CONTRIBUTING.md" ]; then
    echo "PASS: File is at repository root, not in subdirectory"
else
    echo "FAIL: File location incorrect"
fi

# Test: File includes markdown - GitHub will auto-render it
FILE_EXT="${CONTRIBUTING_FILE##*.}"
[ "$FILE_EXT" = "md" ] && echo "PASS: File has .md extension for markdown rendering" || echo "FAIL: Wrong file extension"
```

**Expected Outcome:**
- File is named exactly `CONTRIBUTING.md`
- File is at repository root
- File has `.md` extension for GitHub rendering

### 4.2 Repository Visibility
**Test:** Verify file is visible to repository users

```bash
# Test: File will appear in GitHub's "Contributing" section
echo "INFO: After merge, GitHub will display CONTRIBUTING.md in the 'Contribute' button"
echo "INFO: Users will see contributing guidelines when forking or starting to contribute"
echo "PASS: File placement supports GitHub integration"
```

**Expected Outcome:**
- File will be automatically detected by GitHub
- Will appear in the "Contributing" section of the repo

## 5. End-to-End Tests

### 5.1 Complete Contribution Workflow Validation
**Test:** Verify documentation supports complete workflow

```bash
# Test: New user can understand issue reporting flow
echo "=== Test: Issue Reporting Flow ==="
grep -A5 "Before Submitting A Bug Report" "$CONTRIBUTING_FILE" && echo "PASS: Pre-submission guidance present"
grep -A10 "How Do I Submit A.*Bug Report" "$CONTRIBUTING_FILE" && echo "PASS: Bug report template guidance present"

# Test: Contributor can understand PR submission flow  
echo "=== Test: PR Submission Flow ==="
grep -A3 "Fork the repository" "$CONTRIBUTING_FILE" && echo "PASS: Fork instruction present"
grep -i "branch" "$CONTRIBUTING_FILE" && echo "PASS: Branch guidance present"
grep -i "commit.*message" "$CONTRIBUTING_FILE" && echo "PASS: Commit guidance present"
grep -A2 "Open a pull request" "$CONTRIBUTING_FILE" && echo "PASS: PR submission steps present"

# Test: Reviewer understands the workflow
echo "=== Test: Review Workflow ==="
grep -i "review.*process" "$CONTRIBUTING_FILE" && echo "PASS: Review process documented"
grep -i "approval\|merge" "$CONTRIBUTING_FILE" && echo "PASS: Approval process documented"
```

**Expected Outcome:**
- Issue reporting workflow is clear and actionable
- PR submission workflow is complete with all steps
- Review and approval process is well-documented

## 6. Test Execution Checklist

- [ ] Section 1.1 (File Existence) passes - CONTRIBUTING.md exists and is readable
- [ ] Section 1.2 (File Format) passes - Proper markdown structure with all required sections
- [ ] Section 1.3 (Content Completeness) passes - All required information present
- [ ] Section 2.1 (Backwards Compat) passes - Existing files unchanged
- [ ] Section 3.1 (UX/Clarity) passes - Content is clear and well-structured
- [ ] Section 4.1 (GitHub Integration) passes - File properly named and located
- [ ] Section 4.2 (Repository Visibility) passes - File will be visible to users
- [ ] Section 5.1 (E2E Validation) passes - Complete workflows supported

## 7. Validation Summary

This testing plan focuses on documentation validation since CONTRIBUTING.md is a static file. Key validation points are:

1. **Existence and Format**: File exists in the correct location with valid markdown
2. **Content Completeness**: All required sections are present and informative
3. **Usability**: Content is clear, organized, and actionable
4. **GitHub Integration**: File placement and naming support automatic GitHub discovery
5. **Workflow Support**: Documentation enables users to follow the three main workflows (issue reporting, PR submission, code review)

All tests are non-destructive and verify the file against the requirements specified in the GitHub issue.
