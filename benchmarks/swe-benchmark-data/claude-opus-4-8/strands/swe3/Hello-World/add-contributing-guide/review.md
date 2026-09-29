# Expert Review: CONTRIBUTING.md Guide

*Created: 2025-06-10*
*Reviews the design in `./lld.md` and the spec in `./github-issue.md`.*

This document captures feedback from five reviewer personas. Each reviews the
proposed change strictly from its own angle. Because this is a
documentation-only change to a repository with a single `README`, several
personas find little in scope; they say so plainly rather than inventing
concerns.

---

## Frontend Engineer - Pixel
**Focus:** UI/UX, components, state, API integration.

### Strengths
- The document is the "UI" here, and it is well structured: three clearly
  labeled sections that map exactly to the three questions a contributor asks
  (how do I report, how do I propose, what is expected).
- Numbered steps for issues and PRs read as a clear, scannable flow.
- Short by design, which respects the reader's time.

### Concerns
- **Link rendering:** absolute URLs would break on forks. The LLD already
  mandates relative links (`../../issues`), which is the right call. Confirm the
  relative link actually resolves on GitHub's rendered view (it does:
  `../../issues` from a root file resolves to the repo's issues tab).
- Heading levels should be consistent (`#` title, `##` sections) so GitHub's
  auto-generated table of contents and anchor links work.

### New libraries / infra dependencies
- None required or appropriate.

### Better alternatives considered
- None; a single Markdown page is the correct "UI" for this content.

### Recommendations
- Keep the relative-link guidance (already in the LLD).
- Ensure exactly one `#` H1 and `##` for each major section.

### Questions for author
- Should the "search first" link point to all issues or only open ones? (Minor;
  linking to all issues via a search query is slightly more helpful.)

### Verdict: APPROVED

---

## Backend Engineer - Byte
**Focus:** API design, data models, business logic, performance.

### Strengths
- Correctly identifies there is no API, data model, or business logic; the LLD's
  "Not applicable" entries are honest and appropriate.
- The illustrative git commands are accurate and complete (fork, clone, branch,
  commit, push, PR).

### Concerns
- **Default-branch correctness:** the repo's default branch is `master`, not
  `main`. Hardcoding `git checkout -b ... ` off `main` or telling contributors
  to PR against `main` would be wrong here. The LLD addresses this by using "the
  default branch" phrasing. This must be preserved in implementation.

### New libraries / infra dependencies
- None.

### Better alternatives considered
- None applicable.

### Recommendations
- Keep the branch-neutral phrasing. Do not name `main` anywhere.

### Questions for author
- None.

### Verdict: APPROVED

---

## SRE/DevOps Engineer - Circuit
**Focus:** Deployment, monitoring, scaling, infrastructure.

### Strengths
- Zero operational risk: a static Markdown file with no runtime, no config, no
  services.
- Rollout plan correctly states merging is the deployment; no restart or
  rollout needed. Rollback is a trivial file revert.

### Concerns
- No CI exists to validate Markdown or links, so a broken link could ship
  unnoticed. For a single hand-reviewed file this is acceptable, but worth
  noting as an unmitigated (low) risk.

### New libraries / infra dependencies
- None. Adding a Markdown linter / CI is explicitly out of scope and would be
  disproportionate for one file.

### Better alternatives considered
- None.

### Recommendations
- Rely on the manual verification steps in `testing.md`. Do not add CI for this.

### Questions for author
- None.

### Verdict: APPROVED

---

## Security Engineer - Cipher
**Focus:** AuthN/AuthZ, validation, OWASP, data protection.

### Strengths
- No executable code, no dependencies, no secrets, no data handling: negligible
  attack surface.
- Relative links avoid pointing contributors at a hardcoded (potentially
  spoofable) external URL.

### Concerns
- **Link targets:** any link in the guide should point within the repository
  (relative) or to a well-known trusted domain (github.com docs). Avoid
  shortened or third-party links that could later be repointed. The LLD's
  relative-link guidance satisfies this.
- Encourage contributors not to include secrets/credentials in issues or PRs.
  This is a nice-to-have, not a blocker.

### New libraries / infra dependencies
- None.

### Better alternatives considered
- None.

### Recommendations
- (Optional) Add a one-line note in the "Filing an issue" section reminding
  contributors not to paste secrets or personal data. Optional, non-blocking.

### Questions for author
- None.

### Verdict: APPROVED

---

## SMTS (Overall) - Sage
**Focus:** Architecture, code quality, maintainability.

### Strengths
- Scope is tightly matched to the task: exactly one new file, three required
  sections, no collateral changes.
- The LLD documents alternatives (README-embed, `.github/` placement, full
  suite) and justifies the root-placement choice against the repo's existing
  convention and GitHub auto-discovery.
- Maintainability is high: plain Markdown, no tooling to keep up to date.

### Concerns
- The guide should not drift from reality (for example, referencing a `main`
  branch that does not exist). The default-branch neutral phrasing handles this.
- Ensure the existing `README` truly stays untouched so the diff is minimal and
  reviewable.

### New libraries / infra dependencies
- None.

### Better alternatives considered
- Root placement vs `.github/`: both valid; root chosen for discoverability and
  convention match. Reasonable.

### Recommendations
- Proceed. Keep the diff to a single added file.

### Questions for author
- None.

### Verdict: APPROVED

---

## Review Summary

| Reviewer | Verdict | Blockers | Key Recommendation |
|----------|---------|----------|--------------------|
| Frontend (Pixel) | APPROVED | 0 | Use relative links, consistent headings |
| Backend (Byte) | APPROVED | 0 | Use default-branch-neutral phrasing (repo is `master`) |
| SRE (Circuit) | APPROVED | 0 | Manual verification is sufficient; no CI |
| Security (Cipher) | APPROVED | 0 | Keep links relative/trusted; optional "no secrets" note |
| SMTS (Sage) | APPROVED | 0 | Keep the diff to one added file; do not touch README |

## Triage of Findings (Step 7.5)

No reviewer raised a critical / must-fix / NEEDS REVISION finding. All verdicts
are APPROVED. The recommendations are either already in the LLD or optional:

- **Relative links (Pixel, Cipher):** already required by the LLD. No change
  needed. Resolution: already addressed in LLD Implementation Details.
- **Default-branch-neutral phrasing (Byte, Sage):** already required by the LLD
  ("reference the default branch rather than hardcoding `main`"). Resolution:
  already addressed in LLD.
- **Consistent headings (Pixel):** the LLD's sample uses one `#` H1 and `##`
  sections. Resolution: already addressed.
- **Optional "no secrets" note (Cipher):** nice-to-have, non-blocking. Adopted
  as a small enhancement in the implemented file since it is cheap and
  improves the guide; noted here so the review and implementation stay in sync.
- **No CI (Circuit):** intentional non-goal; documented as an accepted low risk.

**No blocking findings; proceeding to implementation.** The one optional item
(a brief "do not paste secrets" reminder) is incorporated into the implemented
`CONTRIBUTING.md` because it is low-cost and aligns with the security review.

## Next Steps
1. Implement `CONTRIBUTING.md` at the repository root per the (unchanged) LLD.
2. Verify per `testing.md`.
3. Capture `patch.diff` and write `implementation.md`.
