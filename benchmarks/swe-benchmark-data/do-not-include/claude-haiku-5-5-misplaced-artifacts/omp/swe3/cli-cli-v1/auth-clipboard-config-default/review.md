# Expert Review: copy_to_clipboard config default

Reviewed: `lld.md` (initial draft). Reviews performed inline, one persona at a time, per the single-agent variant.

## Persona: Staff Engineer (architecture)

- **Should-fix, resolved.** The draft cited a non-existent YAML config for `gh` keys. The claim was unverified and irrelevant: the three-layer rule in the benchmark repo does not apply to the cloned `gh` source. Removed from the LLD; the registry `DefaultValue` is the single source of the default.
- **Verified.** `defaultConfigStr` (`internal/config/config.go`) does not list registry keys such as `telemetry`. No template change is needed.

## Persona: gh CLI Maintainer (conventions)

- **Must-fix, resolved.** Resolution must happen in `loginRun` and `refreshRun`, not at command construction. Construction-time config reads would run on every `gh` invocation including `--help`. LLD Alternatives #1 records this.
- **Should-fix, resolved.** The file table omitted `pkg/cmd/auth/login/login_test.go`. Login tests use `NewMockConfigFromString`, so the `test.go` wiring is required for them. Row added.
- **Verified.** `refreshRun` already loads `cfg` before `opts.AuthFlow` is called (`refresh.go` lines 134-137), so the OR costs no extra config load.

## Persona: Security Reviewer

- **Note, no action.** The setting only controls whether a one-time device code is written to the system clipboard. It does not change token storage, scopes, or the OAuth flow. Clipboard exposure is the same as the existing `-c` path.

## Persona: QA

- **Should-fix, resolved.** Test plan must cover config unset, config `enabled` with no flag, and `-c` with config `disabled`. Covered in `testing.md`.
- **Must-fix, open until implementation.** `copy_to_clipboard` must appear in `config list` expected output (`list_test.go`), or the existing list test fails.

## Persona: Product / UX

- **Note, accepted.** Config `enabled` cannot be overridden per run; there is no `--no-clipboard`. Issue lists this as out of scope. Accepted.

## Disposition

No blocker remains in the LLD. The must-fix QA item is an implementation step (step 7 of the LLD) and is tracked in `testing.md`.
