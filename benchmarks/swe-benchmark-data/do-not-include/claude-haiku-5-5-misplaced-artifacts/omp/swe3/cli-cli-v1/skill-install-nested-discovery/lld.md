# Low-Level Design: nested hidden-directory skill discovery

Related issue: [github-issue.md](./github-issue.md)

## Context

Skill discovery in `internal/skills/discovery/discovery.go` runs one recursive git tree listing per repository (`DiscoverSkillsWithOptions`). Each blob is passed to two matchers in order:

1. `matchSkillConventions`: standard `skills/`, `skills/{scope}/`, `plugins/`, root conventions. It returns nil for any path containing a dot-prefixed segment (`hasHiddenSegment`), so hidden-directory skills never reach the standard convention.
2. `matchHiddenDirConventions`: returns `hidden-dir` / `hidden-dir-namespaced` only when the dot-directory is at the repository root (`path.Dir(hiddenRoot) == "."`).

Install (`pkg/cmd/skills/install/install.go` `filterHiddenDirSkills`) and preview (`pkg/cmd/skills/preview/preview.go`) partition on `Skill.IsHiddenDirConvention()`, which compares the convention string. They need no change.

## Verified current behaviour

A throwaway probe in the discovery package (deleted after use) printed:

| path | standard matcher | hidden matcher |
|---|---|---|
| `foo/bar/skills/code-review/SKILL.md` | skills | nil |
| `packages/agent-skills/code-review/SKILL.md` | nil | nil |
| `pkg/.claude/skills/code-review/SKILL.md` | nil | nil (bug) |
| `pkg/.claude/skills/monalisa/code-review/SKILL.md` | nil | nil (bug) |
| `a/b/.github/skills/issue-triage/SKILL.md` | nil | nil (bug) |
| `.claude/nested/skills/code-review/SKILL.md` | nil | nil (intended) |
| `x/.claude/nested/skills/code-review/SKILL.md` | nil | nil (intended) |

Root cause: the standard matcher excludes hidden segments, and the hidden matcher hard-codes the dot-directory to the repository root.

## Design

Generalise `matchHiddenDirConventions` so the dot-directory may appear at any depth, with the one constraint that its `skills/` directory is a direct child. Add a helper:

```go
// isHiddenSkillsDir reports whether dir is a skills/ directory whose parent is
// a dot-prefixed directory, at any depth: ".claude/skills" or "pkg/.claude/skills".
func isHiddenSkillsDir(dir string) bool {
	if path.Base(dir) != "skills" {
		return false
	}
	hiddenRoot := path.Dir(dir)
	return hiddenRoot != "." && strings.HasPrefix(path.Base(hiddenRoot), ".")
}
```

`matchHiddenDirConventions` then becomes:

- `parentDir` is a hidden skills dir: return `hidden-dir`.
- `grandparentDir` is a hidden skills dir: validate the namespace, return `hidden-dir-namespaced`.
- Otherwise nil.

The `hiddenRoot != "."` guard is required: `path.Base(".")` is `"."`, which has the dot prefix, so `skills/x/SKILL.md` would otherwise match as hidden.

Dedup in `DiscoverSkillsWithOptions` (`seen[m.skillDir]`) is unchanged. The standard matcher runs first, and the two matchers cannot both match a path because the standard one rejects hidden segments.

## Files

- `cli/internal/skills/discovery/discovery.go`: add `isHiddenSkillsDir`; rewrite the two branches of `matchHiddenDirConventions`; update its doc comment (it currently lists only the root forms).
- `cli/internal/skills/discovery/discovery_test.go`: add rows to `TestMatchHiddenDirConventions` (below).
- `cli/skills/gh-skill/SKILL.md` (the `--allow-hidden-dirs` bullet): one clause noting that nested dot-directories are included.

No change to install, preview, the flag, or the warning text.

## Test plan (summary; full list in testing.md)

- New matcher rows: nested hidden-dir, nested hidden-dir-namespaced, and two negative cases (`pkg/.claude/nested/skills/...`, `skills/` without a dot parent at depth).
- Existing rows, including `.claude/nested/skills/code-review/SKILL.md` expected nil, must still pass.

## Risks and decisions

- Behaviour change without the flag: a repository whose only skills are nested hidden ones now gets "no standard skills found, but N skill(s) exist in hidden directories" instead of "no skills found". This is the intended message for hidden skills and is the same message root-level hidden skills already produce. Accepted.
- Repositories with vendored copies under nested dot-directories become visible to `--allow-hidden-dirs` users. The existing origin warning already covers this class. Accepted.
- Plugin ancestors: the standard matcher excludes `plugins/` ancestors for `skills/` nesting. The new hidden matcher does not, because the original hidden matcher did not either, and `plugins/x/.claude/skills/y` is an unusual layout. Not changed; noted for review.
- Dot-directories that are not agent homes (for example `.cache/skills/`) are matched, but only with `--allow-hidden-dirs`. Same exposure as root-level `.cache/skills/` today.
- No performance impact: matching is string-only, per blob, in the existing single tree pass.
