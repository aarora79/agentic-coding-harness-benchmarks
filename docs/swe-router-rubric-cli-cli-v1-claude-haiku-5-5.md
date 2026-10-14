# How omp + us.anthropic.claude-haiku-5-5 scores each task on the rubric

The rubric pass over `benchmarks/dataset/cli-cli-v1.yaml`: each task scored on six dimensions, 0 to 2, 3 independent time(s), in a clone of its repository at the task's pinned ref. No model output was read; this describes the tasks only. Code turns the scores into a required quality and a difficulty bucket (`routing-policy.json`).

- **Stability.** Required quality agreed across repeats on 16/21 tasks; the bucket on 13/21.
- **Runs.** 63 succeeded, 0 failed. Cost $0.6335.
- **Judged.** 2026-10-14T22:10:12.037956Z to 2026-10-14T22:21:48.671252Z.

Columns: HC hidden contract, SI silent invariant, CS coordinated surfaces, AM ambiguity, VE verification, BR blast radius. Each score is the lower median of the repeats.

| Task | HC | SI | CS | AM | VE | BR | Quality | Bucket | Confidence | Repeats agree |
|---|---:|---:|---:|---:|---:|---:|---:|---|---|---|
| repo-create-reject-empty-name | 1 | 1 | 1 | 1 | 1 | 1 | **70** | hard | medium | quality [70.0, 70.0, 70.0]; buckets {'hard': 1, 'moderate': 2} |
| copilot-not-installed-trailing-newline | 0 | 0 | 0 | 1 | 2 | 1 | **75** | easy | high | quality [70.0, 75.0, 75.0]; buckets {'moderate': 1, 'easy': 2} |
| repo-set-default-unset-without-repo | 1 | 1 | 1 | 2 | 1 | 1 | **70** | hard | medium | yes |
| pr-checks-all-cancelled-summary | 1 | 0 | 0 | 1 | 0 | 1 | **70** | moderate | high | yes |
| extension-uninstall-alias | 1 | 0 | 0 | 1 | 1 | 1 | **70** | moderate | high | yes |
| pr-merge-delete-branch-owner-case | 1 | 1 | 0 | 1 | 1 | 1 | **70** | moderate | high | quality [70.0, 70.0, 70.0]; buckets {'moderate': 2, 'hard': 1} |
| pr-view-json-number-on-issue | 1 | 1 | 1 | 2 | 1 | 1 | **70** | hard | medium | yes |
| project-item-add-output-non-tty | 1 | 0 | 0 | 1 | 1 | 1 | **70** | moderate | medium | yes |
| release-create-404-scope-blame | 1 | 1 | 1 | 1 | 1 | 1 | **70** | hard | high | yes |
| pr-comment-attach-ghu-tokens | 1 | 2 | 1 | 1 | 0 | 1 | **70** | hard | medium | quality [70.0, 70.0, 70.0]; buckets {'very_hard': 1, 'hard': 2} |
| repo-clone-ghe-ssh-ca-url | 1 | 1 | 1 | 2 | 1 | 1 | **70** | hard | medium | yes |
| codespace-ports-forward-concurrent-map | 1 | 2 | 1 | 2 | 1 | 1 | **70** | very_hard | medium | quality [70.0, 70.0, 75.0]; buckets {'very_hard': 3} |
| issue-view-comments-with-json | 1 | 1 | 1 | 1 | 0 | 1 | **70** | hard | high | yes |
| release-verify-sha1-prefix | 1 | 1 | 1 | 1 | 1 | 1 | **70** | hard | medium | quality [70.0, 70.0, 70.0]; buckets {'hard': 2, 'very_hard': 1} |
| auth-refresh-hint-on-expired-token | 1 | 1 | 1 | 2 | 2 | 1 | **75** | hard | medium | quality [70.0, 75.0, 75.0]; buckets {'hard': 3} |
| secret-set-app-agents | 2 | 1 | 1 | 1 | 1 | 1 | **70** | hard | medium | quality [70.0, 70.0, 75.0]; buckets {'very_hard': 2, 'hard': 1} |
| repo-sync-checked-out-worktree | 1 | 2 | 1 | 2 | 1 | 2 | **75** | very_hard | medium | quality [75.0, 75.0, 80.0]; buckets {'very_hard': 2, 'hard': 1} |
| auth-clipboard-config-default | 1 | 1 | 2 | 1 | 1 | 1 | **70** | hard | medium | yes |
| project-item-edit-by-name | 1 | 1 | 1 | 2 | 1 | 1 | **70** | hard | medium | yes |
| skill-update-dir-keeps-install-path | 1 | 2 | 1 | 2 | 1 | 2 | **75** | very_hard | high | yes |
| skill-install-nested-discovery | 1 | 1 | 1 | 2 | 1 | 1 | **70** | hard | medium | quality [70.0, 70.0, 70.0]; buckets {'hard': 2, 'very_hard': 1} |

