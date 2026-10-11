# Testing Plan: Registration Admission Control Gate

Base: `mcp-gateway-registry` tag `v1.0.19`. Design: `lld.md` (rev 2). Review: `review.md`.

## 1. Functional tests

Unit tests in `tests/unit/services/test_registration_gate_service.py`, using `httpx.MockTransport` through the `transport` constructor argument. No global patching.

| Case | Setup | Expected |
|---|---|---|
| Allow | gate returns 200 | `check` returns `None`; one POST made |
| Deny with detail | gate returns 403 `{"detail": "naming violation"}` | raises `RegistrationDeniedError("naming violation")` |
| Deny without usable detail | 403, body `not json` | detail = `Registration denied by admission gate` |
| Deny with empty detail | 403 `{"detail": ""}` | generic detail |
| Gate 500 | 500 | raises `RegistrationGateUnavailableError` |
| Gate 404 / other 4xx | 404 | raises `RegistrationGateUnavailableError` (only 403 is a deny) |
| Timeout | handler raises `httpx.ReadTimeout` | raises `RegistrationGateUnavailableError` |
| Connection error | handler raises `httpx.ConnectError` | raises `RegistrationGateUnavailableError` |
| Enabled, URL empty | `enabled=True, url=""` | raises `RegistrationGateUnavailableError`, no request |
| Disabled | `enabled=False` | returns `None`, no request, even with a broken URL |
| Auth header set | `auth_header="Bearer t"` | request carries `Authorization: Bearer t` |
| Auth header unset | `auth_header=""` | no `Authorization` header |
| Secrets removed | asset has `auth_credential`, `auth_credential_encrypted`, `headers` | none present in the request body; other keys intact |
| Truncation | gate detail 2000 chars | raised detail is 500 chars |
| Body shape | any allow case | body is `{"registration_type": ..., "asset": {...}}` |

Route helper tests in the same file (or `tests/unit/api/test_registration_gate.py` if a unit `api` directory exists; check before creating):

| Case | Expected |
|---|---|
| `RegistrationDeniedError("x")` | `HTTPException` 403, detail `x (from admission gate)` |
| `RegistrationGateUnavailableError` | `HTTPException` 503, detail `Registration gate unavailable; registration blocked` |

Route-level behavior is checked by the smoke run (section 5), not by one test per route, to keep the suite fast.

## 2. Backwards-compatibility tests

- With `REGISTRATION_GATE_ENABLED` unset (default `False`), all eight routes behave as before. Verified by the existing unit suites: `tests/unit/services/test_agent_service.py`, `test_server_service.py`, and the `skill_routes` tests under `tests/unit/`. These must pass unchanged.
- No existing test is edited to accommodate the gate. If one fails, the gate has changed behavior when disabled, which is a bug.
- The 409 duplicate check on `/servers/register` is unchanged and still runs before the gate.

## 3. UX tests

- The gate's `detail` appears in the existing UI error display for the UI `register_service` and `edit_server_submit` routes. Checked by reading the response shape: the UI already displays `HTTPException.detail`. No frontend change.
- The 403 suffix `(from admission gate)` is present, matching the issue's acceptance wording.

## 4. Deployment tests

- `terraform fmt -check` and `terraform validate` on `terraform/aws-ecs` if the toolchain is present. If absent, state it and rely on static review of the diff.
- `helm lint charts/registry` if helm is present; otherwise a `helm template` dry run is skipped and stated.
- `docker-compose.yml` parses: `docker compose config` if available; otherwise `python -c "import yaml; yaml.safe_load(open(...))"` on each compose file.
- Confirm `REGISTRATION_GATE_AUTH_HEADER` appears in `.env.example`, all three compose files, `terraform/aws-ecs/modules/mcp-gateway/ecs-services.tf`, and `charts/registry/templates/secret.yaml` and `deployment.yaml`.

## 5. End-to-end (smoke) tests

1. Start a local stub gate with `http.server` on `127.0.0.1:<port>`: returns 403 `{"detail":"stub deny"}` when the body's `asset.path` contains `deny`, otherwise 200.
2. Drive the service directly with real `httpx` against the stub (no mock transport): allow case returns, deny case raises with `stub deny`.
3. Drive the route helper against the stub: confirm the 403 `HTTPException` detail is `stub deny (from admission gate)`.
4. Point the URL at a closed port: confirm 503 and no exception leaks past the helper.
5. Confirm the gate-off path: `REGISTRATION_GATE_ENABLED=false` makes no outbound request (stub logs zero hits).

Commands: `uv run python -m py_compile` on each changed Python file; `uv run ruff check` and `uv run ruff format --check` on changed files; `uv run python -m unittest` for the new test module and the existing service tests listed in section 2.

## 6. Out of scope

- Live Anthropic/GoDaddy ANS calls: not exercised.
- Full-stack docker-compose boot: not run in this environment unless Docker is present; stated if skipped.
- Load and latency under the gate timeout: not measured.
