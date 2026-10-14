# How omp + us.anthropic.claude-opus-5-5 scores each task on the rubric

The rubric pass over `benchmarks/dataset/cli-cli-v1.yaml`: each task scored on six dimensions, 0 to 2, 3 independent time(s), in a clone of its repository at the task's pinned ref. No model output was read; this describes the tasks only. Code turns the scores into a required quality and a difficulty bucket (`routing-policy.json`).

- **Stability.** Required quality agreed across repeats on 18/21 tasks; the bucket on 20/21.
- **Runs.** 63 succeeded, 0 failed. Cost $15.5931.
- **Judged.** 2026-10-14T22:10:12.033833Z to 2026-10-14T22:23:36.365453Z.

Columns: HC hidden contract, SI silent invariant, CS coordinated surfaces, AM ambiguity, VE verification, BR blast radius. Each score is the lower median of the repeats.

| Task | HC | SI | CS | AM | VE | BR | Quality | Bucket | Confidence | Repeats agree |
|---|---:|---:|---:|---:|---:|---:|---:|---|---|---|
| repo-create-reject-empty-name | 1 | 1 | 0 | 1 | 1 | 1 | **70** | moderate | high | yes |
| copilot-not-installed-trailing-newline | 0 | 0 | 0 | 0 | 1 | 1 | **70** | easy | high | yes |
| repo-set-default-unset-without-repo | 1 | 0 | 0 | 1 | 1 | 1 | **70** | moderate | high | yes |
| pr-checks-all-cancelled-summary | 1 | 0 | 0 | 0 | 1 | 1 | **70** | easy | high | yes |
| extension-uninstall-alias | 1 | 0 | 0 | 1 | 1 | 1 | **70** | moderate | high | yes |
| pr-merge-delete-branch-owner-case | 1 | 1 | 0 | 1 | 1 | 1 | **70** | moderate | high | quality [70.0, 70.0, 70.0]; buckets {'hard': 1, 'moderate': 2} |
| pr-view-json-number-on-issue | 1 | 1 | 1 | 1 | 1 | 1 | **70** | hard | medium | yes |
| project-item-add-output-non-tty | 1 | 0 | 0 | 1 | 1 | 1 | **70** | moderate | high | yes |
| release-create-404-scope-blame | 1 | 1 | 0 | 1 | 1 | 1 | **70** | moderate | high | yes |
| pr-comment-attach-ghu-tokens | 1 | 1 | 0 | 1 | 0 | 1 | **70** | moderate | medium | yes |
| repo-clone-ghe-ssh-ca-url | 1 | 1 | 1 | 1 | 1 | 1 | **70** | hard | medium | yes |
| codespace-ports-forward-concurrent-map | 1 | 2 | 1 | 2 | 1 | 1 | **70** | very_hard | medium | yes |
| issue-view-comments-with-json | 1 | 1 | 1 | 1 | 1 | 1 | **70** | hard | high | yes |
| release-verify-sha1-prefix | 1 | 1 | 1 | 1 | 1 | 1 | **70** | hard | medium | quality [70.0, 70.0, 75.0]; buckets {'hard': 3} |
| auth-refresh-hint-on-expired-token | 1 | 1 | 1 | 2 | 2 | 1 | **75** | hard | medium | yes |
| secret-set-app-agents | 2 | 1 | 1 | 1 | 1 | 1 | **70** | hard | medium | yes |
| repo-sync-checked-out-worktree | 1 | 2 | 1 | 1 | 1 | 1 | **70** | hard | medium | quality [70.0, 70.0, 75.0]; buckets {'hard': 3} |
| auth-clipboard-config-default | 1 | 1 | 1 | 1 | 1 | 1 | **70** | hard | high | yes |
| project-item-edit-by-name | 1 | 1 | 1 | 1 | 1 | 1 | **70** | hard | medium | yes |
| skill-update-dir-keeps-install-path | 1 | 2 | 1 | 1 | 1 | 1 | **70** | hard | medium | quality [70.0, 70.0, 75.0]; buckets {'hard': 3} |
| skill-install-nested-discovery | 1 | 2 | 1 | 2 | 1 | 1 | **70** | very_hard | medium | yes |

## What each task needs

### repo-create-reject-empty-name

