# Implementation: Registration Admission Control Gate

Source: `patch.diff` (20 files, 603 insertions, no deletions), applied to `mcp-gateway-registry` tag `v1.0.19`.

## What changed

**Gate client (new)**

- `registry/services/registration_gate_service.py`: `RegistrationGateService.check()` POSTs `{registration_type, asset}` to the configured URL. It removes the top-level keys `auth_credential`, `auth_credential_encrypted`, and `headers` before sending. A 200 allows. A 403 raises `RegistrationDeniedError` with the gate's `detail` truncated to 500 characters, or the generic text when `detail` is missing or not a string. Any other status, any `httpx.HTTPError` (including timeouts), and an empty URL raise `RegistrationGateUnavailableError`.
- `registry/api/registration_gate.py`: `enforce_registration_gate()` maps denial to 403 with the suffix ` (from admission gate)` and unavailability to 503 with `Registration gate unavailable; registration blocked`. It builds the client from settings on every call.

**Routes (8 call sites)**

- `agent_routes.py`: `register_agent`, `update_agent`.
- `skill_routes.py`: `register_skill`, `update_skill`.
- `server_routes.py`: UI `register_service`, `internal_register_service`, `edit_server_submit`, API `register_service_api`.

`register_agent` calls the gate at line 427, before `agent_validator` (line 470) and `register_agent` persistence (line 493). The other routes were placed by the same rule (before persistence and side effects), but only `register_agent` was traced in order.

**Config**

- `registry/core/config.py`: four settings: `registration_gate_enabled` (false), `registration_gate_url` (empty), `registration_gate_timeout_seconds` (5), `registration_gate_auth_header` (empty).
- Infra: `.env.example`, `docker-compose.yml`, `docker-compose.podman.yml`, `docker-compose.prebuilt.yml`; Terraform root `main.tf`, `variables.tf`, `terraform.tfvars.example`, module `variables.tf`, module `ecs-services.tf`; Helm `values.yaml`, `templates/deployment.yaml`, `templates/secret.yaml`.

**Docs and tests**

- `docs/design/registration-admission-gate.md`: the gate's request and response contract for operators implementing the endpoint.
- `tests/unit/services/test_registration_gate_service.py`: 19 tests using `httpx.MockTransport`.

## Verification

- `python -m unittest tests.unit.services.test_registration_gate_service`: 19 tests, OK, after the final formatting pass.
- `ruff check` and `ruff format --check` on the new files (`registration_gate.py`, `registration_gate_service.py`, the test module): clean.
- `docker compose -f <file> config -q` on all three compose files: exit 0. The gate variables resolve to the expected defaults. `GRAFANA_ADMIN_PASSWORD` was set to a placeholder for this command only.
- `python -m unittest discover -s tests`: 21 run, 2 errors. The same 2 import errors (`auth_server.providers` missing for `test_okta`; `unit.lambda.test_collector`) occur on a clean `git archive HEAD` export, so they are pre-existing and not caused by this change.
- `git apply --check patch.diff` against a clean `git archive HEAD` export: exit 0.
- Backwards-compat suites named in `testing.md` (`test_agent_service`, `test_server_service`, `test_skill_routes_security`, `test_skill_routes_github_auth`) are pytest-based and do not run under `unittest`. Run with `pytest --no-cov` together with the gate module: 132 passed, exit 0. Without `--no-cov` the run exits 1 only because the project's 35% coverage gate applies to a subset run (reports 9%).
- Stub-gate smoke against the service (local `http.server` returning 200, 403 with detail, 500): ALLOWED, DENIED with the gate detail, BLOCKED `gate returned HTTP 500`. This exercises `RegistrationGateService` only, not a route.

## Not verified

- `helm` and `terraform` are not installed on this machine. The chart and Terraform edits were checked by reading the surrounding code, not by `helm template` or `terraform validate`.
- No route-level test drives the 8 route handlers through HTTP, and the stub-gate smoke did not go through a route. The 403 and 503 mapping is covered at the helper level.
- Not run against a real operator gate endpoint. The stub above is local and returns canned responses.

## Known limits

- On ECS and in compose, `REGISTRATION_GATE_AUTH_HEADER` is a plain environment value, the same way `ANS_API_KEY` is passed. It is visible in the task definition. The Helm path can use an existing secret instead.
- Redaction removes top-level keys only. A nested `headers` or credential field would be sent to the gate. The LLD and contract doc both say so.
- Pre-existing lint findings in touched files, left alone to keep the diff to this change: `server_routes.py` F401 (unused `verify_csrf_token`), `config.py` UP042 (two enums), and format drift in `agent_routes.py`, `skill_routes.py`, and `config.py`.

## Changes from the LLD

- LLD section 3 said redaction applies "at any depth". The code is shallow. The LLD now says top-level only.
