# MoiraFlow — Installation & Setup Guide

This guide walks you through running MoiraFlow locally with Docker and setting up a
development environment. The platform runs as a small stack of containers
(PostgreSQL · Temporal · Redis · MinIO · API · worker · agent) plus the frontend
(Vite/React dev server).

> **About the container images:** the code for `api`, `worker`, and `agent` is **baked
> into the image at build time** — there is no source volume mounted. If you change
> backend code, you must **rebuild the image** (`docker compose up -d --build <service>`)
> for the change to take effect. The frontend is different: it runs with hot reload via
> `npm run dev`.

---

## 1. Prerequisites

| Tool | Minimum version | Used for |
|---|---|---|
| Docker + Docker Compose | Docker 24+, Compose v2 | running the full stack |
| Node.js + npm | Node 20+ / npm 10+ | the frontend (dev server and tests) |
| Python | 3.10+ | *optional* — running backend tests outside Docker |
| `git` | — | cloning the repository |

You do **not** need to install PostgreSQL, Temporal, Redis, or MinIO — they all ship in
the Compose file.

---

## 2. Quick start (Docker)

```bash
git clone <repo-url> FlowOps
cd FlowOps

cp .env.example .env          # adjust secrets for anything beyond local development
docker compose up -d          # postgres · temporal · redis · minio · api · worker · agent
docker compose exec api python -m moiraflow_api.scripts.create_admin   # seed the first admin
```

Then start the frontend:

```bash
cd services/frontend
npm install
npm run dev                   # http://localhost:5173
```

**Default admin:** `admin@moiraflow.local` / `admin`
(override with `ADMIN_EMAIL` / `ADMIN_PASSWORD` in `.env` *before* running `create_admin`).

---

## 3. URLs and ports

| Service | Default URL | Notes |
|---|---|---|
| **Web UI** | http://localhost:5173 | sign in, author and launch workflows, watch live executions |
| **API (Swagger)** | http://localhost:8001/api/v1/docs | authorize with your token (the *Authorize* button) |
| **API health** | http://localhost:8001/healthz | liveness; `/readyz` and `/metrics` are also exposed |
| **Temporal UI** | http://localhost:8233 | inspect durable workflow executions |
| **MinIO console** | http://localhost:9001 | `minioadmin` / `minioadmin` |

Host-side ports are configurable in `.env` (the value to the left of the colon in
Compose). The defaults are chosen to avoid clashing with the usual 5432 / 8000 / 6379.

---

## 4. Environment variables (`.env`)

| Variable | Default | Description |
|---|---|---|
| `POSTGRES_USER` / `PASSWORD` / `DB` | `moiraflow` | database credentials |
| `DATABASE_URL` | `postgresql+psycopg://moiraflow:moiraflow@postgres:5432/moiraflow` | DSN used by api/worker (note the **internal** host `postgres`) |
| `TEMPORAL_HOST` | `temporal:7233` | Temporal gRPC endpoint (internal host) |
| `TEMPORAL_NAMESPACE` | `default` | Temporal namespace |
| `MOIRAFLOW_TASK_QUEUE` | `moiraflow-server` | the server-side worker's task queue |
| `REDIS_URL` | `redis://redis:6379/0` | event feed (Redis Streams) |
| `S3_ENDPOINT` | `http://minio:9000` | **internal** MinIO endpoint (the worker uploads artifacts here) |
| `S3_PUBLIC_ENDPOINT` | `http://localhost:9000` | **public** MinIO endpoint (presigned download URLs for the browser) |
| `S3_ACCESS_KEY` / `SECRET_KEY` / `BUCKET` | `minioadmin` / `minioadmin` / `moiraflow-artifacts` | object-storage credentials and bucket |
| `JWT_SECRET` | *dev value* | token-signing secret — **change in production** |
| `JWT_EXPIRES_SECONDS` | `3600` | token lifetime |
| `SECRETS_MASTER_KEY` | *dev value* | secrets master key + Temporal payload codec — **change in production** |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | `admin@moiraflow.local` / `admin` | admin seeded by `create_admin` |
| `API_PORT` | `8001` | host port for the API |
| `POSTGRES_PORT` | `5433` | host port for Postgres |
| `REDIS_PORT` | `6380` | host port for Redis |
| `TEMPORAL_GRPC_PORT` / `TEMPORAL_UI_PORT` | `7233` / `8233` | host ports for Temporal |
| `MINIO_PORT` / `MINIO_CONSOLE_PORT` | `9000` / `9001` | host ports for MinIO |
| `CORS_ORIGINS` | `http://localhost:5173,...` | origins allowed to call the API from the SPA |

### Optional: mTLS to Temporal (docs 05 §5)

The agent / worker / API → Temporal transport can run over mutual TLS. It stays inert
unless configured, so in development everything connects in plaintext to the local dev
server (which has no TLS). Each value may be inline PEM or a path to a PEM file:

