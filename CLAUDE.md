# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Current state

**Hito 0 complete — the stack is runnable** (`docker compose up` → postgres/temporal/redis/minio/api/worker; the create→version→launch→execute vertical works end-to-end against real Temporal; see `README.md`). Built so far: workflow validation core, Temporal interpreter (command/rest), persistence (docs-03 schema + Alembic), workflow CRUD + versioning, executions (idempotent launch), JWT auth + RBAC, docker-compose, CI. Still to build: execution state/event sync back to Postgres + live feed (Redis/WebSocket), `sql` job, remote agent (Hito 5), frontend (Hito 2), cron triggers. The docs are Spanish; the **product/UI/code is English** (i18n-ready). Treat the docs as the source of truth (design refined in the v2 ADRs — see `docs/00-README.md` changelog). Read them before scaffolding new subsystems:

### What's built (tested, lint+type clean)
- `services/api/moiraflow_api/workflow/` — pure-Python validation core: Pydantic models (`models.py`, single source of truth + generated JSON Schema), `parser.py` (YAML/JSON→model), `dag.py` (Kahn cycle detection + topo order), `references.py` (declared-outputs + determinism rules), `hashing.py` (canonical sha256 for immutable versions), `validator.py` (`validate_workflow()` aggregator, never raises). Public surface re-exported from `workflow/__init__.py`.
- `services/api/moiraflow_api/` — FastAPI app (`main.py`, `create_app()`). Endpoints under `/api/v1`: `POST /workflows/validate` (200-with-errors), `GET /catalog/workflow-schema`, workflow CRUD (`POST/GET /workflows`, `GET /workflows/{id}`, `GET|POST /workflows/{id}/versions`, `POST /workflows/{id}/activate/{v}`), executions (`POST /executions`, `GET /executions[?workflow_id]`, `GET /executions/{id}`). Service errors map to a `{error:{code,message,details}}` envelope via `errors.py`.
- `services/api/moiraflow_api/services/` — `workflows.py` (CRUD + immutable content-hashed versioning; name from `metadata.name`, unique per tenant) and `executions.py` (launch via injectable `WorkflowStarter` protocol; deterministic `temporal_workflow_id` → idempotent `executions` projection, ADR-0014). `temporal.py` is the real lazy-imported starter; tests inject a fake.
- `services/api/moiraflow_api/{config,deps}.py` — env settings + DI: per-request `get_session` (commit/rollback), `get_default_tenant`, `get_workflow_starter` (override in tests).
- `services/api/moiraflow_api/db/` — persistence: `base.py` (DeclarativeBase + portable types — JSONB/CITEXT/INET with Postgres variants so models run on sqlite in tests), `models.py` (full docs-03 schema, 12 tables, `tenant_id` everywhere), `session.py`. Tested on in-memory sqlite. **TODO:** Alembic migration (pairs with the docker-compose/Postgres slice).
- `services/api/moiraflow_api/auth/` + `services/users.py` — JWT auth: argon2id password hashing + HS256 tokens (`security.py`), `POST /auth/login` + `GET /auth/me`, and DI guards `get_current_user`/`get_current_tenant`/`require_roles(...)` enforcing the docs-04 RBAC matrix (admin always allowed; developers create/edit workflows; operators+developers launch executions; all roles read). `AuthError` → 401/403 envelope. Endpoints now require a Bearer token; tests authenticate via `tests/_helpers.py` (seed user + override `get_current_user`).
- The workflow schema `apiVersion` is **`moiraflow/v1`**. MVP still runs a single default tenant (multi-tenancy is schema-ready). No `create_admin` bootstrap script yet — seed users directly for now.
- `services/worker/moiraflow_worker/` — the Temporal interpreter: `templating.py` (pure deterministic `{{ }}` rendering), `scheduling.py` (pure DAG readiness), `interpreter.py` (`run_dag` — pure async orchestration with an injected `run_job`, parallel fan-out, declared-output propagation), `workflow.py` (`FlowInterpreter` `@workflow.defn` thin adapter; maps per-job `timeout`/`retry` → Temporal via `durations.py`/`policies.py`), `activities.py` (`run_command_job`, `run_rest_job` with an `execute_rest` seam tested via `httpx.MockTransport`), `runtime.py` (`build_worker`). Pure core is unit-tested; `tests/test_workflow_integration.py` runs a real 2-job DAG against `WorkflowEnvironment.start_local()`. **Still TODO:** `sql` activity (depends on secrets+DB slices), replay tests in CI (ADR-0011).
- Plan + TDD task breakdown: `docs/superpowers/plans/2026-06-24-workflow-validation-core.md`.