## What each task needs

### repo-create-reject-empty-name

The change needs an empty-name check in interactiveRepoNameAndOwner (create.go:929) that fails right after the "Repository name" prompt, using the existing "argument error" convention, with a new empty-name case in create_test.go's interactive table. Whether the non-interactive path and whitespace-only names also need rejecting is not stated in the task and was not confirmed against the repo's intent.

### copilot-not-installed-trailing-newline

The change is a one-line newline fix to the declined-install warning in runCopilot (pkg/cmd/copilot/copilot.go:155) plus a new test asserting the exact ErrOut content and SilentError return, using the existing prompter mock and TTY-simulated iostreams. The main judgement is whether to also add a newline to the non-prompt warning at copilot.go:159, which the task does not name.

### repo-set-default-unset-without-repo

The fix is a small RunE change in pkg/cmd/repo/setdefault/setdefault.go so non-interactive `--unset` skips the 'repository required' check, as `--view` already does, while plain `set-default` keeps the error. The real decision is what to do with a repository argument passed alongside `--unset`, which currently unsets the default silently. Tests go in setdefault_test.go for non-TTY `--unset`, non-TTY `--view` without an argument, and the retained error.

### pr-checks-all-cancelled-summary

The fix is a one-condition change in printSummary (pkg/cmd/pr/checks/output.go:71) so the summary and tally line are emitted when only cancelled checks exist, plus a new all-cancelled fixture and TTY test in checks_test.go alongside the existing someCancelled case. Existing exact-output tests already cover every other state mix, so a regression test for the all-cancelled case is the main new verification.

### extension-uninstall-alias

Add `uninstall` as a cobra alias on the existing `remove` command in pkg/cmd/extension/command.go, following the `ls` alias pattern, so both names run the same handler and remove is unchanged. Cover it with a new case in TestNewCmdExtension (the remove cases at command_test.go ~553-613 are the template), and decide whether the help requirement means the ALIASES section of `remove --help` or a separate listing.

### pr-merge-delete-branch-owner-case

The fix is a one-line case-insensitive owner comparison in `crossRepoPR` in pkg/cmd/pr/merge/merge.go, matching the EqualFold convention already used in context/remote.go and internal/ghrepo. The work also needs a new regression test in merge_test.go with an owner-case mismatch, since every existing fixture uses matching case and would not catch a revert.

### pr-view-json-number-on-issue

The fix is to stop the shared PR finder from answering number-only lookups without calling GitHub, so that `pr view --json number` goes through the same `pullRequest(number:)` query as other fields and fails for issue numbers. That change also reaches pr checks and pr diff, which use the same shortcut, so the existing number-only finder test (which pins the buggy no-API path) has to be rewritten and the view JSON path covered with new tests.

### project-item-add-output-non-tty

The task needs item-add's printResults to emit a stable non-TTY confirmation that includes the already-fetched ProjectItem.Id, while leaving TTY output and --format json unchanged, all within item_add.go and item_add_test.go. The main risks are choosing the exact wording and scope (whether sibling TTY-gated project commands should change too) and adding the missing non-TTY test.

### release-create-404-scope-blame

The fix is in `tokenHasWorkflowScope` (`pkg/cmd/release/create/http.go:301-312`), which must trim whitespace from the comma-split `X-Oauth-Scopes` value the way `api/client.go` and `oauth_scopes.go` already do, and it needs a regression test using GitHub's `, `-separated header in `create_test.go`. The harder part is deciding how the hint should coexist with the underlying 404 for tokens that truly lack `workflow`, because the task asks both to keep the hint and to stop hiding the real cause.

### pr-comment-attach-ghu-tokens

In this repository the fix is a deliberate change to the allowlist in internal/attachments/client.go (uploadTokenTypes), which is the only gate on which credentials may reach the upload endpoint, and the existing 'rejects an App user-to-server token' test must be replaced. The silent risk is over-admitting other token kinds or removing the gate, while the existing table tests in client_test.go already cover ghs_/ghr_ rejection and would catch that.

### repo-clone-ghe-ssh-ca-url

Clone must take the SSH URL from the API (`sshUrl`, which needs adding to the GitHubRepo GraphQL query for both the repo and its parent) instead of rebuilding it from the tenant name in clone.go, with HTTPS unchanged and a defined fallback for empty values. Tests in clone_test.go with httpmock and run.Stub should cover tenant SSH for both the origin and upstream remotes. Confidence is medium because the GraphQL sshUrl vs REST ssh_url equivalence and the fallback behaviour are inferred, not verified.

