# Testing Plan: Add a CONTRIBUTING.md guide

*Created: 2026-10-10*
*Related LLD: `./lld.md` (v2)*
*Related Issue: `./github-issue.md`*

## Overview

### Scope of Testing
The change adds one Markdown file, `CONTRIBUTING.md`, at the repository root. The tests check that the file exists with the agreed sections, that it touches nothing else, that every link resolves, that it renders on GitHub, and that GitHub links it from the issue and pull request forms.

### Prerequisites
- [ ] A clone of `https://github.com/octocat/Hello-World` at `master` (baseline commit `7fd1a60b01f91b314f59955a4e4d4e80d8edf11d`).
- [ ] `patch.diff` from this folder.
- [ ] `git`, `grep`, and `curl` on the path.
- [ ] A browser signed in to GitHub, for the rendering and form checks in sections 3 and 4.

### Shared Variables
```bash
export REPO_URL="https://github.com/octocat/Hello-World"
export BASE_SHA="7fd1a60b01f91b314f59955a4e4d4e80d8edf11d"
export PATCH="$PWD/patch.diff"
git clone --branch master "$REPO_URL" hello-world-test && cd hello-world-test
```

## 1. Functional Tests

### 1.1 curl / HTTP Tests
Check that every absolute link in the guide answers. Run after applying the patch (section 1.2, test 1).

```bash
grep -o 'https://github.com/[^)]*' CONTRIBUTING.md | sort -u | while read -r url; do
  code=$(curl -s -o /dev/null -w '%{http_code}' -L "$url")
  echo "$code $url"
done
```

- Expected: `200` for each of `https://github.com/octocat/Hello-World/issues?q=is%3Aissue` and `https://github.com/octocat/Hello-World/issues/new`. `/issues/new` may answer with a redirect to the sign-in page for an anonymous client; with `-L` the final code is `200`.
- Negative case: a `404` on the `/issues` link means the owner has turned issues off. Record it as a failure of the guide's main instruction and raise it with the maintainer (LLD Open Questions).

### 1.2 CLI Tests

**Test 1: the patch applies and adds exactly one file.**
```bash
git apply --check "$PATCH" && git apply "$PATCH"
git status --porcelain
```
Expected output, one line:
```
?? CONTRIBUTING.md
```
Negative case: any other path in the output, or a modified `README`, fails the test.

**Test 2: the file has every required section.**
```bash
for h in '^# Contributing to Hello-World$' \
         '^## Filing an issue$' \
         '^### Reporting a security problem$' \
         '^## Opening a pull request$' \
         '^## What the maintainer expects$' \
         '^## Questions$'; do
  grep -qE "$h" CONTRIBUTING.md && echo "OK   $h" || echo "FAIL $h"
done
```
Expected: six `OK` lines.

**Test 3: the guide names the real default branch.**
```bash
grep -c '`master`' CONTRIBUTING.md
grep -n '\bmain\b' CONTRIBUTING.md
```
Expected: the first command prints a count of at least 3; the second prints nothing.

**Test 4: the pull request steps are numbered 1 to 7.**
```bash
grep -E '^[0-9]+\. ' CONTRIBUTING.md | cut -d. -f1 | tr '\n' ' '
```
Expected: `1 2 3 4 5 6 7 `

**Test 5: review fixes are present.**
```bash
grep -q 'If the button is missing' CONTRIBUTING.md && echo "OK security fallback"
grep -q 'no license file yet' CONTRIBUTING.md && echo "OK license note"
grep -q 'files, commits, issues, or pull request text' CONTRIBUTING.md && echo "OK no-secrets scope"
grep -q 'Sync fork' CONTRIBUTING.md && echo "OK sync fork"
grep -n 'project license' CONTRIBUTING.md || echo "OK no false license claim"
```
Expected: five `OK` lines.

**Test 6: no references to files the repository lacks.**
```bash
grep -nE 'CODE_OF_CONDUCT|LICENSE\.|SECURITY\.md|\.github/' CONTRIBUTING.md || echo "OK no dangling references"
```
Expected: `OK no dangling references`.

