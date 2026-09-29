# Testing Plan: CONTRIBUTING.md Guide

*Created: 2025-06-10*
*Related LLD: `./lld.md`*
*Related Issue: `./github-issue.md`*

## Overview

### Scope of Testing
Verify that a single new documentation file, `CONTRIBUTING.md`, is added at the
repository root; that it contains the three required sections (filing an issue,
opening a pull request, contribution expectations); that it is valid,
GitHub-renderable Markdown with working relative links; and that the existing
`README` is unchanged. There is no build, runtime, or service to exercise, so
all tests are static/manual checks. (These checks are described for a human or
grader to run; per the skill's constraints they are not executed here.)

### Prerequisites
- [ ] A checkout of the repository at branch `master` with the patch applied.
- [ ] `git` available for diff-based checks.
- [ ] (For render checks) the ability to view the file on GitHub or in any
      Markdown previewer.

### Shared Variables
```bash
export REPO_ROOT="/tmp/swe-clone-add-contributing-guide/Hello-World"
cd "$REPO_ROOT"
```

## 1. Functional Tests

### 1.1 curl / HTTP Tests
**Not Applicable** - this change adds no HTTP endpoint.

### 1.2 CLI Tests
**Not Applicable** - this change adds no CLI command. The git commands shown
inside the guide are illustrative content, not new tooling. (Their correctness
is checked as documentation content in Section 3.2.)

### 1.3 File-presence and content checks (documentation functional tests)

**Test 1.3.1 - File exists at the repository root**
```bash
test -f "$REPO_ROOT/CONTRIBUTING.md" && echo "PASS: CONTRIBUTING.md exists" \
  || echo "FAIL: CONTRIBUTING.md missing"
```
Expected: `PASS: CONTRIBUTING.md exists`.

**Test 1.3.2 - The three required sections are present**
```bash
grep -qi "Filing an issue"        "$REPO_ROOT/CONTRIBUTING.md" && echo "PASS: issue section"
grep -qi "Opening a pull request" "$REPO_ROOT/CONTRIBUTING.md" && echo "PASS: PR section"
grep -qiE "expect|expectations"   "$REPO_ROOT/CONTRIBUTING.md" && echo "PASS: expectations section"
```
Expected: all three `PASS` lines print.

**Test 1.3.3 - The file is tracked by git as a new file**
```bash
git -C "$REPO_ROOT" status --porcelain CONTRIBUTING.md
```
Expected: a line beginning with `A ` (staged add) or `?? ` (untracked new file),
showing `CONTRIBUTING.md`.

**Test 1.3.4 - Key contribution steps are documented**
```bash
grep -qiE "fork"   "$REPO_ROOT/CONTRIBUTING.md" && echo "PASS: fork"
grep -qiE "branch" "$REPO_ROOT/CONTRIBUTING.md" && echo "PASS: branch"
grep -qiE "commit" "$REPO_ROOT/CONTRIBUTING.md" && echo "PASS: commit"
grep -qiE "push"   "$REPO_ROOT/CONTRIBUTING.md" && echo "PASS: push"
```
Expected: all four `PASS` lines print.

## 2. Backwards Compatibility Tests

**Test 2.1 - README is unchanged**
```bash
git -C "$REPO_ROOT" diff --stat -- README
```
Expected: no output (README is not in the diff).

```bash
cat "$REPO_ROOT/README"
```
Expected: `Hello World!` (unchanged content).

**Test 2.2 - Only one file is added, nothing else changes**
```bash
git -C "$REPO_ROOT" diff --name-status HEAD
```
Expected: exactly one entry, `A\tCONTRIBUTING.md` (adding the guide only). No
other files appear.

## 3. UX Tests

### 3.1 Markdown renders cleanly on GitHub
Open `CONTRIBUTING.md` on GitHub (or in a Markdown previewer) and confirm:
- [ ] A single H1 title renders at the top.
- [ ] Each major section renders as an H2 with an anchor.
- [ ] Numbered and bulleted lists render correctly (no raw `1.`/`-` artifacts).
- [ ] Inline code (git commands) renders in monospace.

### 3.2 Content is correct and clear
- [ ] The "Filing an issue" section tells the reader to search first and lists
      what a good report contains.
- [ ] The "Opening a pull request" section lists fork, clone, branch, commit,
      push, open PR - in order.
- [ ] The git commands are syntactically valid and use a placeholder username
      (`<your-username>`) rather than a real one.
- [ ] No reference to a `main` branch (the repo default is `master`); the guide
      says "the default branch".
- [ ] The expectations section covers focused changes, clear commit messages,
      and respectful conduct.

### 3.3 Links resolve
```bash
grep -nE "\]\(([^)]+)\)" "$REPO_ROOT/CONTRIBUTING.md"
```
Expected: any links are relative (for example `../../issues...`) or point to a
trusted domain (`github.com`). Manually confirm the issues link opens the repo's
issues tab from the rendered page. There should be no shortened or third-party
redirect links.

## 4. Deployment Surface Tests

**Not Applicable** - there are no Docker, ECS/Terraform, or Helm surfaces in
this repository, and this change adds none. "Deployment" is simply merging the
Markdown file; there is no configuration parameter to wire anywhere.

### 4.5 Rollback verification
```bash
# Rollback is a trivial file removal / revert:
git -C "$REPO_ROOT" checkout -- . 2>/dev/null; git -C "$REPO_ROOT" clean -n
```
Expected: removing `CONTRIBUTING.md` restores the repository to its prior
single-file state with no side effects.

## 5. End-to-End API Tests

**Not Applicable** - there is no multi-endpoint or multi-service workflow. The
end-to-end "workflow" is a human reading the guide; that is covered by the UX
tests in Section 3.

## 6. Test Execution Checklist
- [ ] Section 1 (Functional / file presence and content) passes
- [ ] Section 2 (Backwards Compat - README unchanged, single added file) passes
- [ ] Section 3 (UX - renders on GitHub, content correct, links resolve) passes
- [ ] Section 4 (Deployment) marked Not Applicable, rollback confirmed trivial
- [ ] Section 5 (E2E) marked Not Applicable
- [ ] No unit/integration tests are applicable (documentation-only change)
- [ ] `git diff --name-status HEAD` shows exactly one added file
