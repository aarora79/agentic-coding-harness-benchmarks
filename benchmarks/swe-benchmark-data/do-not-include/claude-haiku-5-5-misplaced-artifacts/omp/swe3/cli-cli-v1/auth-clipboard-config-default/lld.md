# Low-Level Design: copy_to_clipboard config default for gh auth login and refresh

**Created:** 2026-10-14
**Author:** Claude
**Status:** Draft

## Table of Contents

1. [Overview](#overview)
2. [Codebase Analysis](#codebase-analysis)
3. [Architecture](#architecture)
4. [Data Models](#data-models)
5. [API / CLI Design](#api--cli-design)
6. [Configuration Parameters](#configuration-parameters)
7. [New Dependencies](#new-dependencies)
8. [Implementation Details](#implementation-details)
9. [Observability](#observability)
10. [File Changes](#file-changes)
11. [Testing Strategy](#testing-strategy)
12. [Alternatives Considered](#alternatives-considered)
13. [Rollout Plan](#rollout-plan)

## Overview

### Problem Statement

The `--clipboard` / `-c` flag on `gh auth login` and `gh auth refresh` copies the one-time device code to the clipboard. The flag is required on every run. No config value controls it.

### Goals

- Goal 1: Add a global config key `copy_to_clipboard` (`enabled` | `disabled`, default `disabled`).
- Goal 2: When the value is `enabled`, `login` and `refresh` copy the device code as if `-c` were given.
- Goal 3: `-c` keeps working unchanged.

### Non-Goals

- A negative flag (`--no-clipboard`). Out of scope per the issue.
- Host-scoped config for this key.

## Codebase Analysis

### Files Reviewed

| Path | Purpose | Relevance to This Change |
|------|---------|--------------------------|
| `internal/gh/gh.go` | `gh.Config` interface, generated mock source | Interface gains `CopyToClipboard()`. |
| `internal/config/config.go` | Config accessors, key constants, option registry | Adds key constant, accessor, registry entry. |
| `internal/config/test.go` | `NewMockConfigFromString` wiring of mock funcs | Must wire the new func or tests calling it panic. |
| `internal/gh/mock/config.go` | moq-generated `ConfigMock` | Regenerated with the installed `moq`. |
| `pkg/cmd/auth/login/login.go` | `loginRun` builds `shared.LoginOptions` | Resolves the effective clipboard value. |
| `pkg/cmd/auth/refresh/refresh.go` | `refreshRun` calls `opts.AuthFlow` | Resolves the effective clipboard value. |
| `pkg/cmd/auth/shared/login_flow.go` | `shared.Login`, `iconfig` interface | Not changed: `iconfig` exposes only `Login` and `UsersForHost`, and the value is resolved before this call. |
| `pkg/cmd/config/list/list_test.go` | Expected `gh config list` output | Gains one line. |
| `internal/config/config_test.go` | `TestTelemetry` pattern | New `TestCopyToClipboard` mirrors it. |

### Patterns Identified

- Global accessor precedent: `Telemetry()` in `config.go` ignores hostname, calls `c.GetOrDefault("", telemetryKey).Unwrap()`, and `Telemetry` in the registry uses `DefaultValue` and `AllowedValues`. This change copies that shape.
- Mock precedent: `TelemetryFunc` is a no-argument method and its mock layout is the template for `CopyToClipboardFunc`.
- Constant alignment: the `const` block in `config.go` is aligned by gofmt; the new key is padded to the existing column width.

### Integration Points

- `gh config get|set|list` picks up the new key automatically from the option registry (`internal/config/config.go`, `Options` slice).
- `login.go` and `refresh.go` read the value from the `gh.Config` they already obtain via `opts.Config()`.

### Constraints Discovered

- `shared.iconfig` is a narrow interface used by `shared.Login` tests. Widening it would ripple into test doubles. Resolution is done in `loginRun` before `shared.Login` is called.
- `refreshRun` already calls `opts.Config()` at the top, so no extra config load is needed.
- Mock regeneration: `internal/gh/gh.go` carries `//go:generate moq -rm -pkg ghmock -out mock/config.go . Config`. Regenerating keeps the mock byte-consistent with the interface.

## Architecture

```text
gh config set copy_to_clipboard enabled
        |
        v
config file (hosts-agnostic key "copy_to_clipboard")
        |
        v
cfg.CopyToClipboard()  -- gh.Config accessor, global, default "disabled"
        |
        +--> loginRun:   copyToClipboard := opts.Clipboard || cfg value == enabled
        |                  -> shared.LoginOptions.CopyToClipboard
        |
        +--> refreshRun: clipboard := opts.Clipboard || cfg value == enabled
                           -> opts.AuthFlow(..., clipboard)
```

Resolution is an OR. The flag can only turn copying on. Config `enabled` plus no flag copies. Config `disabled` plus `-c` copies.

## Data Models

No new structs. The accessor returns the existing `gh.ConfigEntry` (`Value`, `Source`), following `Telemetry()`.

| Field | Type | Values | Default |
|-------|------|--------|---------|
| `copy_to_clipboard` | string (config file) | `enabled`, `disabled` | `disabled` (`gh.ConfigDefaultProvided`) |

## API / CLI Design

No new flags. `-c` / `--clipboard` on `login` and `refresh` is unchanged. Behavior change is only in the default when `-c` is absent.

`gh config set copy_to_clipboard <enabled|disabled>` is the new user-facing surface, provided by the registry entry. `AllowedValues` rejects anything else.

## Configuration Parameters

| Key | Default | Scope | Allowed | Description |
|-----|---------|-------|---------|-------------|
| `copy_to_clipboard` | `disabled` | Global | `enabled`, `disabled` | Copy the one-time OAuth device code to the clipboard during `gh auth login` and `gh auth refresh`, without `-c`. |

The default config template (`defaultConfigStr`, `internal/config/config.go`) does not list `telemetry` or any other registry key, so the registry `DefaultValue` is the only place the default is declared. No other config file changes are needed.

## New Dependencies

None.

## Implementation Details

1. `internal/gh/gh.go`: add to `gh.Config`:
   ```go
   // CopyToClipboard returns the configured copy_to_clipboard setting. It ignores host scoping since this is a global setting.
   CopyToClipboard() ConfigEntry
   ```
2. `internal/config/config.go`:
   - Add `copyToClipboardKey = "copy_to_clipboard"` to the `const` block, aligned with gofmt.
   - Add the accessor after `Telemetry()`:
     ```go
     func (c *cfg) CopyToClipboard() gh.ConfigEntry {
         // Intentionally panic if there is no user provided value or default value (which would be a programmer error)
         return c.GetOrDefault("", copyToClipboardKey).Unwrap()
     }
     ```
   - Append a registry entry after the `telemetry` entry:
     ```go
     {
         Key:           copyToClipboardKey,
         Description:   "whether to copy the one-time OAuth device code to the clipboard during gh auth login and refresh",
         DefaultValue:  "disabled",
         AllowedValues: []string{"enabled", "disabled"},
         CurrentValue: func(c gh.Config, hostname string) string {
             return c.CopyToClipboard().Value
         },
     },
     ```
  - No change to `defaultConfigStr`: it does not list registry keys such as `telemetry`, and the registry `DefaultValue` supplies the default.
3. `internal/config/test.go`: wire `mock.CopyToClipboardFunc = func() gh.ConfigEntry { return cfg.CopyToClipboard() }`.
4. `internal/gh/mock/config.go`: regenerate with `moq -rm -pkg ghmock -out mock/config.go . Config` from `internal/gh`.
5. `pkg/cmd/auth/login/login.go`, `loginRun`: replace `CopyToClipboard: opts.Clipboard` with a resolved value:
   ```go
   copyToClipboard := opts.Clipboard || cfg.CopyToClipboard().Value == "enabled"
   ```
   and pass `copyToClipboard` into `shared.LoginOptions`.
6. `pkg/cmd/auth/refresh/refresh.go`, `refreshRun`: after `cfg` is loaded, compute the same resolved value and pass it to `opts.AuthFlow(...)` in place of `opts.Clipboard`.
7. `pkg/cmd/config/list/list_test.go`: add `copy_to_clipboard=disabled` after `telemetry=enabled` in the expected output.

Error handling: the accessor panics on a missing default, as `Telemetry()` does. The registry default guarantees this cannot happen. No new error paths.

## Observability

None. The existing `gh` output is unchanged. No log lines are added.

## File Changes

| File | Action | Summary |
|------|--------|---------|
| `internal/gh/gh.go` | Modify | Add `CopyToClipboard()` to `Config`. |
| `internal/config/config.go` | Modify | Key constant, accessor, registry entry. |
| `internal/gh/mock/config.go` | Regenerate | `ConfigMock` gains `CopyToClipboard` mock. |
| `internal/config/test.go` | Modify | Wire `CopyToClipboardFunc`. |
| `internal/config/config_test.go` | Modify | Add `TestCopyToClipboard`. |
| `pkg/cmd/auth/login/login.go` | Modify | Resolve config OR flag in `loginRun`. |
| `pkg/cmd/auth/refresh/refresh.go` | Modify | Resolve config OR flag in `refreshRun`. |
| `pkg/cmd/auth/refresh/refresh_test.go` | Modify | Add a case: config enabled, no `-c`, AuthFlow receives `true`. |
| `pkg/cmd/auth/login/login_test.go` | Modify | Add cases: config enabled with no `-c` yields `CopyToClipboard: true`; config unset yields `false`. Login tests use `NewMockConfigFromString`, so `test.go` wiring is required. |
| `pkg/cmd/config/list/list_test.go` | Modify | Expected output gains `copy_to_clipboard=disabled`. |

## Testing Strategy

See `testing.md`. Unit tests cover the accessor default and user value, the refresh resolution, and the `config list` output. Verification in this run is compile-level only (`gofmt`, `go vet`), because the swe3 skill does not run the target repository's test suite.

## Alternatives Considered

1. **Set the flag default at command construction from `f.Config()`.** Rejected. It reads config while the command tree is built, which runs for `--help` and for every `gh` invocation. A config load failure would break unrelated commands.
2. **Tri-state flag with `--no-clipboard`.** Rejected. The issue puts it out of scope, and it adds a flag to two commands.
3. **Host-scoped key.** Rejected. Clipboard use is a terminal property, not a host property. `telemetry` sets the precedent for a global key.
4. **Widen `shared.iconfig` to expose the value.** Rejected. It would change the test double used by `shared.Login` tests. Resolving in `loginRun` keeps the change local.

## Rollout Plan

Default `disabled` means no behavior change for existing users. No migration, no deprecation. The change ships in the next minor release of `gh`.