### Dev workflow for `services/api` (local Python is 3.10, not 3.12 — code runs on both)
Tests run with **no editable install** (pytest `pythonpath` config). From `services/api/`:
```bash
python3 -m pytest -q                          # 35 tests
python3 -m ruff check moiraflow_api tests
python3 -m black --check moiraflow_api tests
python3 -m mypy moiraflow_api                    # strict
```
Deps present system-wide: pydantic 2.13, pyyaml, pytest, fastapi, httpx, ruff, black, mypy. `uvicorn` not installed (only needed to actually serve; tests use `TestClient`).

### Original doc map (source of truth):

- `docs/01-factibilidad-alcance-mvp.md` — feasibility, scope, MVP definition (thin vertical slice), Definition of Done
- `docs/02-arquitectura.md` — architecture, components, Temporal's role, key flows
- `docs/03-modelo-datos.md` — PostgreSQL schema (every business table has `tenant_id`), states, audit, Alembic
- `docs/04-api-y-esquema-workflow.md` — FastAPI REST endpoints + the workflow-as-code YAML/JSON schema and validation rules
- `docs/05-protocolo-agente-seguridad.md` — thin-agent protocol, enrollment, mTLS, secrets, isolation, security checklist (**highest-risk component**)
- `docs/06-roadmap-y-adr.md` — milestones (~16 weeks to MVP for 1 dev) and ADRs
- `docs/07-repo-y-setup-dev.md` — monorepo layout, stack, docker-compose, env vars, quickstart, first tickets

## What MoiraFlow is

An "Automation Operating System" for SMBs: a workflow automation platform where workflows are defined as code (YAML/JSON), executed as durable DAGs, and can run jobs either server-side or on remote "thin agents" installed on customer machines.

## Architecture (the big picture)

The single most important decision: **MoiraFlow does not build its own execution engine — it runs on Temporal.** Understanding how MoiraFlow concepts map onto Temporal is essential before touching the worker or execution code:

- A MoiraFlow workflow (a DAG of jobs) is **not** one Temporal workflow per definition. Instead there is **one generic Temporal Workflow ("the interpreter")** that receives a versioned workflow definition + inputs, resolves the DAG, and executes jobs in dependency order. The initial `context` is **read-only**; jobs do **not** mutate a shared blob — they declare `outputs` exposed as `jobs.<id>.outputs.*` (ADR-0013, avoids parallel-branch races).
- **The interpreter must be deterministic** (or Temporal replay corrupts silently): pure DAG orchestration + pure template interpolation in workflow code; all I/O, `secret://` resolution, time, and randomness in **activities**. No non-deterministic template filters (`now()`/random). CI runs **replay tests** (ADR-0011).
- Each **job is a Temporal Activity**. The job `type` (`command`, `rest`, `sql` in the MVP) selects which plugin/activity runs.
- **Task queues do the routing.** Server-side jobs go to server worker queues; jobs with `run_on: agent` are enqueued on that agent's exclusive queue `agent-<agent_id>`, and only that agent picks them up.
- **Retries/timeouts/backoff** map directly from a job's `retry` policy to Temporal's `RetryPolicy`.
- **Replay** = start a fresh interpreter workflow with the same versioned definition + inputs (never reuse mutated history).

Data flow for an execution: API starts the interpreter Temporal workflow with a **deterministic `workflow_id`** (idempotency via `WorkflowIdReusePolicy`; the `executions` row is an idempotent **projection**, not a second source of truth — ADR-0014) → interpreter calls each ready job's Activity on the right task queue → Activity runs the plugin, returns declared `outputs`, writes artifacts to MinIO and refs to Postgres. **Live events: the worker/activity writes `execution_events` to Postgres AND publishes to Redis directly; the API WebSocket only subscribes to Redis** (Temporal does not push events to external subscribers — there is no "Temporal → API → Redis" hop). `cron` triggers are **Temporal Schedules** (ADR-0015). Activity payloads carrying secrets/context are encrypted via a Temporal **Data Converter/Codec** so they aren't stored in cleartext in Temporal history (ADR-0016).

### Component responsibilities (and what owns state)

