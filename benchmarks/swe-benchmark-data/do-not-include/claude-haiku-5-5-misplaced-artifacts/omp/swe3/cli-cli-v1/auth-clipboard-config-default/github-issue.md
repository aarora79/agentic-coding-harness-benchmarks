# GitHub Issue: Let users make "copy device code to clipboard" the default for `gh auth login` and `gh auth refresh`

**Labels:** enhancement, auth

## Description

### Problem Statement

`gh auth login` and `gh auth refresh` copy the one-time OAuth device code to the clipboard only when `-c` / `--clipboard` is passed. Users who always want the code copied must add the flag to every invocation. There is no configuration setting for this preference, so the flag cannot be made a default.

### Proposed Solution

Add a global configuration key `copy_to_clipboard` with allowed values `enabled` and `disabled`. The default is `disabled`, so existing behavior does not change.

- When the key is `enabled`, `gh auth login` and `gh auth refresh` copy the device code as if `-c` were passed, without the flag.
- The `-c` flag keeps working. It enables copying for a single run even when the config value is `disabled`.
- The key is global, like `telemetry`. It is not scoped by hostname.

### User Stories

- As a user who always signs in from a remote or headless session, I want to set `copy_to_clipboard` once so that `gh auth login` copies the device code without my typing `-c` each time.
- As a user who has the setting enabled, I want `gh auth refresh` to honor it the same way, so the two commands behave consistently.

### Acceptance Criteria

- [ ] `gh config get copy_to_clipboard` prints `disabled` when the key was never set.
- [ ] `gh config set copy_to_clipboard enabled` causes `gh auth login` to copy the device code without `-c`.
- [ ] `gh config set copy_to_clipboard enabled` causes `gh auth refresh` to copy the device code without `-c`.
- [ ] `gh config set copy_to_clipboard maybe` is rejected, because only `enabled` and `disabled` are allowed.
- [ ] `gh config list` includes `copy_to_clipboard=disabled` when the key is unset.
- [ ] With the key unset, `gh auth login -c` and `gh auth refresh -c` still copy the device code (no behavior change).

### Out of Scope

- A `--no-clipboard` flag that overrides an `enabled` config value for one run. Only `enabled` in config can be overridden by disabling the config key; the flag can only enable copying.
- Host-scoped configuration of this key.
- Clipboard behavior for any other command.

### Dependencies

None. The `clipboard` package is already imported by `internal/authflow`.

### Related Issues

None.
