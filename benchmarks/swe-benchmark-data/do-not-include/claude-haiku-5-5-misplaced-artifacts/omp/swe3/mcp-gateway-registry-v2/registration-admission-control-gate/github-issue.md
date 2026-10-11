# GitHub Issue: Registration admission control gate

## Title
Add a registration admission control gate that consults an external policy endpoint before agents, servers, and skills are persisted

## Labels
- enhancement
- policy-enforcement
- authentication

## Description

### Problem Statement
Any authenticated user with publish permission can register or update an agent, server, or skill with no external policy check. Organizations need to apply their own rules before a registration is persisted: naming conventions, required metadata, approval workflows, asset classification, and risk scoring.

Without an admission gate, an organization cannot enforce a registry-wide policy without modifying registry code.

### Proposed Solution
Add an admission gate that runs before persistence on every registration and update path. When enabled, the registry POSTs the asset to a configurable HTTP endpoint and proceeds only on an explicit allow.

1. The gate runs on all eight write paths: agent register, agent update, server register (UI form), server register (API), server edit, server internal register, skill create, and skill update.
2. The registry POSTs a JSON body `{"registration_type": "<path-type>", "asset": {...}}` to `REGISTRATION_GATE_URL`.
3. HTTP 200 allows the write. HTTP 403 denies it, and the gate's `detail` string is returned to the caller as a 403.
4. Any other gate response (4xx other than 403, 5xx), a connection error, or a timeout blocks the write (fail-closed) and returns 503 with a generic message. The gate's body is not echoed.
5. The gate is off by default. With the flag unset, no outbound call is made and behavior is unchanged.
6. The `registration_type` field identifies the endpoint that triggered the call.

### Acceptance Criteria
- [ ] Gate is configured by `REGISTRATION_GATE_ENABLED` (default `false`), `REGISTRATION_GATE_URL`, `REGISTRATION_GATE_TIMEOUT_SECONDS` (default `5`), and optional `REGISTRATION_GATE_AUTH_HEADER` (sent as the `Authorization` header value).
- [ ] The gate runs before persistence on: agent register, agent update, server register (UI `/register`), server register (API `/servers/register`), server edit (`/edit/{path}`), server internal register (`/internal/register`), skill create (`POST /skills`), skill update (`PUT /skills/{path}`).
- [ ] With the gate disabled, no outbound request is made and all eight paths behave as before.
- [ ] HTTP 200 allows; HTTP 403 denies and returns 403 with the gate's `detail` plus the suffix ` (from admission gate)`.
- [ ] Unreachable gate (connection error), timeout, non-403 error status, or enabled-but-no-URL blocks the write with 503 and writes nothing.
- [ ] Each request body carries `registration_type` identifying the triggering endpoint.
- [ ] Secret fields (`auth_credential`, `auth_credential_encrypted`, `headers`) are removed from the `asset` before it is sent to the gate.
- [ ] Gate decisions are logged: allow at INFO, deny at WARNING, failures at ERROR. Log lines contain the registration type and path, never the secret fields.
- [ ] Config is wired through `registry/core/config.py`, `.env.example`, `docker-compose.yml`, `docker-compose.prebuilt.yml`, `docker-compose.podman.yml`, Terraform (`terraform/aws-ecs`), and Helm (`charts/registry`).
- [ ] Unit tests cover allow, deny, timeout, unreachable, non-403 error, disabled-by-default, auth header, and secret redaction.
- [ ] The request and response contract is documented for gate implementers.

### Out of Scope
- Implementing the external gate service (the caller's responsibility).
- Caching gate responses. Every registration calls the gate.
- Retries or fallback on gate timeout.
- Rate limiting of gate calls.
- UI changes. The feature is configured by environment variables.
- Versioning of the gate contract (caller's responsibility).
- The credential-only PATCH `/servers/{path}/auth-credential`. It rotates a credential on an existing server and does not register or replace an asset. This is recorded as a deliberate exclusion in `lld.md`.

### Dependencies
- `httpx` (already a registry dependency; used by `registry/services/ans_client.py`).
- Existing `Settings` (pydantic-settings) in `registry/core/config.py`.
- Existing auth and audit framework.

### Acceptance Test Scenario
1. Gate enabled with `REGISTRATION_GATE_URL=https://policy.example.com/gate`.
2. Admin registers an agent at path `my-agent/test`, which violates the lowercase rule.
3. The registry POSTs `{"registration_type": "agent_register", "asset": {...}}` to the gate.
4. The gate responds 403 with `{"detail": "Agent path must be lowercase"}`.
5. The registry returns 403 to the admin with `Agent path must be lowercase (from admission gate)`.
6. The admin retries with `myagent/test`. The gate returns 200 and the agent is persisted.

### Related Issues
- Original request for registration admission control (issue #809, per the upstream tracker).

### Implementation Notes
- Gate client: `registry/services/registration_gate_service.py`.
- Route helper: `registry/api/registration_gate.py`, which maps service errors to `HTTPException`.
- The call happens after existing validation and before any `try` block that could convert an `HTTPException` into a 500.
- Error handling treats connection errors, timeouts, and non-403 errors as deny.