| Variable | Description |
|---|---|
| `MOIRAFLOW_TLS_SERVER_CA` | CA that signed the Temporal server certificate |
| `MOIRAFLOW_TLS_CLIENT_CERT` | client certificate (issued by the internal CA) |
| `MOIRAFLOW_TLS_CLIENT_KEY` | client private key |
| `MOIRAFLOW_TLS_SERVER_NAME` | server name override (SNI) |

> The end-to-end mTLS handshake requires a **TLS-enabled Temporal**. The
> `temporal server start-dev` used in Compose does **not** support TLS — enabling it
> means migrating to `temporalio/auto-setup`, which is not yet included.

---

## 5. Verifying the installation

```bash
# API health
curl -s localhost:8001/healthz            # -> {"status":"ok"}

# sign in
curl -s localhost:8001/api/v1/auth/login -H 'content-type: application/json' \
  -d '{"email":"admin@moiraflow.local","password":"admin"}'

# end-to-end smoke test (30 checks against the running stack)
bash scripts/e2e_smoke.sh
```

`e2e_smoke.sh` exercises the whole platform: authentication, catalog/simulate, secrets,
workflow create/export, launch with live projection, artifacts in MinIO, cancel, user
management, the full remote-agent lifecycle, and the audit log. It exits non-zero if any
check fails.

---

## 6. Development setup

### Backend (`services/api`, `services/worker`)

Tests run **without an editable install** (pytest's `pythonpath` config); the
dependencies are available system-wide. From each service directory:

```bash
cd services/api          # or services/worker
python3 -m pytest -q                          # tests
python3 -m ruff check moiraflow_api tests     # lint
python3 -m black --check moiraflow_api tests  # formatting
python3 -m mypy moiraflow_api                 # types (strict)
```

> Your local Python may be 3.10 even though the images use 3.12 — the code runs on both
> (thanks to `from __future__ import annotations`).

### Frontend (`services/frontend`)

```bash
cd services/frontend
npm install
npm run dev            # dev server with hot reload (http://localhost:5173)
npm run build          # tsc -b + vite build (type-check + production bundle)
npm test               # Vitest (builder logic, API client, RBAC helpers)
npm run test:watch     # Vitest in watch mode
```

The frontend's API client targets `VITE_API_URL` (default `http://localhost:8001/api/v1`).

---

## 7. Common operations

```bash
# status / logs
docker compose ps
docker compose logs -f api          # or worker / temporal / redis / ...

# REBUILD after a backend code change (required — the code is baked into the image)
docker compose up -d --build api worker

# restart a service (no rebuild — only if you did not change code)
docker compose restart api

# stop / tear down
docker compose down                 # stop the containers
docker compose down -v              # ... and drop the volumes (DB / MinIO reset to empty)
```

### Resetting test data (keeping the stack up)

Delete test executions and workflows directly in the database (in FK-safe order),
keeping one workflow as an example:

```bash
docker compose exec -T postgres psql -U moiraflow -d moiraflow <<'SQL'
BEGIN;
CREATE TEMP TABLE del AS SELECT id FROM workflows WHERE name <> 'health_check';
DELETE FROM artifacts        WHERE execution_id IN (SELECT id FROM executions WHERE workflow_id IN (SELECT id FROM del));
DELETE FROM execution_events WHERE execution_id IN (SELECT id FROM executions WHERE workflow_id IN (SELECT id FROM del));
DELETE FROM job_executions   WHERE execution_id IN (SELECT id FROM executions WHERE workflow_id IN (SELECT id FROM del));
UPDATE executions SET replay_of_execution_id = NULL WHERE workflow_id IN (SELECT id FROM del);
DELETE FROM executions       WHERE workflow_id IN (SELECT id FROM del);
UPDATE workflows SET active_version_id = NULL WHERE id IN (SELECT id FROM del);
DELETE FROM workflow_versions WHERE workflow_id IN (SELECT id FROM del);
DELETE FROM workflows         WHERE id IN (SELECT id FROM del);
COMMIT;
SQL
```

---

## 8. Common installation problems

| Symptom | Cause / fix |
|---|---|
| A host port is already in use | change the matching `*_PORT` in `.env`, then `docker compose up -d` |
| Backend code change isn't reflected | the code is baked into the image — `docker compose up -d --build api worker` |
| `create_admin` says the admin already exists | harmless if you ran it before; the admin is already seeded |
| API doesn't respond right after `--build` | give it ~6s to start, then retry. A transient 404 immediately after the container is recreated clears itself on retry |
| Frontend can't reach the API (CORS) | make sure `CORS_ORIGINS` includes `http://localhost:5173`, and `VITE_API_URL` points at the API port (`8001`) |
| Temporal "not ready" at startup | the worker retries the connection ~30 times — wait for Temporal to finish booting |

For **usage** problems (workflows that won't advance, replay, logs, and so on), see the
**[User Guide → Troubleshooting](USER-GUIDE.md#9-troubleshooting)**.
