# GitHub Issue: Add a CONTRIBUTING.md guide

## Title
Add CONTRIBUTING.md with issue, pull request, and contribution guidelines

## Labels
- documentation
- good first issue

## Description

### Problem Statement
The repository at `master` (commit `7fd1a60`) holds one tracked file, `README`, whose only content is `Hello World!`. A contributor who wants to report a problem or propose a change finds no instructions: no `CONTRIBUTING.md`, no issue or pull request templates, and no `.github/` directory. Each contributor has to guess how to report a bug, which branch to target, and what a maintainer expects in a pull request.

GitHub looks for `CONTRIBUTING.md` in the repository root, `docs/`, or `.github/`. When it finds one, it links the file from the new-issue and new-pull-request pages and from the repository sidebar. The repository gets none of that today.

### Proposed Solution
Add a short `CONTRIBUTING.md` at the repository root. It covers three topics:

1. How to file an issue: search first, then what to include in a bug report or a change request.
2. How to open a pull request: fork, branch from `master`, make a focused change, open the pull request against `master`, and respond to review.
3. Basic expectations for a contribution: small and on-topic changes, clear commit messages, no secrets or personal data, and no edits to unrelated files.

The guide also tells reporters not to post security problems in public issues.

### User Stories
- As a first-time contributor, I want one page that tells me how to report a problem so that the maintainer gets the details needed to act on it.
- As a returning contributor, I want to know which branch to target and what a reviewer expects so that my pull request merges without rework.
- As the maintainer, I want contributors to send small, described changes so that review takes minutes.

### Acceptance Criteria
- [ ] `CONTRIBUTING.md` exists at the repository root.
- [ ] It has a section on filing an issue that says to search existing issues first and lists what a bug report should contain.
- [ ] It has a section on opening a pull request with numbered steps from fork to review, targeting `master`.
- [ ] It has a section on contribution expectations (scope, commit messages, no secrets, licensing of the contribution).
- [ ] It tells reporters to keep security problems out of public issues.
- [ ] It links only to files and pages that exist; it does not reference a code of conduct, license, test suite, or build system the repository lacks.
- [ ] It renders as valid GitHub-flavored Markdown with no broken links.
- [ ] The change touches no other file.

### Out of Scope
- Issue templates and pull request templates under `.github/`.
- A `CODE_OF_CONDUCT.md`, `LICENSE`, or `SECURITY.md`.
- Any change to `README`.
- Build, lint, test, or CI configuration.

### Dependencies
- None.

### Related Issues
- None known.
