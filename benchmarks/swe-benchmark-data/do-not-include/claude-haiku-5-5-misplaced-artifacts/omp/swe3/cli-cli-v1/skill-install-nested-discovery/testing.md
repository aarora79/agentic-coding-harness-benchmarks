# Testing plan: nested hidden-directory skill discovery

Repository: `cli/cli` at `f96972c` (see [lld.md](./lld.md)). All commands run from the `cli/` checkout.

## 1. Functional tests (matcher)

Add rows to `TestMatchHiddenDirConventions` in `internal/skills/discovery/discovery_test.go`:

| name | path | expected |
|---|---|---|
| nested claude skills directory | `pkg/.claude/skills/code-review/SKILL.md` | hidden-dir, `code-review` |
| nested github namespaced skill | `a/b/.github/skills/monalisa/issue-triage/SKILL.md` | hidden-dir-namespaced, `issue-triage`, ns `monalisa` |
| nested dot dir not followed by skills | `pkg/.claude/nested/skills/code-review/SKILL.md` | nil |
| skills dir without dot parent at depth | `pkg/app/skills/code-review/SKILL.md` | nil from hidden matcher (standard matcher still matches) |

Run:

```bash
go test ./internal/skills/discovery/ -run TestMatchHiddenDirConventions -v
```

Existing row `too deeply nested hidden dir` (`.claude/nested/skills/code-review/SKILL.md` -> nil) must still pass.

## 2. Backwards compatibility

```bash
go test ./internal/skills/discovery/ ./pkg/cmd/skills/...
```

All existing tests must pass unchanged. Root-level hidden rows, standard rows, plugin rows, and install/preview hidden-dir tests (`allow-hidden-dirs includes hidden skills`, and the "no standard skills found" error) are unchanged.

## 3. UX

- Without `--allow-hidden-dirs`, a repo with only `pkg/.claude/skills/x/SKILL.md` must print the "no standard skills found, but 1 skill(s) exist in hidden directories" error. Verified by the install test that already covers that message for root-level hidden skills; the matcher change feeds the same path.
- With `--allow-hidden-dirs`, the origin warning is printed. Same code path as root-level hidden skills.

## 4. Deployment surface

Not applicable: CLI library change, no Docker, Terraform, or ECS surface.

## 5. End-to-end

- Smoke: build the binary and run discovery against a local fixture (see implementation.md for the exact command used).
- Upstream-API E2E is out of scope: the discovery path is driven by the GitHub tree API; the matcher is the changed boundary and is exercised with real tree paths in the unit table.

## 6. Test execution checklist

- [ ] Section 1 matcher rows added and passing
- [ ] Section 2 full discovery and install packages passing
- [ ] Section 3 UX messages confirmed by existing install tests
- [ ] Section 4 not applicable
- [ ] Section 5 smoke run recorded in implementation.md
- [ ] Probe file removed

## Guidance

1. Each new row asserts a single boundary (positive or negative).
2. Negative rows protect against over-matching the `.claude/nested/skills` restriction.
3. No new test for the probe itself; the table rows are the permanent form.