Add an empty (and likely whitespace-only) name check in `interactiveRepoNameAndOwner` in `pkg/cmd/repo/create/create.go`, right after the "Repository name" Input and before the owner lookup and Select. It should return an error in the repo's "cannot be blank" style so the from-scratch, template and local flows all stop early. Add `create_test.go` table cases with an empty name that assert the error and that no later prompts or API calls happen, and keep the existing valid-name tests passing.

### copilot-not-installed-trailing-newline

Add a trailing newline to the 'Copilot CLI was not installed' warning in runCopilot (pkg/cmd/copilot/copilot.go:155), keeping the SilentError return. Add a runCopilot test that stubs findCopilotBinaryFunc to return "", makes the prompter decline with a TTY iostreams, and asserts the exact stderr output.

### repo-set-default-unset-without-repo

Relax the non-interactive 'repository required' guard in NewCmdSetDefault (pkg/cmd/repo/setdefault/setdefault.go) so that `--unset`, like `--view`, runs without a repository argument when stdin is not a terminal, while plain `gh repo set-default` keeps the existing FlagError. Extend TestNewCmdSetDefault with a TTY toggle and cases for non-TTY `--unset`, non-TTY `--view` and the non-TTY no-argument error that must stay.

### pr-checks-all-cancelled-summary

The fix is to add counts.Canceled to the guard in printSummary (pkg/cmd/pr/checks/output.go) so that all-cancelled PRs reach the existing 'Some checks were cancelled' branch and its tally line. It needs a new all-cancelled fixture and a test row in checks_test.go that asserts the full summary output.

### extension-uninstall-alias

Add `uninstall` as a cobra alias on the existing `remove` subcommand in pkg/cmd/extension/command.go, following the `list`/`ls` pattern, so routing and the ALIASES help section come for free. Add a table-driven case to pkg/cmd/extension/command_test.go that runs `uninstall` and checks that Remove is called with the normalized name.

### pr-merge-delete-branch-owner-case

The crossRepoPR computation in pkg/cmd/pr/merge/merge.go:592 must compare the PR head owner login with the base repo owner case-insensitively (matching ghrepo.IsSame/FindByRepo), so same-repo PRs get their remote branch deleted. A merge_test.go regression test must cover an owner-case mismatch and expect the DELETE git/refs call, while fork PRs keep their branches.

### pr-view-json-number-on-issue

The shared PR finder (pkg/cmd/pr/shared/finder.go) returns a synthetic PullRequest without any API call when only 'number' is requested, so gh pr view N --json number succeeds for issue numbers. The fix must make that path check with GitHub, either in the finder (which also changes pr diff and pr checks) or in pr view, and must update the finder test that pins the shortcut and add an issue-number case that expects an error.

### project-item-add-output-non-tty

