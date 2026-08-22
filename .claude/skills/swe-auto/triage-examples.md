# Triage examples: classifying a task into a tier

This reference backs Step 2 of [SKILL.md](SKILL.md). It gives worked examples of each tier, drawn from the tasks shipped in this repo's datasets ([benchmarks/dataset/mcp-gateway-registry.yaml](../../../benchmarks/dataset/mcp-gateway-registry.yaml) and [benchmarks/dataset/multi-repo-throughput.yaml](../../../benchmarks/dataset/multi-repo-throughput.yaml)), so the router model has concrete anchors when classifying a new task.

## How to read a task's tier

The tier is about **risk multiplied by leverage**, not raw size:

- **How expensive is a wrong design here?** Security, auth, data-model, migration, and concurrency work is expensive to get wrong, which pulls a task **up** even when the change is small.
- **How much of the system does it touch?** Cross-cutting changes (many components, infra + app, a public API contract) pull **up**; a single self-contained function pulls **down**.
- **Would a cheap model reliably get it right?** Mechanical, well-trodden edits stay **budget**; subtle-correctness work does not.

**Tier is not the dataset `complexity` field.** `complexity` estimates size; tier estimates stakes. A `medium`-complexity security task can be **frontier** (see `ssrf-hardening`), and a `low`-complexity feature can be **workhorse** (see `fastapi-request-id-middleware`). When torn between two tiers, pick the **lower** one: the escalation loop will bump it up automatically if the run falls short, which is the cost-aware default.

## Budget tier

Small, mechanical, low-risk, localized. A cheap model gets it right, and the change is easy to review. Reach here for boilerplate, self-contained utilities, docs, and small mechanical edits.

- **`add-contributing-guide`** (hello-world) - add a `CONTRIBUTING.md`. Pure docs, no code paths, no blast radius.
- **`lodash-deep-freeze-utility`** - add one self-contained `deepFreeze` utility. New, isolated function; nothing existing changes behavior, so the risk is contained to the new code.
- **`commons-lang-nullsafe-builder`** - an *additive* fluent option on existing builders that does not alter the existing reflection builders. Localized, backward-compatible by construction.
- **`cobra-command-deprecation`** - a structured deprecation/aliasing helper: mechanical API plumbing with a clear, well-known shape.

## Workhorse tier

A typical feature or refactor: real, well-scoped engineering that spans a few components but has no sharp correctness or security edge. This is the bulk of day-to-day coding, and where routing to a mid-frontier model saves the most money.

- **`remove-faiss`** (mcp-gateway-registry) - remove a subsystem end to end across imports, dependencies, Docker build, tests, and docs, routing remaining needs to an existing alternative. Substantial but well-understood; the hard part is thoroughness, not subtlety.
- **`remove-efs-from-terraform-aws-ecs`** (mcp-gateway-registry) - an infrastructure refactor across Terraform resources and ECS task definitions, keeping `terraform validate/plan` green. Multi-file and careful, but a standard removal.
- **`fastapi-request-id-middleware`** - add request-correlation-id middleware (accept/generate `X-Request-ID`, expose via a context var, echo on the response, thread into logging). Marked `low` complexity, but it is a genuine feature touching the request lifecycle and logging, so it is **workhorse, not budget** - a clear tier-vs-complexity split.
- **`axios-request-dedup`** - an opt-in in-flight GET-dedup feature with a global/per-request config surface and cache interactions. A real feature with a design surface, but no safety-critical edge.

## Frontier tier

Business-critical, cross-cutting, or subtle-correctness/security work where a wrong design is expensive to unwind. Pay for the best model here; the token volume is usually small relative to the cost of getting it wrong.

- **`migrate-ecs-env-vars-to-secrets-manager`** (mcp-gateway-registry) - classify which env vars are secrets, create Secrets Manager resources, switch ECS to the `secrets` block, grant least-privilege IAM, and keep a plaintext fallback for cutover. Security + IAM + infra across every service, with a migration path - a wrong design leaks secrets or breaks deploys.
- **`replace-keycloak-db-password-with-rds-iam`** (mcp-gateway-registry) - remove static DB credentials, enable RDS IAM auth, mint short-lived tokens, and keep a feature-flagged password fallback. Auth-critical, cross-cutting, with a safe-cutover requirement.
- **`ssrf-hardening-outbound-url-validation`** (mcp-gateway-registry) - reuse an existing guard across every outbound-fetch path, blocking private IPs with an allowlist, covering DNS rebinding and redirects, staying backward-compatible. Marked `medium` complexity, but the **security stakes and subtle edge cases make it frontier** - the second clear tier-vs-complexity split.
- **`sqlalchemy-readonly-session`** - guarantee a session emits no writes/DDL (for read-replica routing). Subtle-correctness: the guard must be airtight or the guarantee is worthless.
- **`guava-cache-async-refresh`** - non-blocking async refresh with coalesced concurrent reloads. Concurrency correctness where races are easy to introduce and hard to catch.
- **`serde-partial-deserialize`** - "deserialize what you can, collect the rest as errors" with per-field error accumulation. An API-shape and correctness design with many edge cases.

## Quick reference

| Signal | Budget | Workhorse | Frontier |
|---|---|---|---|
| Blast radius | one file / new isolated code | a few components | cross-cutting / whole subsystem |
| Cost of a wrong design | low (easy to review/revert) | moderate | high (security, data, auth, cutover) |
| Correctness subtlety | mechanical | standard | sharp edges (races, edge cases, guarantees) |
| Example | `lodash-deep-freeze-utility` | `remove-faiss` | `ssrf-hardening-outbound-url-validation` |
