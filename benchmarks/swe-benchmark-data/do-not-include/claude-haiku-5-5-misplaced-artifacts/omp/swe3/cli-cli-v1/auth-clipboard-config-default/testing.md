# Testing Plan: copy_to_clipboard config default

## Functional Tests

| # | Scenario | Expected |
|---|----------|----------|
| F1 | `gh config get copy_to_clipboard` with key unset | Prints `disabled`. |
| F2 | `gh config set copy_to_clipboard enabled`, then `gh config get copy_to_clipboard` | Prints `enabled`. |
| F3 | `gh config set copy_to_clipboard maybe` | Rejected; only `enabled` and `disabled` allowed. |
| F4 | `gh config list` with key unset | Output includes `copy_to_clipboard=disabled`. |
| F5 | `gh auth login` with config `enabled`, no `-c` | `AuthFlow` receives clipboard `true`. |
| F6 | `gh auth refresh` with config `enabled`, no `-c` | `AuthFlow` receives clipboard `true`. |
| F7 | `gh auth login -c` with config unset | Clipboard `true` (unchanged behavior). |
| F8 | `gh auth refresh -c` with config unset | Clipboard `true` (unchanged behavior). |
| F9 | `gh auth login` with config unset, no `-c` | Clipboard `false` (unchanged default). |

## Backwards-Compatibility Tests

- Existing `login_test.go` and `refresh_test.go` cases with `-c` or without it, and no config value, must still pass unchanged in their expected arguments.
- Existing `list_test.go` expected output gains exactly one line; no other keys change.

## UX Tests

- The `Description` string is shown by `gh config list` and help. It must read as a plain sentence and name both commands.

## Deployment Tests

- None. The change is a Go source change with a regenerated mock. No schema migration: the config file gains a key only when a user sets it.

## End-to-End Tests

- Build the `gh` binary from the patched clone and run F1 through F4 against an isolated `GH_CONFIG_DIR`.
- F5 and F6 are covered by unit tests with `AuthFlow` stubs; a live device flow is not run.

## Verification in This Run

The swe3 skill does not execute the target repository's test suite. Verification in this run is limited to `gofmt -l` on changed files and `go vet ./internal/config/... ./pkg/cmd/auth/...` after implementation, with results recorded in `implementation.md`.