### codespace-ports-forward-concurrent-map

The fix belongs in the codespace port-forwarding path: ForwardPorts runs one goroutine per port, and each goroutine's CreateTunnelPort writes to the TunnelRequestOptions map that the forwarders share through connection.CodespaceConnection, so the change must make per-port tunnel operations safe, either by isolating options per forwarder or by serializing shared-state access as connection.go already does for Connect. A test that forwards several ports at once has to be added, and the offline tunnel mock already supports it, but nothing in the current suite exercises this path.

### issue-view-comments-with-json

The fix belongs in `pkg/cmd/issue/view/view.go`, where `--comments` is dropped on the `--json` path because `lookupFields` is built only from `Exporter.Fields()`, so either `comments` must be added and preloaded with the existing paginated `preloadIssueComments`, or the flags must be rejected with `cmdutil.MutuallyExclusive` as in discussion view. Tests belong in `view_test.go` alongside the existing `--comments` and `TestIssueView_json_*` cases using the `CommentsForIssue` fixtures. The sibling `pr view` has the same silent no-op, which the task does not mention.

### release-verify-sha1-prefix

The fix derives the digest algorithm (sha1 vs sha256) from the ref the API returns, since FetchRefSHA returns only the SHA string, and threads that single value through the attestation lookup, the sigstore digest policy and the printed output in both release verify commands. Tests must cover both 40- and 64-character refs and assert the printed prefix, which no existing test does, and SHA-256 attestation handling is inferred rather than verified against a real fixture.

### auth-refresh-hint-on-expired-token

The fix belongs in the 401 branch of internal/ghcmd/cmd.go: classify the token used for the failing host (from HTTPError.RequestURL) as login-created when ActiveToken's source is keyring or oauth_token, and suggest gh auth refresh only then. It needs tests for that branch, which currently has no coverage and cannot be injected without refactoring Main. The scores rest on code reading, not on running gh, so confidence is medium.

### secret-set-app-agents

Adding agents means extending the shared app enum, GetSecretApp and IsSupportedSecretEntity, plus flag enums and help text in set, list and delete, and most of the path logic already follows the `{app}` pattern. The non-obvious requirement is that the documented agents org endpoint takes integer selected_repository_ids (like Actions), not the string IDs that the Dependabot special case uses, and the new tests must pin repo and org set/list/delete paths and payloads in the existing httpmock style.

### repo-sync-checked-out-worktree

Syncing a branch checked out in another worktree must not leave that worktree's index and files stale, and the fix has to either update it safely (which requires checking that worktree's dirty state) or refuse with a message that names the worktree. The change sits in pkg/cmd/repo/sync (sync.go, git.go, mocks.go, sync_test.go) and needs new worktree-detection and dirty-check test cases, since the existing mock-based suite covers only the current-worktree and plain-ref paths.

### auth-clipboard-config-default

The task needs a new global enabled/disabled config key registered through the existing config Options, default and gh.Config accessor (with regenerated mock and test wiring), and read in `gh auth login` so the device code is copied without `--clipboard` while the flag still works. The main risks are the coordinated plumbing that a partial change would leave broken, and an unresolved scope question about whether `auth refresh` should honour the setting.

### project-item-edit-by-name

The task needs item-edit to resolve a project item from an issue or PR URL, a project from --owner and number, and a field and option (or value) by case-insensitive name, validated before the mutation, while keeping --id, --field-id and --project-id working. The item-from-URL lookup is not in the repo (the GitHub GraphQL schema is external), so its shape is inferred from the existing projectItems usage in pr/shared and issue/shared, and the change must be covered by new offline gock tests in item_edit_test.go.

### skill-update-dir-keeps-install-path

The fix is in pkg/cmd/skills/update/update.go: install into the skill's current parent directory for every scope (with or without --dir) and delete the post-install cleanup block, which means the installer's flat-only write (installer.go:251-253) must not relocate namespaced skills. The existing TestUpdateRun case at update_test.go:711-775 pins the old migrate-and-delete behavior and must be replaced with in-place tests for flat and namespaced layouts, covering both host and --dir paths.

### skill-install-nested-discovery

The reported path foo/bar/skills/<name>/SKILL.md already matches the 'skills' convention at any depth in internal/skills/discovery/discovery.go, so the real work is to confirm which nested case still fails (likely nested hidden-dir skills, which conflicts with the pinned negative test at discovery_test.go L231) before changing matchers and adding nested-skill tests. Scores rest on reading the code and tests, since I did not run the reproduction.