- **API (FastAPI, `services/api/`)** — **stateless**. Auth/RBAC, workflow CRUD + immutable versioning, schema validation, launching/querying executions (delegates to Temporal), plugin catalog, machine-readable catalog/validate/simulate endpoints. All state lives in Postgres/Temporal/MinIO/Redis.
- **Worker (`services/worker/`)** — registers the interpreter Temporal Workflow + server-side job activities (`rest`, `sql`, local `command`). Scales by adding replicas.
- **Agent (`services/agent/`)** — the **same worker runtime** on a dedicated task queue, runs only `command` jobs in the MVP. **MVP starts as a *local* worker (same host, ADR-0017)** to validate the full `run_on: agent` contract; the *remote* agent (mTLS, CA, enrollment) is a later timeboxed milestone. **The agent never receives tenant credentials, DB access, or the secrets master key.** Secrets reach it via **per-agent envelope encryption** (encrypted to the agent's public key — ADR-0013), so a stolen task can't leak them. ⚠️ **A Temporal task queue name is NOT a security boundary** — any authenticated worker can poll any queue; isolation comes from crypto + (Phase 3) per-tenant namespaces, never from the `agent-<id>` name (ADR-0012).
- **PostgreSQL** — source of truth for metadata + audit (definitions, versions, executions, job_executions, events, users, plugins, agents, secrets). Stores **references** to MinIO objects, never binaries. Everything carries `tenant_id`.
- **Redis** — **UI pub/sub only**, not the execution queue. If it dies, nothing durable is lost (truth stays in Postgres/Temporal).
- **MinIO (S3-compatible)** — artifact storage (inputs/outputs/reports). Postgres holds the key + metadata.
- **Frontend (React + TS + Vite + React Flow, `services/frontend/`)** — pure API consumer; its API client is **generated from the API's OpenAPI** (single contract). React Flow renders the DAG read-only in the MVP.

### Cross-cutting principles that govern design choices

- **API First** — every capability exists via the API; the UI only consumes it.
- **Plugin First** — the core depends on no concrete connector; jobs/connectors are plugins (Temporal activities) with a common contract registered in the `plugins` catalog.
- **Workflow as Code** — YAML/JSON is the source of truth; versions are **immutable and content-hashed** (`workflow_versions` is never updated or deleted).
- **AI First** — the engine exposes machine-readable catalog + `validate` + `simulate` (dry-run) endpoints (reserved now for the future "MoiraFlow Architect" AI, built in a later phase). The AI generates valid YAML/JSON; it **never** touches internal tables.
- **Multi-tenant ready** — `tenant_id` on every business table from day 1 (MVP runs a single "default" tenant; RLS is prepared but enforced in the API layer for now). A job from one tenant must never route to another tenant's agent.
- **Auditability** — nothing critical lives only in memory; `execution_events` (per-execution timeline) and `audit_log` (user/system governance actions) are append-only.

## Planned stack & layout

Monorepo (`services/api`, `services/worker`, `services/agent`, `services/frontend`; `packages/shared-schemas`; `deploy/`). Each Python service keeps its own `pyproject.toml`; the frontend its own `package.json`.

- **API**: Python 3.12, FastAPI, Pydantic v2, Uvicorn, SQLAlchemy 2, Alembic
- **Worker/Agent**: Python + Temporal Python SDK
- **DB**: PostgreSQL 16 (needs `pgcrypto` + `citext` extensions)
- **Auth**: JWT with argon2id password hashing; roles `admin`/`operator`/`developer`/`viewer`
- **Tests**: pytest (backend, including Temporal test environment for the interpreter); Vitest/Playwright (frontend)
- **Lint/format**: ruff + black + mypy (Python); eslint + prettier (TypeScript)

## Planned dev commands (target — not yet implemented)

Per `docs/07`, once scaffolded the workflow is:

```bash
cp .env.example .env                 # set secrets
docker compose up -d                 # full local stack
docker compose exec api alembic upgrade head            # migrations
docker compose exec api python -m moiraflow_api.scripts.create_admin   # initial admin
# UI http://localhost:5173 · API docs http://localhost:8000/api/v1/docs
# Temporal UI http://localhost:8080 · MinIO http://localhost:9001
```

Schema changes go through Alembic (`alembic revision --autogenerate -m "..."`, review, commit) — never hand-edit the schema in any environment. Regenerate the frontend API client from the API's OpenAPI after API contract changes.

## When scaffolding (suggested first tickets, from `docs/07`)

1. Monorepo scaffold + `docker-compose` bringing up the 4 base services (postgres, temporal, redis, minio).
2. Initial Alembic migration for the full `docs/03` schema (+ `pgcrypto`, `citext` extensions).
3. Workflow JSON Schema + `POST /api/v1/workflows/validate`.
4. Minimal interpreter Temporal Workflow: run a 2-job `rest` DAG.
5. `POST /api/v1/executions` + execution/event persistence.
6. React executions list page with live log stream.

## Security notes that affect implementation (from `docs/05`)

The remote agent is the highest-risk component. Non-negotiable invariants when implementing it:

- **Explicit admin approval before any execution** — no trust-on-first-use. Single-use, short-lived enrollment tokens.
- **mTLS** agent↔Temporal, verified by persisted certificate `fingerprint`; revocation must actually block reconnection (CRL/denylist).
- **Late secret resolution**: `secret://<key>` is resolved as late as possible — server-side by the server worker; for agents the secret is passed **encrypted** as an activity param and decrypted **in memory only** during execution, never written to disk. Logs/outputs pass through a **redactor** that masks secret values.
- **Isolation**: `command` jobs run as a dedicated unprivileged user with CPU/mem/time limits and an ephemeral working dir (MVP); per-job container isolation is Phase 2.
