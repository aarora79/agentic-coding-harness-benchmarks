# Expert Review: Registration Admission Control Gate

Reviewed: `lld.md` (base `9d031852`, tag `v1.0.19`).

## Persona 1: Security engineer

- **BLOCKER (resolved in LLD rev 2):** the gate auth value (`REGISTRATION_GATE_AUTH_HEADER`) is a credential, and the LLD did not specify its handling. Revision: Helm stores it in the chart secret template (`charts/registry/templates/secret.yaml`) and the deployment reads it from the secret, matching the ANS key pattern. Terraform marks the variable `sensitive = true`.
- **Known limit (recorded, not fixed):** in Terraform, `ANS_API_KEY` is passed as a plain container environment value (`terraform/aws-ecs/modules/mcp-gateway/ecs-services.tf`, `value = var.ans_api_key`), not from a secret store. The gate auth value follows the same pattern for consistency. It is marked `sensitive` so it does not print in plan output, but it is visible in the ECS task definition. Recorded in the contract doc and `.env.example`.
- **MUST-FIX (resolved):** the asset sent to the gate must not carry plaintext credentials. The UI and internal server entries can hold `auth_credential` and `headers`. Redaction covers `auth_credential`, `auth_credential_encrypted`, and `headers`. A unit test pins the redaction.
- **SHOULD-FIX (accepted):** the gate's `detail` is returned to the caller. Truncated to 500 chars; the spec requires it. Other gate body content is never echoed.
- **SHOULD-FIX (accepted):** SSRF. `REGISTRATION_GATE_URL` is operator config, not user input. No per-request URL validation. Documented in the contract doc.

## Persona 2: Backend / API engineer

- **MUST-FIX (resolved in LLD section 6):** gate placement must not fall inside an `except Exception` `try`. Verified: `register_service_api` wraps persistence in a `try` at line 2704 whose `except Exception` (line 2754) turns `HTTPException` into 500. The gate goes before that `try`. The same rule applies to `register_agent` (line 426) and `update_agent` (line 1250).
- **SHOULD-FIX (resolved):** the UI `register_service` persistence (line 789) has no enclosing `try`, so the gate is placed immediately before it, after the form-field parsing.
- **NOTE:** `/servers/register` returns 409 for duplicates before the gate. Accepted; a rejected duplicate writes nothing.
- **NOTE:** `enforce_registration_gate` lives in `registry/api/`, not `services/`, so the service has no FastAPI imports. Accepted.

## Persona 3: SRE / operations

- **SHOULD-FIX (accepted):** misconfiguration (enabled, URL empty) fails per request with 503, not at startup. A startup validator on `Settings` would be a second behavior change to a shared config model. Accepted: fail-closed at call time, logged at ERROR. Recorded as a known limit in the contract doc.
- **SHOULD-FIX (accepted):** every registration now adds one outbound round trip up to `REGISTRATION_GATE_TIMEOUT_SECONDS` (default 5). No retries. Documented.
- **NOTE:** log lines carry `registration_type` and `path`, not the asset body or secrets.

## Persona 4: QA / test engineer

- **MUST-FIX (partially resolved):** tests must cover the eight routes, not only the service. Resolution: service tests with `httpx.MockTransport` cover the decision matrix (19 tests); the route helper is tested directly for the 403 suffix and the 503 mapping. Open: no HTTP-level run through the eight route handlers was performed. The LLD's stub-server smoke was run against the service only, not against a route.
- **SHOULD-FIX (resolved):** tests must not patch `httpx.AsyncClient` globally. Resolution: the service takes `transport` as a constructor argument.

## Persona 5: Product / API designer

- **SHOULD-FIX (resolved):** the spec's acceptance scenario says the admin sees `(from admission gate)`. The LLD suffix matches it exactly.
- **NOTE:** the `/edit/{path}` route is a UI form endpoint and returns a 303 redirect on success. A 403 from the gate is returned as a JSON error, not a redirect. Accepted: the existing edit route already returns `HTTPException` for permission failures in the same way.
- **NOTE:** the spec's "`/servers/{path}/edit`" in the issue does not match the code (`/edit/{service_path}`). The LLD uses the real route. Recorded in the issue.

## Blocking findings

1. Secret handling for `REGISTRATION_GATE_AUTH_HEADER` across Terraform and Helm (Security). Resolved in LLD rev 2 below, with the Terraform limit recorded above.

No other blockers. The LLD is revised with the sensitive/secret wiring and the redaction test.

## LLD revision 2 (applied)

- Terraform: `variable "registration_gate_auth_header"` with `sensitive = true` and default `""`, passed through `terraform/aws-ecs/main.tf` into the registry service environment in `ecs-services.tf`, mirroring the `ANS_API_KEY` env entry (plain value, see Known limit).
- Helm: `registrationGate.authHeader` in `values.yaml`, written into `charts/registry/templates/secret.yaml` as base64, and read into the deployment from the secret. Matches the `ANS_API_KEY` secret pattern in `deployment.yaml`.
- `.env.example` documents `REGISTRATION_GATE_AUTH_HEADER` as a secret.
