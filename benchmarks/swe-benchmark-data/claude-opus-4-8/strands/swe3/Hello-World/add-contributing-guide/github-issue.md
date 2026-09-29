# GitHub Issue: Add a CONTRIBUTING.md guide

## Title
Add a CONTRIBUTING.md to explain how to file issues and open pull requests

## Labels
- documentation
- good first issue
- enhancement

## Description

### Problem Statement
The repository currently contains only a `README` and offers no guidance for
people who want to contribute. Contributors have nowhere to look for how to
report a problem, propose a change, or open a pull request. A `CONTRIBUTING.md`
file is the standard, well-known place for this guidance, and GitHub surfaces it
automatically in the "new issue" and "new pull request" flows. Its absence
raises the barrier to entry for new and returning contributors alike.

### Proposed Solution
Add a short, well-structured `CONTRIBUTING.md` at the repository root that
covers:

1. **How to file an issue** - what to search for first, and what information a
   good report should include.
2. **How to open a pull request** - the fork / branch / commit / push / PR
   flow.
3. **Basic expectations for a contribution** - scope, clear commit messages,
   respectful conduct, and keeping changes focused.

The file is Markdown only. It introduces no build system, tests, or code, and
does not modify the existing `README`.

### User Stories
- As a first-time contributor, I want a single document that tells me how to
  file an issue so that I can report a problem correctly the first time.
- As a returning contributor, I want a documented pull-request flow so that my
  change is reviewed and merged without back-and-forth about process.
- As a maintainer, I want contributors to follow a shared checklist so that
  incoming issues and PRs are consistent and easy to triage.

### Acceptance Criteria
- [ ] A new file `CONTRIBUTING.md` exists at the repository root.
- [ ] It has a section explaining how to file an issue (search first, what to
      include).
- [ ] It has a section explaining how to open a pull request (fork, branch,
      commit, push, open PR).
- [ ] It has a section describing the basic expectations for a contribution.
- [ ] The document is valid Markdown and renders cleanly on GitHub.
- [ ] The existing `README` is unchanged.
- [ ] No code, build system, tests, or dependencies are added.

### Out of Scope
- A formal Code of Conduct file (`CODE_OF_CONDUCT.md`).
- Issue or pull-request templates under `.github/`.
- Continuous integration, linting, or automated Markdown checks.
- Any change to the existing `README` file.
- Licensing, security-policy, or governance documents.

### Dependencies
- None. This is a standalone documentation file.

### Related Issues
- None.
