# Low-Level Design: Registration Admission Control Gate

Base: `mcp-gateway-registry` tag `v1.0.19`, commit `9d031852c1acc2a095e33021bb8906b0affed4f4`.

## 1. Components

| File | Change |
|---|---|
| `registry/services/registration_gate_service.py` | New. `RegistrationGateService.check(registration_type, asset)`. Owns the HTTP call, the decision, and the secret redaction. Raises domain errors only; no FastAPI imports. |
| `registry/api/registration_gate.py` | New. `enforce_registration_gate(registration_type, asset)`. Calls the service and converts errors to `HTTPException` (403 deny, 503 unavailable). Called by the eight route handlers. |
| `registry/core/config.py` | Add four `Settings` fields after the ANS block. |
| `registry/api/agent_routes.py` | Gate in `register_agent` (before line 426 `try`) and `update_agent` (before line 1250 `try`). |
| `registry/api/skill_routes.py` | Gate in `register_skill` (before line 637 `try`) and `update_skill` (before the `updates = request.model_dump(...)` line). |
| `registry/api/server_routes.py` | Gate in UI `register_service` (before line 789), `internal_register_service` (before line 1030 log), `edit_server_submit` (before line 1591 `update_server`), and API `register_service_api` (before line 2704 `try`). |
| `.env.example`, `docker-compose.yml`, `docker-compose.prebuilt.yml`, `docker-compose.podman.yml` | Env wiring. |
| `terraform/aws-ecs/**` | Root `variables.tf` and `main.tf` module input, module `variables.tf` (`registration_gate_auth_header`, `sensitive = true`), `ecs-services.tf` env block for the registry service (plain value, mirroring `ANS_API_KEY`), `terraform.tfvars.example`. |
| `charts/registry/values.yaml`, `charts/registry/templates/secret.yaml`, `charts/registry/templates/deployment.yaml` | `registrationGate.authHeader` value written to the secret as base64; deployment reads `REGISTRATION_GATE_AUTH_HEADER` from the secret via `secretKeyRef`, matching the `ANS_API_KEY` pattern at `deployment.yaml:141`. |
| `tests/unit/services/test_registration_gate_service.py` | New unit tests. |
| `docs/design/registration-admission-gate.md` | New contract doc for gate implementers. |

## 2. Config

```python
registration_gate_enabled: bool = Field(default=False, description="Enable the registration admission gate")
registration_gate_url: str = Field(default="", description="Admission gate endpoint URL (POST)")
registration_gate_timeout_seconds: int = Field(default=5, description="Admission gate request timeout in seconds")
registration_gate_auth_header: str = Field(default="", description="Optional Authorization header value sent to the gate")
```

Values are read per request through `settings`. Tests pass values explicitly, so no global state is patched.

Secret handling: `REGISTRATION_GATE_AUTH_HEADER` is a credential. Helm keeps it in the secret, not a ConfigMap. Terraform marks it `sensitive`, but passes it as a plain container env value, as `ANS_API_KEY` is today. The ECS task definition therefore holds it in plaintext; this is recorded as a known limit in the contract doc, not fixed here.

## 3. Gate contract (HTTP)

Request: `POST {REGISTRATION_GATE_URL}`, `Content-Type: application/json`, `Authorization: <REGISTRATION_GATE_AUTH_HEADER>` only when set.

```json
{"registration_type": "agent_register", "asset": { "...": "..." }}
```

`registration_type` values:

| Route | Value |
|---|---|
| `POST /agents/register` | `agent_register` |
| `PUT /agents/{path}` | `agent_update` |
| `POST /register` (UI) | `server_register` |
| `POST /servers/register` (API) | `server_api_register` |
| `POST /edit/{path}` | `server_update` |
| `POST /internal/register` | `server_internal_register` |
| `POST /skills` | `skill_create` |
| `PUT /skills/{path}` | `skill_update` |

`asset` is the registration data as the route would persist it, with these top-level keys removed: `auth_credential`, `auth_credential_encrypted`, `headers`. Nested keys are not removed.

Responses:

| Gate response | Registry behavior | Caller sees |
|---|---|---|
| 200 | allow; persist | normal route response |
| 403 with JSON `{"detail": str}` | deny | 403, `detail` = `<gate detail, truncated to 500 chars> (from admission gate)` |
| 403 without usable `detail` | deny | 403, `detail` = `Registration denied by admission gate` |
| any other status | block (fail-closed) | 503, `Registration gate unavailable; registration blocked` |
| connection error, timeout | block (fail-closed) | 503, same message |
| enabled but URL empty | block (fail-closed) | 503, same message |
| disabled | no call | unchanged |

