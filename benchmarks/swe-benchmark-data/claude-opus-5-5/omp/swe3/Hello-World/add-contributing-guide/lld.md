# Low-Level Design: Add a CONTRIBUTING.md guide

*Created: 2026-10-10*
*Author: Claude*
*Status: Revised (v2, after expert review; see `./review.md`, "Resolution of Findings")*

## Revision History

| Version | Change |
|---------|--------|
| v1 | First draft: section outline only. |
| v2 | After review: security section gains a fallback when private vulnerability reporting is off (Cipher); false license claim removed (Sage); no-secrets rule covers files, commits, issues, and pull requests (Cipher); "the maintainer" replaces "we" (Sage); full proposed text added (Pixel); sync-fork step added (Byte); issues-enabled check added as an open question (Circuit). |

## Table of Contents
1. [Overview](#overview)
2. [Codebase Analysis](#codebase-analysis)
3. [Architecture](#architecture)
4. [Data Models](#data-models)
5. [API / CLI Design](#api--cli-design)
6. [Configuration Parameters](#configuration-parameters)
7. [New Dependencies](#new-dependencies)
8. [Implementation Details](#implementation-details)
9. [Observability](#observability)
10. [Scaling Considerations](#scaling-considerations)
11. [File Changes](#file-changes)
12. [Testing Strategy](#testing-strategy)
13. [Alternatives Considered](#alternatives-considered)
14. [Rollout Plan](#rollout-plan)

## Overview

### Problem Statement
`octocat/Hello-World` at `master` (commit `7fd1a60b01f91b314f59955a4e4d4e80d8edf11d`) tracks one file, `README`, which contains the 13 bytes `Hello World!\n`. Contributors get no instructions on how to report a problem or send a change. GitHub surfaces a `CONTRIBUTING.md` on the new-issue page, the new-pull-request page, and the repository sidebar, but only when the file exists.

### Goals
- Add `CONTRIBUTING.md` at the repository root.
- Explain how to file an issue, how to open a pull request, and what a contribution must meet.
- Keep the guide short enough to read in two minutes (target: under 80 lines).
- Reference only things that exist in the repository or on GitHub.

### Non-Goals
- Issue or pull request templates.
- `CODE_OF_CONDUCT.md`, `LICENSE`, `SECURITY.md`.
- Edits to `README`.
- Build, lint, test, or CI setup. The repository has none.

## Codebase Analysis

### Key Files Reviewed

| File/Directory | Purpose | Relevance to This Change |
|----------------|---------|--------------------------|
| `README` | Plain text, no extension, content `Hello World!` with a trailing newline | The only tracked file. It sets no Markdown style to follow and stays unchanged. |
| `.git` (refs, remote) | Remote `origin` is `https://github.com/octocat/Hello-World`; branch `master`; head `7fd1a60` ("Merge pull request #6 from Spaceghost/patch-1") | Confirms the default branch name (`master`) and that the project already takes changes as pull requests from forks. |

`git ls-files` lists `README` and nothing else. No `.github/`, `docs/`, `LICENSE`, `CODE_OF_CONDUCT.md`, or `SECURITY.md` exists.

### Existing Patterns Identified
1. **Fork-and-pull-request workflow**: the head commit merges pull request #6 from a fork (`Spaceghost/patch-1`). The guide describes this same flow.
   - Files: git history only.
   - How a future implementer should follow this: tell contributors to fork, branch, and open a pull request against `master`.
2. **Default branch `master`**: `git rev-parse --abbrev-ref HEAD` returns `master`. The guide must name `master`, not `main`.

### Integration Points

| Component | Integration Type | Details |
|-----------|------------------|---------|
| GitHub community profile | Uses | GitHub detects `CONTRIBUTING.md` in the root, `docs/`, or `.github/` and links it from the issue and pull request forms. |
| GitHub issues | Links to | The guide links `https://github.com/octocat/Hello-World/issues`. |

### Constraints and Limitations Discovered
- No license file: the guide cannot promise a license for contributions.
- Repository settings (issues enabled, private vulnerability reporting enabled) are not visible from a clone. The guide must not depend on a setting being on.
- No tooling: the guide cannot tell contributors to run tests or linters.

## Architecture

### System Context Diagram
```
 contributor
     |
     | opens repo / clicks "New issue" or "New pull request"
     v
 GitHub UI ---- detects ----> CONTRIBUTING.md (repo root)
     |                              |
     | shows link to guide          | explains
     v                              v
 issue / pull request  <------  how to file, how to PR, expectations
```

### Sequence Diagram
```
Contributor        GitHub             CONTRIBUTING.md        Maintainer
    |  New issue     |                       |                   |
    |--------------->| banner: read guide    |                   |
    |<---------------|---------------------->|                   |
    |  reads steps   |                       |                   |
    |  files issue / opens PR against master |                   |
    |--------------->|---------------------------------------- ->|
    |                |                       |   reviews         |
    |<-------------------------------------------------------------|
```

### Component Diagram
```
CONTRIBUTING.md
 |-- Filing an issue
 |     |-- search first
 |     |-- bug report contents
 |     |-- change requests
 |-- Reporting a security problem
 |-- Opening a pull request (numbered steps)
 |-- What the maintainer expects
 |-- Questions
```

## Data Models
**Not Applicable** - documentation-only change; no data structures.

## API / CLI Design
**Not Applicable** - no endpoints or commands. The guide shows contributors standard `git` commands only.

## Configuration Parameters
**Not Applicable** - no environment variables, settings, or deployment surfaces.

### Deployment Surface Checklist
None. The file ships by merging to `master`.

## New Dependencies
This change uses only existing dependencies. It adds none.

## Implementation Details

### Step-by-Step Plan (for a future implementer)

#### Step 1: Create the guide
**File:** `CONTRIBUTING.md`
**Lines:** new file

The file must contain exactly this text (the outer four-backtick fence is not part of the file):

````markdown
# Contributing to Hello-World

This guide explains how to report a problem, how to propose a change, and what the maintainer looks for in a contribution.

## Filing an issue

Search the [open and closed issues](https://github.com/octocat/Hello-World/issues?q=is%3Aissue) before you open a new one. If an issue already covers your problem, add a comment with any new details instead of opening a duplicate.

To report a problem, open a [new issue](https://github.com/octocat/Hello-World/issues/new) and include:

- A short title that names the problem.
- What you expected to see and what you saw instead.
- Steps someone else can follow to see the same thing.
- The branch or commit you looked at, for example `master`.

To suggest a change, describe what you want to change and why. For a large change, agree on the idea in the issue before you write the pull request.

Issues are public. Do not put passwords, tokens, or personal data in them.

### Reporting a security problem

Do not describe a security problem in a public issue. If the repository's **Security** tab shows a **Report a vulnerability** button, use it to send a private report. If the button is missing, open an issue that asks the maintainer for a private contact, and leave out the details.

## Opening a pull request

1. Fork the repository and clone your fork.
2. If your fork already existed, click **Sync fork** on GitHub so its `master` matches this repository. Then create a branch from `master` with a short name that says what it does:

   ```sh
   git checkout master
   git pull
   git checkout -b fix-readme-typo
   ```

3. Make your change. Keep it to one topic.
4. Commit with a message that says what the change does, for example `Fix typo in README`.
5. Push the branch to your fork and open a pull request against `master`.
6. In the pull request description, say what you changed and why. If the pull request resolves an issue, write `Fixes #<issue-number>` so GitHub links the issue and closes it on merge.
7. Answer review comments by pushing new commits to the same branch. The pull request picks them up.

The maintainer may ask for changes, or may close a pull request that does not fit the project.

## What the maintainer expects

- **One change per pull request.** Put unrelated fixes in separate pull requests.
- **A small diff.** Do not reformat, rename, or move files your change does not need.
- **Clear commit messages.** Write the summary line in the imperative ("Add", "Fix", "Remove") and keep it under about 72 characters.
- **A checked change.** Read your own diff before you open the pull request. For Markdown, use the **Preview** tab on GitHub to see how it renders.
- **No secrets or personal data** in files, commits, issues, or pull request text.
- **Respect** for other people in issues, reviews, and comments.

The repository has no license file yet. Before you send a large contribution, open an issue and ask the maintainer how it will be licensed.

## Questions

Open an issue and ask.
````

Section map: purpose line; **Filing an issue** (search first, bug report contents, change requests, public-data warning); **Reporting a security problem** (private report with a fallback); **Opening a pull request** (seven numbered steps against `master`); **What the maintainer expects** (six bullets plus the license note); **Questions**.

#### Step 2: Style rules for the file
- GitHub-flavored Markdown. ATX headings (`#`, `##`, `###`).
- One paragraph per line; no hard wrapping.
- Absolute links to `https://github.com/octocat/Hello-World/...` so the links work on GitHub and in a local editor.
- Fenced code block with `sh` for the git commands.
- Trailing newline at end of file.

### Error Handling
**Not Applicable** - no runtime behavior.

### Logging
**Not Applicable** - no runtime behavior.

## Observability
GitHub's community profile page (`/community`) shows a check next to "Contributing" once the file lands on the default branch. That page is the only signal to watch.

## Scaling Considerations
**Not Applicable** - a static file. GitHub serves it.

## File Changes

### New Files

| File Path | Description |
|-----------|-------------|
| `CONTRIBUTING.md` | Contributor guide: issues, pull requests, expectations |

### Modified Files
None.

### Estimated Lines of Code

| Category | Lines |
|----------|-------|
| New documentation | ~55 |
| New tests | 0 |
| Modified code | 0 |
| **Total** | **~55** |

## Testing Strategy
See `./testing.md`. Verification is manual: render on GitHub, click every link, confirm GitHub links the guide from the new-issue page.

## Alternatives Considered

### Alternative 1: Put the guide in `.github/CONTRIBUTING.md`
**Description:** GitHub also detects the file under `.github/`.
**Pros / Cons:** Keeps the root tidy; but the root holds one file, and contributors browsing the tree miss a file inside a dotted folder.
**Why Rejected:** The root is the most visible spot and matches the issue.

### Alternative 2: Append a "Contributing" section to `README`
**Description:** Add the guidance to the existing file.
**Pros / Cons:** One file; but `README` is plain text without an extension, so Markdown would not render, and GitHub would not link it from the issue and pull request forms.
**Why Rejected:** Loses the GitHub integration, and the issue scopes the change to a new file.

### Alternative 3: Full template set (issue forms, PR template, code of conduct)
**Pros / Cons:** More structure; but five-plus files for a one-file repository, and each needs maintainer decisions.
**Why Rejected:** Out of scope for a low-scope change.

### Comparison Matrix

| Criteria | Root `CONTRIBUTING.md` | `.github/` | README section | Template set |
|----------|------------------------|------------|----------------|--------------|
| Complexity | Low | Low | Low | High |
| Visible in tree | Yes | Less | Yes | Mixed |
| GitHub links it from forms | Yes | Yes | No | Yes |
| Files touched | 1 | 1 | 1 | 5+ |

## Rollout Plan
- Phase 1: Add `CONTRIBUTING.md` in a pull request against `master`.
- Phase 2: Maintainer previews the rendered file and checks the links.
- Phase 3: Merge. GitHub picks the file up from the default branch.

## Open Questions
- Which license should the project adopt? Outside this change. Until the owner adds a `LICENSE`, the licensing of outside contributions stays undefined; the guide states the gap and does not paper over it.
- Are GitHub issues enabled on `octocat/Hello-World`? The clone cannot show it. The guide's issue links 404 if issues are off; `testing.md` section 4.4 checks it after merge.
- Is private vulnerability reporting enabled? Unknown from the clone. The guide gives a fallback, so its instruction holds either way.

## References
- GitHub Docs, "Setting guidelines for repository contributors": https://docs.github.com/en/communities/setting-up-your-project-for-healthy-contributions/setting-guidelines-for-repository-contributors
- GitHub Docs, "Privately reporting a security vulnerability": https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability
