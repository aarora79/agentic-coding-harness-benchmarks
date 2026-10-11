# Expert Review: Add a CONTRIBUTING.md guide

*Reviewed: 2026-10-10*
*Documents reviewed: `./github-issue.md`, `./lld.md` (v1)*

## Frontend Engineer (Pixel)

Pixel reviewed the reading experience: layout, headings, and how the file looks on GitHub.

### Strengths
- Root placement puts the file next to `README`, where a contributor browsing the tree sees it first.
- Numbered steps for the pull request flow match the order a contributor follows.
- The 80-line target keeps the page to one screen of scrolling.

### Concerns
- The v1 LLD describes each section in a bullet but does not give the text. Two implementers would write two different guides, and nobody can review the wording before the patch.
- Bold-led bullets in "What we expect" read well, but the LLD does not say how to format them.

### New libraries / infra dependencies
None.

### Better alternatives considered
A table of contents. Rejected: five sections fit on one screen, and GitHub already renders a heading outline menu.

### Recommendations
- Put the full proposed text of `CONTRIBUTING.md` in the LLD so the review covers the actual wording.

### Questions for author
- Should the guide use "we" for the maintainer? The repository has one owner (`octocat`).

### Verdict
APPROVED WITH CHANGES

## Backend Engineer (Byte)

Byte reviewed the git instructions for correctness against the repository.

### Strengths
- The LLD checked the default branch (`master`) instead of assuming `main`. A guide that says `main` would send contributors to a branch that does not exist.
- The fork flow matches the history: head commit `7fd1a60` merges pull request #6 from `Spaceghost/patch-1`.

### Concerns
- Step 2 of the pull request flow says "branch from `master`" but gives no hint that a fork's `master` can fall behind upstream. A contributor with an old fork opens a pull request with conflicts.
- `Fixes #N` closes the issue only when the pull request merges into the default branch. That holds here because pull requests target `master`, so no change needed.

### New libraries / infra dependencies
None.

### Better alternatives considered
Tell contributors to add an `upstream` remote and rebase. Rejected for a short guide: GitHub's **Sync fork** button does the same job with one click.

### Recommendations
- Add one line telling contributors to sync their fork before branching.

### Questions for author
- None.

### Verdict
APPROVED WITH CHANGES

## SRE/DevOps Engineer (Circuit)

Circuit reviewed deployment and operational effects.

### Strengths
- No build, CI, or runtime change. Merging the file is the whole rollout, and reverting the merge is the rollback.
- The LLD names a concrete post-merge check: the community profile page at `/community`.

### Concerns
- The guide links to `https://github.com/octocat/Hello-World/issues` and `/issues/new`. If the owner has turned issues off, both links 404 and the guide's main instruction fails. The clone cannot show that setting.

### New libraries / infra dependencies
None.

### Better alternatives considered
None needed.

### Recommendations
- Add the issues-enabled check to `testing.md` as a deploy check, and list it as an open question in the LLD.

### Questions for author
- None.

### Verdict
APPROVED

## Security Engineer (Cipher)

Cipher reviewed what the guide tells people to do with sensitive information.

### Strengths
- The issue section warns against posting passwords, tokens, or personal data in public issues.
- The guide gives security reports their own heading, so a reporter does not file them as ordinary bugs.

### Concerns
- **Should fix (blocking):** the v1 security section sends reporters to private vulnerability reporting on the **Security** tab and offers nothing else. The owner must turn that feature on per repository, and the LLD's own constraints admit the clone cannot show whether it is on. If it is off, the reporter finds no button, and the most likely next step is a public issue with full details. The instruction must work whether the feature is on or off.
- The no-secrets rule appears only under issues. Commits and pull request text are public too.

### New libraries / infra dependencies
None. A `SECURITY.md` would be the fuller answer but is out of scope.

### Better alternatives considered
Add `SECURITY.md` with a contact address. Rejected: the issue excludes it, and the reviewer cannot invent a maintainer address.

### Recommendations
- Give a fallback: if the **Report a vulnerability** button is missing, open an issue that asks for a private contact and contains no details.
- Extend the no-secrets rule to files, commits, and pull request text.

### Questions for author
- None.

### Verdict
NEEDS REVISION

## SMTS (Sage)

Sage reviewed the design as a whole: scope, accuracy, and upkeep.

### Strengths
- Tight scope: one new file, no edits to `README`, alternatives weighed with a matrix.
- The constraint list (no license, no tooling, settings not visible) is the right inventory for a documentation change.

### Concerns
- **Should fix (blocking):** the v1 expectations section says "Contributions are licensed under the project license." The repository has no license file, and the LLD lists that fact as a constraint. The sentence makes a legal claim that is false today and tells contributors their work falls under terms that do not exist.
- The guide says "we" in places while the project has one owner. Minor.

### New libraries / infra dependencies
None.

### Better alternatives considered
Pick a license in this change. Rejected: only the owner can choose one, and the issue excludes `LICENSE`.

### Recommendations
- Replace the license sentence with a plain statement that no license file exists and an instruction to ask the maintainer before a large contribution.
- Use "the maintainer" in place of "we" throughout.

### Questions for author
- None beyond the license question, which stays open for the owner.

### Verdict
NEEDS REVISION

## Review Summary

| Reviewer | Verdict | Blockers | Key Recommendations |
|----------|---------|----------|---------------------|
| Frontend (Pixel) | APPROVED WITH CHANGES | 0 | Put the full proposed text in the LLD |
| Backend (Byte) | APPROVED WITH CHANGES | 0 | Tell contributors to sync their fork first |
| SRE (Circuit) | APPROVED | 0 | Check that issues are enabled after merge |
| Security (Cipher) | NEEDS REVISION | 1 | Fallback for security reports; no secrets anywhere public |
| SMTS (Sage) | NEEDS REVISION | 1 | Remove the false license claim; say "the maintainer" |

## Resolution of Findings (Step 7.5)

The two blocking findings and the three should-fix recommendations changed the LLD. Revised LLD status: v2.

1. **Cipher: security reports depend on a setting that may be off.**
   Resolution: LLD v2 section "Reporting a security problem" now says: use **Report a vulnerability** on the **Security** tab if it appears; if it does not, open an issue that asks the maintainer for a private contact and leaves out the details. The instruction works either way.
2. **Cipher: no-secrets rule covers issues only.**
   Resolution: LLD v2 expectations list now reads "No secrets or personal data in files, commits, issues, or pull request text."
3. **Sage: false license claim.**
   Resolution: LLD v2 removes "Contributions are licensed under the project license." It now says the repository has no license file yet and asks contributors to open an issue about licensing before a large contribution. The license gap stays open and unmitigated; the LLD records it under Open Questions.
4. **Sage: "we" versus one maintainer.**
   Resolution: LLD v2 text uses "the maintainer" throughout.
5. **Pixel: no proposed text.**
   Resolution: LLD v2 adds the full text of `CONTRIBUTING.md` under Implementation Details, Step 1. The patch must match it.
6. **Byte: stale forks.**
   Resolution: LLD v2 pull request step 2 tells contributors to click **Sync fork** on GitHub before branching.
7. **Circuit: issues may be disabled.**
   Resolution: LLD v2 lists it under Open Questions; `testing.md` section 4.4 checks it after merge.

## Next Steps
- Implement `CONTRIBUTING.md` from the LLD v2 text.
- Run the manual checks in `testing.md` after the pull request opens and again after merge.
