# Implementation: copy_to_clipboard config default

## Summary

Adds a `copy_to_clipboard` config key (values `enabled` / `disabled`, default `disabled`). When `-c` / `--clipboard` is absent, `gh auth login` and `gh auth refresh` read this key and copy the one-time OAuth device code to the clipboard when it is `enabled`. When the flag is passed explicitly, it wins in both directions: `--clipboard=false` disables copying even when the config is `enabled`, and `--clipboard` enables copying regardless of the config.

## Files touched (patch.diff, 8 files)

| File | Change |
|---|---|
| `internal/config/config.go` | Adds `copyToClipboardKey` constant, `CopyToClipboard()` accessor (`GetOrDefault("", key)`), and a registry entry (`ConfigOption`) with allowed values `enabled` / `disabled` and default `disabled`, appended last so `gh config list` shows it after `telemetry`. |
| `internal/gh/gh.go` | Adds `CopyToClipboard() ConfigEntry` to the `Config` interface, with a doc comment noting it is global. |
| `internal/gh/mock/config.go` | Regenerated with moq (see Deviations). Adds `CopyToClipboardFunc`, calls struct, lock, method and `CopyToClipboardCalls()`. |
| `internal/config/test.go` | Wires `mock.CopyToClipboardFunc` to `cfg.CopyToClipboard()` in `NewMockConfigFromString`, so mock-backed tests see the real value. |
| `pkg/cmd/auth/login/login.go` | Adds unexported `clipboardSet` to `LoginOptions`, set in `RunE` from `cmd.Flags().Changed("clipboard")`. `loginRun` computes `copyToClipboard := opts.Clipboard`, sets it to `true` when `!opts.clipboardSet` and the config is `enabled`, and passes it to `shared.Login`. |
| `pkg/cmd/auth/refresh/refresh.go` | Same pattern as login: unexported `clipboardSet` on `RefreshOptions`, set in `RunE`; `refreshRun` computes `copyToClipboard` the same way and passes it to `opts.AuthFlow`. |
| `pkg/cmd/auth/refresh/refresh_test.go` | New `copyToClipboard` table field; sets the key via `cfg.Set("", "copy_to_clipboard", ...)` before the run; new case "no hostname, one host configured, copy_to_clipboard config enabled" expects `clipboard: true`. gofmt realigned the existing struct field block, which accounts for the extra deletions in the diffstat. |
| `pkg/cmd/config/list/list_test.go` | Expected `gh config list` output gains `copy_to_clipboard=disabled` after `telemetry=enabled`. |

## Deviations

1. **moq toolchain.** `moq` on the installed Go 1.27.2 toolchain failed with `could not import github.com/cli/cli/v2/pkg/option ... export data version 5 is greater than maximum supported version 4`, and it had already deleted the old mock with `-rm`. The mock was restored from git, then regenerated with `GOTOOLCHAIN=go1.26.0 moq -pkg ghmock -out <tmp> . Config` and copied over the committed file. Regeneration also moved the `sync` import line, which shows in the diff.
2. **No login test for the config path.** `shared.Login` calls the auth flow directly, and `Test_loginRun_*` in `login_test.go` have no `AuthFlow` seam to capture the `clipboard` argument. The login config path has no permanent test. The refresh test covers the same resolution pattern. Adding a seam would widen the change beyond the LLD, so it was not done.
3. **No separate `config get` / `config set` tests.** The default `disabled` value is asserted through `list_test.go`. The allowed-value validation comes from the existing `ConfigOption` mechanism and was not re-tested.
4. **Precedence corrected after first capture.** The first capture combined the flag and config with `opts.Clipboard || cfg...Value == "enabled"`, so `--clipboard=false` could not override `copy_to_clipboard=enabled`. `lld.md` (section 3, line 103) says the config changes only the default when `-c` is absent, so an explicit flag must win.
   The fix tracks whether the flag was set (`cmd.Flags().Changed("clipboard")` in `RunE`) and consults config only when it was not. The first corrected attempt, `if !opts.clipboardSet { copyToClipboard = cfg... == "enabled" }`, broke the existing refresh case `no hostname, one host configured, clipboard enabled`. That case calls `refreshRun` with `Clipboard: true` directly, bypassing `RunE`, so `clipboardSet` stays false and the flag was dropped. The final rule keeps the flag as the base value and only ORs in config when the flag was not set, so the flag can enable copying in every path and config applies only when the flag is absent.

## Verification (run in the clone at baseline 45437bc7eeeb3359bbfddd1742f79de7652fd3e2 plus the patch)

- `gofmt -l internal pkg`: no files listed.
- `go build ./...`: exit 0.
- `go vet ./internal/config/ ./internal/gh/... ./pkg/cmd/auth/... ./pkg/cmd/config/list/`: exit 0.
- `go test ./internal/config/ ./internal/gh/... ./pkg/cmd/auth/... ./pkg/cmd/config/...`: all packages `ok`, including `pkg/cmd/auth/refresh` (`Test_refreshRun`, with the new `copy_to_clipboard config enabled` case and the existing `clipboard enabled` case) and `pkg/cmd/config/list`.
- Throwaway smoke test (deleted afterward, not in the patch): `RefreshOptions{clipboardSet: true, Clipboard: false}` with `copy_to_clipboard=enabled` yields `AuthFlow(... clipboard=false)`. PASS. This confirms explicit `--clipboard=false` beats config.
- Not covered by a permanent test: the explicit-false case and the login config path. The refresh test covers the config-enabled and flag-set paths; the explicit-false case was only smoke-tested.
- `patch.diff`: captured with `git add -A` then `git diff --staged 45437bc7eeeb3359bbfddd1742f79de7652fd3e2` in the clone. `git diff --staged --numstat` lists 8 files, matching the table above.
