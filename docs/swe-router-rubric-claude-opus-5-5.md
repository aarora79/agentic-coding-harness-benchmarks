# How claude + us.anthropic.claude-opus-5-5 scores each task on the rubric

The rubric pass over `benchmarks/dataset/mcp-gateway-registry-v2.yaml`: each task scored on six dimensions, 0 to 2, 3 independent time(s), in a clone of its repository at the task's pinned ref. No model output was read; this describes the tasks only. Code turns the scores into a required quality and a difficulty bucket (`routing-policy.json`).

- **Stability.** Required quality agreed across repeats on 14/21 tasks; the bucket on 19/21.
- **Runs.** 63 succeeded, 0 failed. Cost $20.2262.
- **Judged.** 2026-10-13T22:51:35.022467Z to 2026-10-13T23:03:07.306856Z.

Columns: HC hidden contract, SI silent invariant, CS coordinated surfaces, AM ambiguity, VE verification, BR blast radius. Each score is the lower median of the repeats.

| Task | HC | SI | CS | AM | VE | BR | Quality | Bucket | Confidence | Repeats agree |
|---|---:|---:|---:|---:|---:|---:|---:|---|---|---|
| default-create-in-idp-checkbox-unchecked | 1 | 1 | 2 | 1 | 1 | 1 | **70** | hard | medium | quality [70.0, 70.0, 70.0]; buckets {'hard': 2, 'very_hard': 1} |
| build-docker-images-from-uv-lock | 1 | 1 | 2 | 2 | 2 | 1 | **75** | very_hard | medium | quality [70.0, 75.0, 75.0]; buckets {'very_hard': 3} |
| honor-cloud-provider-override-in-ui | 1 | 1 | 0 | 1 | 1 | 1 | **70** | moderate | high | quality [70.0, 70.0, 70.0]; buckets {'hard': 1, 'moderate': 2} |
| fix-reserved-groups-var-in-service-account-script | 1 | 1 | 1 | 1 | 2 | 1 | **75** | hard | high | yes |
| cli-custom-egress-oauth-provider-flags | 1 | 1 | 1 | 1 | 2 | 1 | **75** | hard | high | quality [70.0, 75.0, 75.0]; buckets {'hard': 3} |
| derive-repo-url-from-skill-md | 1 | 1 | 2 | 1 | 1 | 1 | **70** | hard | high | quality [70.0, 70.0, 75.0]; buckets {'hard': 3} |
| consistent-csrf-across-toggle-endpoints | 1 | 2 | 1 | 2 | 2 | 2 | **80** | very_hard | medium | quality [75.0, 80.0, 80.0]; buckets {'very_hard': 3} |
| configurable-ui-title | 1 | 1 | 2 | 1 | 1 | 1 | **70** | hard | medium | yes |
| configurable-mcp-proxy-upstream-timeout | 1 | 1 | 2 | 1 | 1 | 1 | **70** | hard | medium | yes |
| nginx-location-trailing-slash-route-hijack | 2 | 2 | 2 | 2 | 1 | 2 | **75** | very_hard | medium | yes |
| registration-admission-control-gate | 1 | 2 | 2 | 2 | 2 | 2 | **80** | very_hard | medium | quality [75.0, 80.0, 80.0]; buckets {'very_hard': 3} |
| server-side-oauth-token-storage | 2 | 2 | 2 | 2 | 1 | 2 | **75** | very_hard | high | yes |
| lifecycle-workflow-webhooks | 2 | 2 | 2 | 2 | 1 | 2 | **75** | very_hard | medium | yes |
| per-caller-per-target-rate-limits-and-quarantine | 2 | 2 | 2 | 2 | 1 | 2 | **75** | very_hard | high | yes |
| idp-authenticated-embedding-endpoint | 2 | 2 | 2 | 1 | 1 | 2 | **75** | very_hard | medium | yes |
| index-demo-videos-in-one-page | 1 | 1 | 1 | 1 | 2 | 1 | **75** | hard | high | quality [65.0, 75.0, 75.0]; buckets {'hard': 3} |
| hide-register-button-on-virtual-and-skills-tabs | 1 | 0 | 0 | 1 | 2 | 1 | **75** | moderate | high | yes |
| pass-ssrf-allowlist-env-to-registry-container | 1 | 2 | 1 | 1 | 2 | 2 | **80** | hard | high | yes |
| macos-setup-python-version-precheck | 1 | 1 | 1 | 2 | 2 | 1 | **75** | hard | medium | yes |
| portable-env-secret-generation-in-build-script | 1 | 2 | 1 | 1 | 2 | 2 | **80** | hard | medium | quality [75.0, 80.0, 80.0]; buckets {'hard': 3} |
| logout-id-token-hint-out-of-browser-url | 2 | 2 | 2 | 2 | 2 | 2 | **80** | very_hard | high | yes |