**Test 7: file hygiene.**
```bash
tail -c 1 CONTRIBUTING.md | od -An -c        # expect: \n
grep -nP '\t| +$' CONTRIBUTING.md || echo "OK no tabs or trailing spaces"
grep -nP '\x{2014}' CONTRIBUTING.md || echo "OK no em-dashes"
wc -l < CONTRIBUTING.md                       # expect: under 80
```

## 2. Backwards Compatibility Tests
The only existing file is `README`. Confirm the patch leaves it byte-for-byte unchanged:

```bash
git diff --quiet "$BASE_SHA" -- README && echo "OK README unchanged"
git hash-object README    # expect the same hash as before applying the patch
```

No API, schema, CLI, or default exists to break.

## 3. UX Tests

### 3.1 Rendering on GitHub
1. Push the patched branch to a fork and open the file at `https://github.com/<your-user>/Hello-World/blob/<branch>/CONTRIBUTING.md`.
2. Check:
   - [ ] Headings render as one `#` title, four `##` sections, one `###` subsection.
   - [ ] The bullet list under "Filing an issue" renders as four bullets.
   - [ ] The numbered list runs 1 to 7 without restarting at step 3. The indented `sh` code block sits inside step 2.
   - [ ] Bold text renders for **Security**, **Report a vulnerability**, **Sync fork**, **Preview**, and the six bullet leads.
   - [ ] Both issue links are clickable and open the issues pages of `octocat/Hello-World`.

### 3.2 Readability
- [ ] A reader new to the repository can answer three questions from the page alone: where to file a bug, which branch to target, and what to do with a security problem.
- [ ] The page fits on about one screen of scrolling (under 80 lines in the source).

## 4. Deployment Surface Tests

### 4.1 Docker wiring
**Not Applicable** - the repository has no Docker files.

### 4.2 Terraform / ECS wiring
**Not Applicable** - the repository has no infrastructure code.

### 4.3 Helm / EKS wiring
**Not Applicable** - the repository has no Helm charts.

### 4.4 Deploy and verify
"Deploy" means merging the pull request into `master`. After merge:

1. Open `https://github.com/octocat/Hello-World/community`. Expected: "Contributing" shows a check.
2. Open `https://github.com/octocat/Hello-World/issues/new`. Expected: GitHub shows a link to the contributing guidelines.
3. Start a new pull request from a fork. Expected: GitHub shows a link to the contributing guidelines.
4. Confirm issues are enabled: the **Issues** tab appears on the repository page. If it does not, the guide's issue links fail; raise it with the maintainer.
5. Check the **Security** tab for a **Report a vulnerability** button and note whether it appears. Either result passes, since the guide covers both.

### 4.5 Rollback verification
Revert the merge commit with `git revert -m 1 <merge-sha>` and push. Expected: `CONTRIBUTING.md` disappears from `master`, the community profile check clears, and `README` stays unchanged.

## 5. End-to-End API Tests

### 5.1 Contributor walk-through
1. Follow "Opening a pull request" step by step from a fresh fork: fork, sync, branch `fix-readme-typo` from `master`, make a one-line change, commit, push, open a pull request against `master` with `Fixes #<n>` pointing at a test issue.
2. Expected: GitHub links the issue in the pull request sidebar. On merge, GitHub closes the issue.
3. Close the test pull request without merging if you only want to check the steps; delete the test branch and issue afterward.

## 6. Test Execution Checklist
- [ ] Section 1 (Functional) passes
- [ ] Section 2 (Backwards Compat) verified
- [ ] Section 3 (UX) verified
- [ ] Section 4 (Deployment) verified; 4.1 to 4.3 marked Not Applicable
- [ ] Section 5 (E2E) verified
- [ ] Unit tests under `tests/unit/`: **Not Applicable** - the repository has no code or test suite
- [ ] Integration tests under `tests/integration/`: **Not Applicable** - same reason
- [ ] Test suite run: **Not Applicable** - no suite exists; sections 1 to 5 replace it
