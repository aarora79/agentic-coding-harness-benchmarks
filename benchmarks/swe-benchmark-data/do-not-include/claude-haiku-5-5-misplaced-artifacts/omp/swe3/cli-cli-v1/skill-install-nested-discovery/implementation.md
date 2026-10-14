# Implementation: nested hidden-directory skill discovery

Source: `cli/cli` at `f96972c` (base `v2.93.0`), edited in the disposable clone `/tmp/swe-clone-skill-install-nested-discovery/cli`. The captured diff is [patch.diff](./patch.diff) (3 files, +52 / -24).

## What changed

- `internal/skills/discovery/discovery.go`
  - `matchHiddenDirConventions` now accepts a dot-prefixed directory at any depth, not only at the repository root. The `skills/` directory must still be a direct child of the dot-directory.
  - New helper `isHiddenSkillsDir(dir)`: true when `dir` ends in `skills` and its parent's base name starts with `.`. The `hiddenRoot != "."` guard stops a root-level `skills/` from matching as hidden.
  - Doc comment rewritten to show the `<prefix>/.{host}/skills/...` forms.
- `internal/skills/discovery/discovery_test.go`: four rows added to `TestMatchHiddenDirConventions` (two positive, two negative).
- `skills/gh-skill/SKILL.md`: the `--allow-hidden-dirs` description now says the directory may be nested.

No change to `pkg/cmd/skills/install` or `pkg/cmd/skills/preview`. Both gate on `discovery.PartitionHiddenDirSkills`, which keys on the convention string, so they pick up the fix without edits.

## Checks run

1. Baseline before edits: `go test ./internal/skills/discovery/ ./pkg/cmd/skills/install/` passed.
2. Probe before the fix (throwaway, deleted): `pkg/.claude/skills/code-review/SKILL.md` and `a/b/.github/skills/...` returned nil; `foo/bar/skills/code-review/SKILL.md` matched the standard matcher.
3. After the fix: `go vet` clean, `gofmt -l` empty, `go test ./internal/skills/discovery/ ./pkg/cmd/skills/... -count=1` all `ok`. `TestMatchHiddenDirConventions` passes all 17 subtests, including the four new rows.
4. Built binary (`go build ./cmd/gh`) against a fixture with `packages/app/.claude/skills/code-review/SKILL.md`:
   - no flag: "no standard skills found, but 1 skill(s) exist in hidden directories ... Use --allow-hidden-dirs". Install refused.
   - `--allow-hidden-dirs`: origin warning printed, `code-review` installed to `~/.claude/skills/code-review/SKILL.md`.
5. Built binary against `pkg/app/skills/code-review/SKILL.md` with no flag: installed through the standard matcher, so the non-dot nested case is unchanged.

Probe file `probe_scratch_test.go` deleted before the final test run; `git status` shows only the three intended files modified.

## Not run

- No live GitHub API run. Discovery was exercised through the local path (`--from-local`), which uses the same matchers (`DiscoverLocalSkillsWithOptions`, the same match loop as the tree-based path). The tree-based path was covered only by the unit table.
- `go test ./...` over the whole CLI was not run; only the discovery and skills packages.

## Open risk

Plugin ancestors are not excluded for hidden matches, as recorded in [lld.md](./lld.md). Unchanged behavior from the root-level hidden matcher.