Gate `detail` text is surfaced verbatim (truncated) because the spec requires it. Other gate bodies are never echoed.

## 4. Service

```python
class RegistrationDeniedError(Exception):
    def __init__(self, detail: str) -> None: ...

class RegistrationGateUnavailableError(Exception): ...

class RegistrationGateService:
    def __init__(self, *, enabled: bool, url: str, timeout_seconds: int, auth_header: str, transport: httpx.AsyncBaseTransport | None = None) -> None: ...

    async def check(self, registration_type: str, asset: dict[str, Any]) -> None:
        if not self._enabled: return
        if not self._url: log error; raise RegistrationGateUnavailableError
        body = {"registration_type": registration_type, "asset": _redact(asset)}
        try:
            async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
                response = await client.post(self._url, json=body, headers=headers)
        except httpx.HTTPError as e:   # covers timeouts and connection errors
            log error; raise RegistrationGateUnavailableError from e
        if response.status_code == 200: log info; return
        if response.status_code == 403: detail = _extract_detail(response); log warning; raise RegistrationDeniedError(detail)
        log error; raise RegistrationGateUnavailableError
```

`_redact` returns a shallow copy with the three secret keys removed. `_extract_detail` reads `response.json()["detail"]` when it is a non-empty string, otherwise uses the generic text; the result is truncated to 500 chars.

Log lines include `registration_type` and the asset `path` when present. They never include secret fields or the gate body.

## 5. Route helper

```python
async def enforce_registration_gate(registration_type: str, asset: dict[str, Any]) -> None:
    try:
        await registration_gate_service_from_settings().check(registration_type, asset)
    except RegistrationDeniedError as e:
        raise HTTPException(status_code=403, detail=f"{e} (from admission gate)")
    except RegistrationGateUnavailableError as e:
        raise HTTPException(status_code=503, detail="Registration gate unavailable; registration blocked")
```

`RegistrationDeniedError` carries the already-truncated detail, so the helper appends only the suffix.

## 6. Placement and asset per route

Rule: the gate call goes after existing validation and before any persistence or FAISS/nginx side effect, and outside any `try` whose `except Exception` would turn `HTTPException` into 500.

| Route | Insert before | Asset |
|---|---|---|
| `register_agent` | line 426 `try:` | `request.model_dump(mode="json")` |
| `update_agent` | line 1250 `try:` | `request.model_dump(mode="json")` |
| `register_skill` | line 637 `try:` | `request.model_dump(mode="json")` |
| `update_skill` | line before `updates = request.model_dump(exclude_unset=True, ...)` | `request.model_dump(mode="json")` |
| UI `register_service` | line 789 `result = await server_service.register_server(server_entry)` | `server_entry` |
| `internal_register_service` | line 1030 (log before register/update) | `server_entry` |
| `edit_server_submit` | line 1591 `success = await server_service.update_server(...)` | `updated_server_entry` |
| `register_service_api` | line 2704 `try:` (after the 409 duplicate check) | `server_entry` |

The 409 duplicate check on `/servers/register` runs before the gate. A rejected duplicate writes nothing, so the gate is not consulted for it.

## 7. Excluded

- `PATCH /servers/{path}/auth-credential`: credential rotation on an existing server, not a registration. Excluded and recorded in the issue.
- `POST /servers/{path}/rescan`, toggles, and group changes: not registrations.

## 8. Failure and security notes

- Fail-closed: any error on the gate path blocks the write. No write occurs before the gate call, so there is nothing to roll back.
- Secrets are removed from `asset` before the call. The token in `REGISTRATION_GATE_AUTH_HEADER` is sent only to the configured gate URL and is never logged.
- SSRF: the URL is operator-configured, not user input, so no per-request validation is added. Documented in the contract doc.
- No caching, no retries (out of scope).

## 9. Verification plan

- Unit tests with `httpx.MockTransport`: allow, deny with detail, deny with no detail, 500, timeout (`httpx.ReadTimeout` via handler raising), connection error, enabled without URL, disabled makes no request, auth header set, secrets removed from body, truncation of long detail.
- Route-helper tests: 403 and 503 mapping and the suffix.
- Smoke: run the service against a local `http.server` stub returning 403/200 and observe the outcomes.
- `python -m py_compile` and `ruff` on changed Python files; full harness `unittest discover` for the touched test module.
