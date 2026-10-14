# Skill discovery misses skills in nested hidden directories even with --allow-hidden-dirs

## Summary

`gh skill install <owner/repo> --allow-hidden-dirs` does not find skills stored under a dot-prefixed directory that is not at the repository root, for example `packages/app/.claude/skills/<name>/SKILL.md`. Only dot-directories at the repository root (`.claude/skills/`, `.agents/skills/`, `.github/skills/`, `.copilot/skills/`) are recognised. Nested skills in standard `skills/` directories already work.

Related upstream report: cli/cli#13372 (skill discovery does not traverse nested `skills/` directories with `--allow-hidden-dirs`).

## Reproduction

1. Create a repository containing `packages/app/.claude/skills/code-review/SKILL.md` with valid frontmatter, and no other skills.
2. Run `gh skill install <owner/repo> --allow-hidden-dirs`.
3. Observed: `no skills found in <owner>/<repo>` and the expected-locations hint.
4. Expected: `code-review` is discovered and offered for install.

The same repository with the skill at `packages/app/skills/code-review/SKILL.md` is discovered without any flag. That case is not part of this issue.

## Expected behaviour

- A skill whose `skills/` directory sits under a dot-prefixed directory at any depth is discovered, provided the dot-directory is immediately followed by `skills/`.
- It is classified as a hidden-dir skill, so the existing `--allow-hidden-dirs` gate, the origin warning, and the "no standard skills found, but N skill(s) exist in hidden directories" error apply unchanged.
- Without `--allow-hidden-dirs`, nested hidden skills stay excluded.

## Non-goals

- Installing from arbitrary non-`skills` directories (for example `skills-catalog/<name>/`) by path. That is a separate request.
- Changing the `--allow-hidden-dirs` default or the origin warning text.
- Matching `.x/nested/skills/` (a `skills/` directory that is not directly under the dot-directory).

## Acceptance criteria

- `discovery.matchHiddenDirConventions` matches `pkg/.claude/skills/<name>/SKILL.md` (hidden-dir) and `a/b/.github/skills/<scope>/<name>/SKILL.md` (hidden-dir-namespaced).
- `.claude/nested/skills/<name>/SKILL.md` and `x/.claude/nested/skills/<name>/SKILL.md` still do not match.
- Existing discovery and install tests pass unchanged.
