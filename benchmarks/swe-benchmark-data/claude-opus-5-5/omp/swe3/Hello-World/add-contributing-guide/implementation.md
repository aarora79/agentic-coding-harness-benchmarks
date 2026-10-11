# Implementation Summary: Add a CONTRIBUTING.md guide

*Created: 2026-10-10*
*Baseline ref: `master` (commit `7fd1a60b01f91b314f59955a4e4d4e80d8edf11d`)*
*Patch: `./patch.diff`*
*Related LLD: `./lld.md` (v2)*

## What Changed
The patch adds `CONTRIBUTING.md` at the repository root. The guide covers filing an issue (with a private route for security problems), opening a pull request against `master` in seven steps, and what the maintainer expects from a contribution. It includes every fix from the expert review: a fallback when private vulnerability reporting is off, no false license claim, a no-secrets rule that covers files, commits, issues, and pull requests, and a step to sync a stale fork.

## Files Touched

| File | Change | Lines +/- | Notes |
|------|--------|-----------|-------|
| `CONTRIBUTING.md` | added | +56 / -0 | Contributor guide, text identical to LLD v2, Implementation Details, Step 1 |

`README` and every other path stay unchanged (`git status --porcelain` showed only `A  CONTRIBUTING.md`).

## How to Apply

```bash
git clone --branch master https://github.com/octocat/Hello-World repo && cd repo
git apply /path/to/patch.diff
```

`git apply --check` passed against a fresh checkout of commit `7fd1a60`.

## Deviations from the LLD
None. A script compared the file in the clone with the fenced text in `lld.md` and found them identical. The file has 56 lines, under the 80-line goal; the LLD estimate of ~55 was one line short.

## Not Implemented / Follow-ups
None in scope. Items the LLD leaves open for the owner, outside this patch:
- No `LICENSE` exists, so the licensing of outside contributions stays undefined. The guide states the gap and asks contributors to raise it before a large change.
- Whether GitHub issues and private vulnerability reporting are enabled on `octocat/Hello-World` cannot be seen from a clone. `testing.md` section 4.4 checks both after merge.

## Verification (not executed)
`testing.md` lists the checks: patch application and file scope, section headings, branch name, review fixes, link status codes, GitHub rendering, community profile detection, and rollback. Per the skill's constraints, those tests were designed but not run. The only checks run were `git apply --check` on a fresh baseline checkout and the byte comparison against the LLD text.