Change `printResults` in `pkg/cmd/project/item-add/item_add.go` so that non-TTY stdout gets a short, stable confirmation (preferably the added item's ID from the mutation response), leaving the TTY "Added item" message and the `--format json` exporter path unchanged. Add a non-TTY test next to the existing TTY and JSON tests in `item_add_test.go`.

### release-create-404-scope-blame

tokenHasWorkflowScope in pkg/cmd/release/create/http.go splits X-Oauth-Scopes on "," without trimming whitespace, so real "a, b, workflow" headers never match "workflow" and every 404 is replaced by the scope hint. The fix is to trim each scope, following HeaderHasMinimumScopes in auth/shared, and to add create_test.go cases that use the real comma-space header format for tokens with and without workflow, keeping the existing empty-header rule.

### pr-comment-attach-ghu-tokens

Add gh.TokenTypeUserToServer to uploadTokenTypes in internal/attachments/client.go, keeping ghs_/ghr_/unknown rejected and the host check first. Flip the 'rejects an App user-to-server token' row in TestNewUploader and add a command-level test with a ghu_ token that uploads, plus a check that a server refusal comes back to the user.

### repo-clone-ghe-ssh-ca-url

Add sshUrl to the RepositoryInfo fragment in api.GitHubRepo for the repository and its parent, and have cloneRun use the API SSH URL for both the clone and the fork upstream remote when the protocol is ssh, including the URL-argument and wiki paths, while leaving HTTPS unchanged. Add clone_test.go cases with mocked sshUrl responses that check the git clone and remote add commands.

### codespace-ports-forward-concurrent-map

ForwardPorts runs one goroutine per port, and all of them share a single CodespaceConnection whose TunnelRequestOptions.AdditionalHeaders map and Tunnel.Ports are changed by dev-tunnels Manager calls, so the fix needs synchronization (or per-call copies) at the shared connection or in ForwardPorts, not inside each per-goroutine forwarder. It also needs a new test that forwards several ports at once against the existing mock tunnels server, which CI runs under -race.

### issue-view-comments-with-json

In `pkg/cmd/issue/view/view.go`, `--comments` combined with `--json` must either add `comments` to the exporter's field list (so the comments are fetched and written) or fail with a mutually-exclusive flag error after PreRunE has set up the Exporter. `--json` alone and `--comments` alone must behave as they do today. New table tests in `view_test.go` should cover the combination using the existing httpmock fixtures.

### release-verify-sha1-prefix

Replace the hard-coded "sha1" passed to `artifact.NewDigestedArtifactForRelease` in both `verify.go` and `verify_asset.go` with an algorithm worked out from the ref returned by `shared.FetchRefSHA` (40 hex characters means sha1, 64 means sha256), ideally through one shared helper. The output text, the `GetByDigest` lookup and the sigstore digest policy all need the same algorithm, with tests covering both SHA-1 and SHA-256 refs in both commands.

### auth-refresh-hint-on-expired-token

In internal/ghcmd/cmd.go, the 401 branch should print `gh auth refresh` (probably with `-h <host>`) only when the active token for the host of the failed request was stored by gh and is an OAuth token. That is the oauth_token/keyring source plus gho_ prefix rule from agent_task.go; every other token keeps `gh auth login`. New tests are needed because nothing covers this branch today, and they should cover the tricky cases (a `--with-token` PAT, a gho_ token from an env var, a non-default host), not just the obvious pair.

### secret-set-app-agents

Add an `agents` App to pkg/cmd/secret/shared with GetSecretApp and IsSupportedSecretEntity support (repository and organization), add it to the `--app` enum in set, list and delete, choose the right org PUT payload in set/http.go, and update help text. Add httpmock-based tests for repo and org set, list and delete whose paths and payloads must match GitHub's documented agents secrets REST endpoints.

### repo-sync-checked-out-worktree

`executeLocalRepoSync` needs to find out whether the target branch is checked out in any other worktree, for example through a new gitClient/git.Client method that parses `git worktree list --porcelain`. If it is, sync must refuse with a message naming that worktree's path, or update it safely, instead of moving the ref with `update-ref`. That means changing the gitClient interface, the executer, mocks.go and the table tests in sync_test.go, while syncing a branch nobody has checked out keeps working as before.

### auth-clipboard-config-default

Add a `clipboard` enabled/disabled setting following the spinner/prefer_editor_prompt pattern: the gh.Config interface method, regenerated mock, const, accessor, default config string, Options entry, test stub and the config list test expectation. Then have `gh auth login` copy the code when either `--clipboard` is passed or the setting is enabled, with tests covering how flag and config combine.

### project-item-edit-by-name

Add an opt-in name form to `gh project item-edit` (`<number> --owner --url --field --value`). It must resolve the project, the content-to-item mapping, the field (case-insensitive) and the option or typed value before calling the existing `updateProjectV2ItemFieldValue` mutation, and fail with a list of candidates when a name does not match. It must also keep the ID-flag paths unchanged and add gock-mocked tests in `item_edit_test.go`, probably along with a new lookup helper in `shared/queries`.

### skill-update-dir-keeps-install-path

In pkg/cmd/skills/update/update.go, the update must reinstall each skill into the parent of its current directory for flat and namespaced layouts, whether or not an agent host is involved, and the RemoveAll/parent-cleanup block must go. update_test.go needs its namespaced test turned around and new cases showing the original path is kept and updated in place.

### skill-install-nested-discovery

The core repro (foo/bar/skills/<name>/SKILL.md) already matches in internal/skills/discovery/discovery.go and has tests. The real work is to decide whether nested skills under hidden or plugins directories should be discovered when --allow-hidden-dirs is set, and to extend the shared matcher (used by remote, local, preview, search and path-based install) without breaking today's conventions or the hidden-dir gate. Nested-skill tests are needed across discovery and install.
