# How claude + us.anthropic.claude-haiku-5-5 scores each task on the rubric

The rubric pass over `benchmarks/dataset/mcp-gateway-registry-v2.yaml`: each task scored on six dimensions, 0 to 2, 3 independent time(s), in a clone of its repository at the task's pinned ref. No model output was read; this describes the tasks only. Code turns the scores into a required quality and a difficulty bucket (`routing-policy.json`).

- **Stability.** Required quality agreed across repeats on 16/21 tasks; the bucket on 15/21.
- **Runs.** 62 succeeded, 1 failed. Cost $0.8377.
- **Judged.** 2026-10-13T22:51:35.031332Z to 2026-10-13T23:02:26.086741Z.

Columns: HC hidden contract, SI silent invariant, CS coordinated surfaces, AM ambiguity, VE verification, BR blast radius. Each score is the lower median of the repeats.

| Task | HC | SI | CS | AM | VE | BR | Quality | Bucket | Confidence | Repeats agree |
|---|---:|---:|---:|---:|---:|---:|---:|---|---|---|
| default-create-in-idp-checkbox-unchecked | 2 | 1 | 2 | 2 | 1 | 1 | **70** | very_hard | medium | yes |
| build-docker-images-from-uv-lock | 1 | 2 | 2 | 2 | 2 | 2 | **80** | very_hard | medium | quality [70.0, 80.0, 80.0]; buckets {'very_hard': 3} |
| honor-cloud-provider-override-in-ui | 1 | 1 | 1 | 1 | 1 | 1 | **70** | hard | high | quality [70.0, 70.0, 75.0]; buckets {'hard': 3} |
| fix-reserved-groups-var-in-service-account-script | 1 | 1 | 1 | 2 | 2 | 1 | **75** | hard | medium | quality [75.0, 75.0, 75.0]; buckets {'hard': 1, 'very_hard': 2} |
| cli-custom-egress-oauth-provider-flags | 1 | 2 | 1 | 2 | 2 | 1 | **75** | very_hard | high | quality [70.0, 75.0, 80.0]; buckets {'hard': 1, 'very_hard': 2} |
| derive-repo-url-from-skill-md | 1 | 1 | 2 | 1 | 1 | 1 | **70** | hard | medium | quality [70.0, 70.0, 75.0]; buckets {'hard': 2, 'very_hard': 1} |
| consistent-csrf-across-toggle-endpoints | 1 | 2 | 2 | 2 | 2 | 2 | **80** | very_hard | medium | yes |
| configurable-ui-title | 1 | 1 | 2 | 1 | 1 | 1 | **70** | hard | medium | yes |
| configurable-mcp-proxy-upstream-timeout | 1 | 1 | 2 | 2 | 1 | 1 | **70** | very_hard | medium | quality [70.0, 70.0, 70.0]; buckets {'very_hard': 2, 'hard': 1} |
| nginx-location-trailing-slash-route-hijack | 1 | 2 | 1 | 2 | 1 | 2 | **75** | very_hard | medium | yes |
| registration-admission-control-gate | 1 | 2 | 2 | 2 | 1 | 2 | **75** | very_hard | medium | yes |
| server-side-oauth-token-storage | 2 | 2 | 2 | 2 | 1 | 2 | **75** | very_hard | high | yes |
| lifecycle-workflow-webhooks | 2 | 2 | 2 | 2 | 1 | 2 | **75** | very_hard | medium | yes |
| per-caller-per-target-rate-limits-and-quarantine | 2 | 2 | 2 | 2 | 1 | 2 | **75** | very_hard | high | yes |
| idp-authenticated-embedding-endpoint | 1 | 2 | 2 | 2 | 1 | 2 | **75** | very_hard | medium | yes |
| index-demo-videos-in-one-page | 1 | 0 | 1 | 2 | 2 | 1 | **75** | hard | medium | quality [75.0, 75.0, 75.0]; buckets {'moderate': 1, 'hard': 2} |
| hide-register-button-on-virtual-and-skills-tabs | 1 | 0 | 0 | 1 | 2 | 1 | **75** | moderate | medium | yes |
| pass-ssrf-allowlist-env-to-registry-container | 1 | 2 | 2 | 2 | 2 | 1 | **75** | very_hard | high | quality [75.0, 75.0, 80.0]; buckets {'very_hard': 3} |
| macos-setup-python-version-precheck | 1 | 1 | 1 | 2 | 2 | 1 | **75** | hard | medium | yes |
| portable-env-secret-generation-in-build-script | 1 | 2 | 1 | 1 | 2 | 2 | **80** | hard | medium | quality [80.0, 80.0, 80.0]; buckets {'hard': 2, 'very_hard': 1} |
| logout-id-token-hint-out-of-browser-url | 2 | 2 | 2 | 2 | 2 | 2 | **80** | very_hard | medium | yes |

## What each task needs

### default-create-in-idp-checkbox-unchecked