## What each task needs

### default-create-in-idp-checkbox-unchecked

Flip the create_in_idp default to false everywhere in IAMGroups.tsx (the initial state, both reset paths and the JSON template) and in the backend default in management_routes.py, then update the backend test that pins the old default. Add a new Jest/RTL test that asserts the checkbox starts unchecked, while ticking it still sends create_in_idp=true.

### build-docker-images-from-uv-lock

The task needs uv.lock files generated for auth_server and three servers/* projects, every Dockerfile that installs a Python project (auth, registry and the mcp-server variants) switched to frozen or locked `uv sync`, and a CI job that runs `uv lock --check` in each root. It must also keep the CPU-only torch index, torchvision, the absence of dev dependencies and the editable install working, so the images behave exactly as before.

### honor-cloud-provider-override-in-ui

Change /api/system/telemetry-detection in registry/api/system_routes.py to await telemetry._resolve_cloud(), the function telemetry events use (env override, then operator hint, then auto-detection), instead of the raw _detect_cloud_provider_with_method(). Then add endpoint tests showing that MCP_CLOUD_PROVIDER wins when set and that auto-detection is used when it is unset.

### fix-reserved-groups-var-in-service-account-script

verify_setup() assigns to the reserved bash variable GROUPS, which kills an otherwise successful run under set -e. The fix renames that variable (e.g. SA_GROUPS), checks membership with an exact match against the real group names, and applies the same fix to setup-m2m-service-account.sh:235, which the sweep turns up. Nothing in the repo tests these scripts, so only shellcheck or a live Keycloak run can confirm the fix.

### cli-custom-egress-oauth-provider-flags

Add --custom-authorize-url, --custom-token-url, --custom-scope-separator, --custom-token-auth-style (choices post_body/basic_header) and --custom-resource to the egress-configure parser, pass them through cmd_egress_configure, and add matching optional parameters to RegistryClient.configure_egress_auth that are only put in the POST body when supplied. Add unit tests covering argparse parsing and body construction that fail on the current tree.

### derive-repo-url-from-skill-md

The backend /parse-skill-md route must derive and return repository_url from GitHub blob and raw SKILL.md URLs, including Enterprise hosts and the raw.<host> rule in url_utils.py, and return nothing for non-GitHub hosts. The frontend must use that value to pre-fill the editable Dashboard field and replace 'View on GitHub' with 'View Skill' and 'View Repo' in both the SkillCard and SemanticSearchResults modals, with repository_url added to the Skill type.

### consistent-csrf-across-toggle-endpoints

The task needs one CSRF policy, probably in registry/auth/csrf.py, applied to all four toggle routes (server, agent, skill, virtual-server). It must exempt only genuine bearer-token requests that carry no session cookie and still require a valid X-CSRF-Token for any cookie-bearing browser request. It also needs new tests that run the real dependency for the browser path and the bearer path, instead of overriding it as the current tests do.

### configurable-ui-title

Add an optional UI_TITLE setting with a DEPLOYMENT_MODE-based fallback, return it from /api/config and the System Config panel, and replace the hardcoded titles in the React components with the runtime value. Plumb it through .env.example, every compose file, the Terraform root and module variables, the ECS task definition and tfvars example, and the Helm values, deployment template and stack values, keeping the registry chart's reserved-env list and extraEnv index tests in sync.

### configurable-mcp-proxy-upstream-timeout

The task replaces the hardcoded 30s httpx timeout in the auth-server /mcp-proxy hop with a settings field plus an MCP_PROXY_* env fallback, modelled on _read_mcp_proxy_max_body_bytes, with a floor, a 30s default and an entry in the admin config surface. The main work is carrying the new knob consistently through docker-compose (three files), .env.example, the Helm values, secret and reserved-env list (with unittests), Terraform root and module variables plus ECS env (and the CDK equivalent), and the parameter reference doc.

### nginx-location-trailing-slash-route-hijack

The generated nginx locations in nginx_service.py (MCP server blocks and the identical virtual-server block) need to become slash-bounded. Paths already stored with a trailing slash must not end up with '//', bare /name needs explicit exact-match or redirect handling, and config must be regenerated on existing deployments, with /name/mcp and /name/sse still working. The change also needs tests that assert the exact location string and the prefix-collision case, which the current substring tests do not.

### registration-admission-control-gate

Add a configurable, fail-closed admission webhook that runs before persistence on every agent, server and skill create and update path, including both duplicate internal server routes, and send an endpoint identifier in the payload. Wire the settings through config.py, .env, docker-compose, Helm and Terraform, write the docs, and add mocked tests for allow, deny, timeout and unreachable gate.

### server-side-oauth-token-storage

The task needs an encrypted, user-scoped, TTL-indexed MongoDB token store, used by the auth_server OAuth callback, that leaves only an opaque reference in the shared mcp_gateway_session cookie, plus an authorized retrieval endpoint feeding the frontend's Get JWT Token page. It also needs key configuration in compose, Helm and Terraform and new tests for the expired and revoked cases, all without adding a database read to cookie validation or breaking the registry's existing cookie parsing.

### lifecycle-workflow-webhooks

The task adds a signed scan_complete webhook, HMAC signing of every async webhook, a status filter, a flag mandating the initial status, and a separate lifecycle-status permission, across the server, agent and skill routes, the webhook service, config and the auth-server scopes. It also has to wire the new settings through compose, Helm (reserved env names) and Terraform, and add a metric and consumer docs.

### per-caller-per-target-rate-limits-and-quarantine

The task adds a caller_target axis keyed on a composite caller and target subject, plus reserved, auto-seeded, undeletable caller and target quarantine groups evaluated as an early deny inside the existing limiter at the auth server's /validate hook. It needs deliberate, documented choices on the deny status code, admin bypass and store-failure behaviour, and must reach the models, limiter, admin API, CLI, React UI and docs consistently.

### idp-authenticated-embedding-endpoint

Add an opt-in, thread-safe OAuth2 client-credentials token manager, modelled on federation_auth.py, that supplies a fresh bearer to each LiteLLM embedding call without touching global env vars. It needs fail-fast validation, secret masking and redaction, and new settings wired through Docker, Terraform/CDK, Helm (with reserved-name lists and unittests) and the parameter reference doc, with every existing provider behaving exactly as today when the settings are unset.

### index-demo-videos-in-one-page

The task needs a full scan of README.md, docs/ (including docs/design) and possibly release-notes/ for GitHub user-attachment, YouTube and Vidcast video URLs, both labelled links and bare embeds. The results go into a deduplicated, grouped docs/demo-videos.md, linked prominently from the README and ideally added to the mkdocs.yml nav.

### hide-register-button-on-virtual-and-skills-tabs

The header Register button in frontend/src/pages/Dashboard.tsx shows on every tab except 'discover', because of the condition at line 2378. That condition needs to be narrowed so the button appears only where server/agent registration applies (servers and agents, with a decision on 'external'). The search bar and Refresh button in the same wrapper must stay as they are, and the registration flow must not change.

### pass-ssrf-allowlist-env-to-registry-container

Add `SSRF_ALLOWED_HOSTS=${SSRF_ALLOWED_HOSTS:-}` and `SSRF_ALLOWED_CIDRS=${SSRF_ALLOWED_CIDRS:-}` to the registry service in docker-compose.podman.yml and docker-compose.prebuilt.yml, matching the entries already in docker-compose.yml. Keep the empty default so the guard still denies internal hosts unless the operator lists them.

### macos-setup-python-version-precheck

Phase 1 of .claude/skills/macos-setup/SKILL.md must read the minimum Python version from the project's pyproject.toml, even though the repo is not cloned until Phase 2. It must compare that version numerically against `python3` and fail early with a message naming the requirement, keeping the PYTHON_FAIL remediation row and the gating text consistent.

### portable-env-secret-generation-in-build-script

Replace every BSD-incompatible `sed -i` placeholder strip in build_and_run.sh's secret blocks and its metrics-token loop with one portable helper (for example a temp file plus mv) that stops the script when the edit fails, without touching values operators set themselves. Correctness turns on .env first-assignment-wins semantics and on keeping secrets that are already set, and no test or Linux CI run would catch a regression on BSD.

### logout-id-token-hint-out-of-browser-url

The registry's logout must stop putting the encrypted-at-rest id_token into the redirect URL to the auth server. Instead it should pass something opaque, such as a single-use, short-lived handle in the shared session store, which the auth server's /oauth2/logout endpoint redeems server-side before building the provider-specific IdP logout request, keeping the old id_token_hint query parameter as a fallback. Getting it right means handling the session-delete ordering, single-use and no-logging rules for the handle, compatibility between the two services, and per-provider differences, none of which current tests cover.
