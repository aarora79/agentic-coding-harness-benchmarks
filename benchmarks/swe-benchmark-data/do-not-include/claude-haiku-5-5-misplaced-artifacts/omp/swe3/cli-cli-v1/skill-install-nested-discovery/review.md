# Expert review: nested hidden-directory skill discovery

Reviewed against [lld.md](./lld.md). Personas were applied inline, in sequence, by the single agent that wrote the design.

## Maintainer (discovery package)

- Finding (should-fix): the hidden matcher's doc comment lists only the root forms. Resolution: update the comment with `{prefix}/.{host}/skills/...` forms. Included in the LLD file list.
- Finding (must-fix): without the `hiddenRoot != "."` guard, `path.Base(".")` yields a dot-prefixed name and `skills/x/SKILL.md` would become a hidden-dir match. Resolution: guard added to `isHiddenSkillsDir` in the LLD. Covered by a negative test row.
- Verdict: approve with the two changes above.

## Install and preview owner

- Finding: no change needed in install or preview; both partition on the convention string. Confirmed by grep: `PartitionHiddenDirSkills` is the only partition point in both packages.
- Finding (should-fix): the no-flag error path now fires for repos that previously showed "no skills found". Resolution: intended behaviour, documented in the LLD risks section. No code change.
- Verdict: approve.

## Security

- Finding: nested hidden directories expand what `--allow-hidden-dirs` installs from. Skills there are third-party copies by design, and the existing origin warning covers that. The default (no flag) path still excludes them, so the default attack surface is unchanged. Resolution: no code change; risk recorded in the LLD.
- Finding: no new input is parsed; matching is string-only on tree paths already returned by the API. No new network call.
- Verdict: approve.

## Test quality

- Finding (must-fix): a test that only asserts the new positive row would not catch over-matching. Resolution: add negative rows for `pkg/.claude/nested/skills/...` and for a `skills/` directory with no dot parent at depth, mirroring the existing `.claude/nested/skills` row.
- Finding: do not add a permanent test for the probe itself; the table rows cover the same boundary. Resolution: probe file to be deleted after use.
- Verdict: approve with the negative rows.

## Resolutions applied to the LLD

- Doc-comment update and `hiddenRoot != "."` guard: already reflected in the LLD design section.
- Negative test rows: reflected in the test plan summary; full list in testing.md.
- Deferred: the plugin-ancestor exclusion for hidden matches is not added. Stated as an open risk in the LLD so the reviewer can decide.