In this repository the task is not only a React default: the create-in-IdP default is set to true on the frontend (IAMGroups.tsx:341) and in several REST endpoints (management_routes.py:422, server_routes.py:2248, 3389, 3464, 3800), and the documentation and a backend unit test pin that behaviour. The change has to flip every layer consistently, update the pinned backend test, and add the first frontend test for the checkbox's initial state.

### build-docker-images-from-uv-lock

The task needs uv.lock files for auth_server and three servers, Dockerfiles that install from the lock without changing what ships (especially CPU-only torch in the registry and cpu MCP images), and a CI `uv lock --check` per project root. The work spans Dockerfiles, lock files, CI workflows and the build tooling that publishes public images, and nothing in the current tests or CI would catch a silently wrong lock. Confidence is medium because I could not run `uv lock --check` or a Docker build here, so the torch-resolution behaviour is inferred from the Dockerfiles.

### honor-cloud-provider-override-in-ui

The fix is to have /api/system/telemetry-detection (registry/api/system_routes.py:333-354) call the existing async _resolve_cloud() resolver instead of the raw _detect_cloud_provider_with_method(), so the UI matches the telemetry events. It needs a regression test for override-set and override-unset in tests/unit/test_stats_endpoint.py, plus an update to the endpoint docstring's list of cloud values.

### fix-reserved-groups-var-in-service-account-script

The task needs a fix to verify_setup() in keycloak/setup/setup-agent-service-account.sh so that it stops assigning to the reserved GROUPS variable, prints its output, and checks exact group names, which means updating the same bug in setup-m2m-service-account.sh, cli/user_mgmt.sh and terraform/aws-ecs/scripts/user_mgmt.sh. Nothing in the repository's tests or pre-commit hooks would catch a regression here, and the docs and macos-setup skill depend on the exit code. Confidence is medium because the bash GROUPS behaviour comes from the task text and I did not run bash to confirm it.

### cli-custom-egress-oauth-provider-flags

The change adds five custom-provider flags to the egress-configure CLI and forwards them through configure_egress_auth in api/registry_client.py, with the auth-style flag restricted to post_body and basic_header from the server enum. The hard part is that the server's edit route rebuilds egress_oauth from the request body, so a client-only "send what was supplied" fix would not stop stored custom values from being silently reset, and nothing in the repo tests the CLI or client path today.

### derive-repo-url-from-skill-md

In this repository the task needs a pure GitHub URL-to-repo-root derivation shared between the backend parse endpoint (skill_service.py and skill_routes.py, following the enterprise host convention in url_utils.py) and the frontend parse handler, plus a Skill type field and two modal link changes in SkillCard.tsx and SemanticSearchResults.tsx. The main risk is that no existing test covers the parse response, the derivation, or the modal links, so a mistake would ship unnoticed even though the blast radius is a wrong or missing link.

### consistent-csrf-across-toggle-endpoints

The task needs one CSRF rule applied to every toggle route that distinguishes cookie-authenticated browser requests (must validate the token against the session cookie) from bearer requests that nginx_proxied_auth authenticates via X-User headers (no cookie, must not be blocked), while keeping the auth dependency and the frontend's X-CSRF-Token behaviour consistent across server, agent, skill and virtual-server routes. The current tests override the CSRF dependency everywhere, so the new browser and bearer paths need dedicated tests against the real dependency.

### configurable-ui-title

The work is a cross-cutting configuration addition: a UI_TITLE setting with a DEPLOYMENT_MODE-based fallback, served from the unauthenticated /api/config, consumed by the frontend title components, shown in the System Config admin panel, and plumbed through Docker, Terraform and Helm. The main risks are missing one of the many surfaces and the 'unset means no change' requirement, since the repo has almost no automated coverage for this plumbing.

### configurable-mcp-proxy-upstream-timeout

The task needs a configurable MCP_PROXY_* upstream timeout for the auth-server /mcp-proxy hop, wired through the same settings, admin, compose, Terraform, Helm and docs surfaces as MAX_BODY_BYTES, with a 30s default and a floor. Because nginx's generated /mcp-proxy location also sets proxy_read_timeout 30s (registry/core/nginx_service.py:477), the change is only effective if that timeout is made consistent too, and no existing test covers the 504 branch or the nginx timeout.

### nginx-location-trailing-slash-route-hijack

The task needs the nginx location generator in registry/core/nginx_service.py to emit a trailing-slash prefix (or equivalent) so a server at /name owns only /name/... while /name/mcp and /name/sse keep working and the bare /name path has a deliberate outcome. It must do this without leaving any route unauthenticated, and existing deployments pick up the change through the startup config regeneration, which the current unit tests check only as rendered strings.

### registration-admission-control-gate

The task needs a feature-flagged, fail-closed admission gate wired into every registration and update path (agent register/update, server register including /internal/register, skill create/update) and configured through Settings and the Docker Compose, Helm and Terraform surfaces. The hard part is scope: the listed routes are not the only writers, since federation, peer sync, AgentCore sync, startup and health updates also persist, so the repo does not settle whether those must be gated.

### server-side-oauth-token-storage

In this repository the task needs a new encrypted, user-scoped MongoDB token store with a TTL index, wired through the auth-server OAuth callback, the registry cookie dependency, a new authorized retrieval endpoint, and every deployment surface that already carries OAUTH_STORE_TOKENS_IN_SESSION. It must reconcile with the earlier decision (#490/#528) that IdP tokens are not stored, and with the existing self-signed "Get JWT Token" path, which already works for OAuth users, so the stated premise needs checking before design.

### lifecycle-workflow-webhooks

The task adds a signed scan_complete webhook, a mandated initial status, a status filter, and a separate lifecycle-status permission to the server, agent, and skill registration paths. In this repo that means changing the fire-and-forget sender in webhook_service.py, the scan-on-registration routines, the three PATCH handlers, and the scopes and deployment config, while keeping the existing webhook consumer contract intact. The main risks are signing the wrong bytes, skipping the failure path, and leaving the status-gated permission half-applied, and none of these is covered by tests today.

### per-caller-per-target-rate-limits-and-quarantine

This task adds a per-(caller, target) counter axis and an undeletable, auto-seeded quarantine group to the single /validate enforcement hook, and it must settle the quarantine response, admin-bypass and fail-mode semantics that docs/design/rate-limiting.md already constrains. It is security-sensitive, spans the limiter, the memberships and definitions repositories, the admin routes, CLI and UI, and needs new tests because the existing suite does not exercise the new axis or quarantine.

### idp-authenticated-embedding-endpoint

In this repository the task means adding an opt-in OAuth2 client-credentials token manager beside the existing LiteLLM path (registry/embeddings/client.py, registry/core/config.py), with a per-call bearer, masked client-secret handling in config_routes.py, and fail-fast validation, all of which must be wired through docker-compose, docker/registry-entrypoint.sh, the Terraform aws-ecs module and infra/ CDK, and docs/unified-parameter-reference.md. The mirrored FederationAuthManager uses a bare httpx client and returns None on failure, so a literal copy would conflict with the SSRF, no-log and fail-closed invariants in CLAUDE.md; Helm has no embedding wiring at all despite what the reference doc says, so that surface is new work.

### index-demo-videos-in-one-page

The work is to scan all markdown for demo-video links (about 25 occurrences across README.md, docs/ and release-notes/, with 9 distinct videos beyond the README bar) and index them in a new docs/demo-videos.md, linked prominently from the README. The main risk is a list that copies only the README bar and misses deep-page videos, along with an unresolved conflict between two Dynamic Tool Discovery asset IDs and no automated check for completeness.

### hide-register-button-on-virtual-and-skills-tabs

The change is a one-line render-condition narrowing in frontend/src/pages/Dashboard.tsx, where the header Register button at lines 2410-2416 currently shows on every non-discover tab. The main judgement is which tabs keep the button, since the Agents and External tabs also lead to the server registration form, and nothing in the repository covers Dashboard.tsx, so the change would ship unverified unless a test is added.

### pass-ssrf-allowlist-env-to-registry-container

Wire SSRF_ALLOWED_HOSTS and SSRF_ALLOWED_CIDRS into the registry service's environment in docker-compose.podman.yml and docker-compose.prebuilt.yml, matching docker-compose.yml:206-207 and the Helm and Terraform wiring, with empty defaults so the guard stays default-deny. The repo already has a static compose test module and no test for this variable, so a test asserting the pair in each registry block is needed for verification.

### macos-setup-python-version-precheck

The task needs the macos-setup skill's Phase 1 bash check to read requires-python from pyproject.toml, fail with a message naming that requirement, and keep the brew/uv remediation reachable, with the matching guide text in docs/macos-setup-guide.md kept in step. The main open point is that Phase 1 runs before the repository is cloned, so the metadata is not local at that step, and no existing test covers the skill, so correctness rests on manual verification.

### portable-env-secret-generation-in-build-script

This task is a single-file fix in build_and_run.sh: replace the BSD-incompatible `sed -i '<expr>' .env` calls at the five generated-secret blocks and the METRICS_API_KEY loop with a portable edit that fails loudly, and that keeps operator-provided values intact. Confidence is medium because the hidden-contract and blast-radius scores rest on inference from comments and compose files, and no test or CI job in the repo exercises this path.

### logout-id-token-hint-out-of-browser-url

The task needs the registry and auth server to hand the id_token to the IdP-facing logout step without placing it in any browser-facing URL, while keeping RP-initiated logout working and falling back cleanly for deployments without the new path. That spans logout_handler, oauth2_logout, the session store, and the nginx routes, and no existing test covers the logout endpoints, so the work is security-sensitive with weak automated verification.
