# MoiraFlow — Installation & Setup Guide

This guide covers everything needed to run MoiraFlow: a single-host Docker setup for
development, a distributed multi-server deployment for production, scaling, database
migrations, and installing remote agents.

The platform is a small set of stateless services around shared infrastructure:

```
                         ┌──────────────┐
        browser ───────► │  Frontend    │  (static SPA, Vite/React)
                         └──────┬───────┘
                                │ HTTPS (VITE_API_URL)
                         ┌──────▼───────┐        ┌───────────┐
                         │     API      │◄──────►│ PostgreSQL│  metadata, audit, secrets
                         │  (FastAPI)   │        └───────────┘  (source of truth)
                         └──┬────────┬──┘
              starts/queries│        │ subscribes (events)
                            │        └──────────► ┌───────────┐
                         ┌──▼────────┐            │   Redis   │  durable event stream (UI feed)
                         │  Temporal │◄───────────┤  Streams  │
                         │  (engine) │   polls    └───────────┘
                         └──┬────────┘
              task queues   │
            ┌───────────────┼────────────────┐
       ┌────▼─────┐    ┌────▼─────┐      ┌────▼──────────┐
       │  Worker  │    │  Worker  │ ...  │ Remote Agent  │  command jobs on a customer host
       │ (server) │    │ (server) │      │ (agent-<id>)  │  (mTLS, no DB/secret access)
       └────┬─────┘    └──────────┘      └───────────────┘
            │ artifacts
       ┌────▼─────┐
       │  MinIO   │  artifact storage (S3-compatible)
       └──────────┘
```

Everything is configured through environment variables, so the same images run in a
single container or spread across many servers — only the endpoints change.

> **About the container images:** the code for `api`, `worker`, and `agent` is **baked
> into the image at build time** — there is no source volume mounted. If you change
> backend code, you must **rebuild the image** (`docker compose up -d --build <service>`)
> for the change to take effect. The frontend runs with hot reload via `npm run dev`.

---

## 1. Prerequisites

| Tool | Minimum version | Used for |
|---|---|---|
| Docker + Docker Compose | Docker 24+, Compose v2 | running the stack |
| Node.js + npm | Node 20+ / npm 10+ | the frontend (dev server and tests) |
| Python | 3.10+ | *optional* — running backend tests outside Docker |
| `git` | — | cloning the repository |

You do **not** need to install PostgreSQL, Temporal, Redis, or MinIO — they ship in the
Compose file. For production you may run those as managed services instead (see §10).

---

## 2. Quick start (single host, Docker)

```bash
git clone <repo-url> FlowOps
cd FlowOps

cp .env.example .env          # adjust secrets for anything beyond local development
docker compose up -d          # postgres · temporal · redis · minio · api · worker · agent
docker compose exec api python -m moiraflow_api.scripts.create_admin   # seed the first admin
```

The API container runs `alembic upgrade head` on startup, so the database schema is
created automatically — no manual migration step in development.

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
Compose). The defaults avoid clashing with the usual 5432 / 8000 / 6379.

---

## 4. Environment variables (`.env`)

Each variable is read by one or more services. The **internal** hostnames (`postgres`,
`temporal`, `redis`, `minio`) only resolve inside the Compose network — in a multi-server
deployment you replace them with real hostnames (see §10).

| Variable | Default | Read by | Description |
|---|---|---|---|
| `POSTGRES_USER` / `PASSWORD` / `DB` | `moiraflow` | postgres | database credentials |
| `DATABASE_URL` | `postgresql+psycopg://moiraflow:moiraflow@postgres:5432/moiraflow` | api, worker | DSN (worker needs it to resolve `secret://`) |
| `TEMPORAL_HOST` | `temporal:7233` | api, worker, agent | Temporal gRPC endpoint |
| `TEMPORAL_NAMESPACE` | `default` | api, worker, agent | Temporal namespace |
| `MOIRAFLOW_TASK_QUEUE` | `moiraflow-server` | api, worker | the server worker's task queue |
| `MOIRAFLOW_AGENT_QUEUE` | `agent-local` | agent | the queue the agent polls (set to `agent-<id>` for a remote agent) |
| `REDIS_URL` | `redis://redis:6379/0` | api, worker | event feed (Redis Streams) |
| `S3_ENDPOINT` | `http://minio:9000` | worker | **internal** MinIO endpoint (artifact uploads) |
| `S3_PUBLIC_ENDPOINT` | `http://localhost:9000` | api | **public** MinIO endpoint (presigned download URLs) |
| `S3_ACCESS_KEY` / `SECRET_KEY` / `BUCKET` | `minioadmin` / `minioadmin` / `moiraflow-artifacts` | api, worker | object-storage credentials and bucket |
| `JWT_SECRET` | *dev value* | api | token-signing secret — **change in production** |
| `JWT_EXPIRES_SECONDS` | `3600` | api | token lifetime |
| `SECRETS_MASTER_KEY` | *dev value* | api, worker, agent | secrets master key + Temporal payload codec — **change in production** |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | `admin@moiraflow.local` / `admin` | api | admin seeded by `create_admin` |
| `CORS_ORIGINS` | `http://localhost:5173,...` | api | origins allowed to call the API from the SPA |
| `API_PORT` / `POSTGRES_PORT` / `REDIS_PORT` | `8001` / `5433` / `6380` | compose | host ports |
| `TEMPORAL_GRPC_PORT` / `TEMPORAL_UI_PORT` | `7233` / `8233` | compose | host ports |
| `MINIO_PORT` / `MINIO_CONSOLE_PORT` | `9000` / `9001` | compose | host ports |

### mTLS to Temporal (optional, docs 05 §5)

The agent / worker / API → Temporal transport can run over mutual TLS. It stays inert
unless configured, so in development everything connects in plaintext. Each value may be
inline PEM or a path to a PEM file:

| Variable | Read by | Description |
|---|---|---|
| `MOIRAFLOW_TLS_SERVER_CA` | api, worker, agent | CA that signed the Temporal server certificate |
| `MOIRAFLOW_TLS_CLIENT_CERT` | api, worker, agent | client certificate (issued by the internal CA) |
| `MOIRAFLOW_TLS_CLIENT_KEY` | api, worker, agent | client private key |
| `MOIRAFLOW_TLS_SERVER_NAME` | api, worker, agent | server name override (SNI) |

> The end-to-end mTLS handshake requires a **TLS-enabled Temporal**. The
> `temporal server start-dev` used in Compose does **not** support TLS — enabling it means
> migrating to `temporalio/auto-setup`, which is not yet included. The client-side wiring
> and certificate issuance are in place; only the TLS-enabled server is pending.

---

## 5. Verifying the installation

```bash
curl -s localhost:8001/healthz            # -> {"status":"ok"}
curl -s localhost:8001/api/v1/auth/login -H 'content-type: application/json' \
  -d '{"email":"admin@moiraflow.local","password":"admin"}'
bash scripts/e2e_smoke.sh                  # 30 end-to-end checks against the running stack
```

`e2e_smoke.sh` exercises authentication, catalog/simulate, secrets, workflow
create/export, launch with live projection, artifacts, cancel, user management, the full
remote-agent lifecycle, and the audit log. It exits non-zero on any failure.

### Test SFTP server (for the `file_transfer` SFTP path)

A test SFTP server is defined under the `test` Compose profile (it is **not** part of the
default stack). It serves the files in `scripts/sftp-seed/` to `testuser` / `testpass`:

```bash
docker compose --profile test up -d sftp     # reachable from the worker as sftp:22
```

Then a `file_transfer` job can pull from `sftp://testuser@sftp/upload/<file>` with
`credentials` resolving to `{"username":"testuser","password":"testpass"}`.

---

## 6. Database and migrations

The schema is managed with **Alembic**. The API image runs `alembic upgrade head` on
startup, so a fresh stack is migrated automatically.

```bash
# apply migrations manually (e.g. against an external database)
docker compose exec api alembic upgrade head

# after changing a SQLAlchemy model, generate a migration, review it, and commit it
docker compose exec api alembic revision --autogenerate -m "add X"
docker compose exec api alembic upgrade head
```

Never hand-edit the schema in any environment — always go through Alembic. Back up the
PostgreSQL volume (`postgres-data`) before upgrades in production.

---

## 7. Development setup

### Backend (`services/api`, `services/worker`)

Tests run **without an editable install** (pytest's `pythonpath` config). From each
service directory:

```bash
cd services/api          # or services/worker
python3 -m pytest -q                          # tests
python3 -m ruff check moiraflow_api tests     # lint
python3 -m black --check moiraflow_api tests  # formatting
python3 -m mypy moiraflow_api                 # types (strict)
```

> Your local Python may be 3.10 even though the images use 3.12 — the code runs on both.

### Frontend (`services/frontend`)

```bash
cd services/frontend
npm install
npm run dev            # dev server with hot reload (http://localhost:5173)
npm run build          # tsc -b + vite build (type-check + production bundle)
npm test               # Vitest (builder logic, API client, RBAC helpers)
```

The frontend's API client targets `VITE_API_URL` (default `http://localhost:8001/api/v1`).

---

## 8. Common operations

```bash
docker compose ps
docker compose logs -f api          # or worker / temporal / redis / ...

# REBUILD after a backend code change (required — the code is baked into the image)
docker compose up -d --build api worker

docker compose restart api          # restart (no rebuild — only if you didn't change code)
docker compose down                 # stop the containers
docker compose down -v              # ... and drop the volumes (DB / MinIO reset to empty)
```

### Resetting test data (keeping the stack up)

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

## 9. Scaling and multi-server deployment

All services are **stateless** (the truth lives in PostgreSQL / Temporal / MinIO), so they
scale horizontally and can be split across hosts. There is nothing to configure beyond
pointing each service's environment at the right endpoints.

### 9.1 Scaling workers

The server worker is the unit of execution throughput. Run more replicas — they all poll
the same Temporal task queue and share the load automatically:

```bash
docker compose up -d --scale worker=4        # 4 server workers
```

In Kubernetes/Nomad this is just `replicas: 4` on the worker Deployment. Workers hold no
local state; add or remove them freely. The API is also stateless and can run behind a
load balancer with multiple replicas.

> **Event subscriber note:** the API's live-event subscriber uses a Redis **consumer
> group**, so running multiple API replicas is safe — each event is delivered to exactly
> one replica, which persists it and fans it out over its own WebSocket connections.

### 9.2 Splitting components across servers

Replace the internal Compose hostnames with the real ones, per service:

| Component | Move it by setting | On which services |
|---|---|---|
| PostgreSQL | `DATABASE_URL` → managed Postgres host | api, worker |
| Temporal | `TEMPORAL_HOST` → Temporal cluster host | api, worker, agent |
| Redis | `REDIS_URL` → managed Redis host | api, worker |
| MinIO / S3 | `S3_ENDPOINT` (internal) + `S3_PUBLIC_ENDPOINT` (browser) | worker / api |
| API | run behind a reverse proxy (TLS termination); set `CORS_ORIGINS` and the frontend's `VITE_API_URL` | — |

A common production layout: a managed PostgreSQL, a Temporal cluster (or Temporal Cloud),
a managed Redis, S3 (or MinIO) for artifacts, API + worker replicas behind a load
balancer, and the frontend served as static assets from a CDN.

### 9.3 What each role needs

| Service | Needs | Must **not** have |
|---|---|---|
| **API** | DB, Temporal, Redis, MinIO (public endpoint), JWT/secret keys | — |
| **Server worker** | DB (for `secret://`), Temporal, Redis, MinIO (internal endpoint), `SECRETS_MASTER_KEY` | — |
| **Remote agent** | Temporal endpoint, its task queue, mTLS certs | **no** DB access, **no** tenant credentials, **no** secrets master key (by design — ADR-0013) |

---

## 10. Production hardening checklist

- [ ] Set strong `JWT_SECRET` (≥32 bytes) and a real `SECRETS_MASTER_KEY` — rotating the
      latter requires re-encrypting stored secrets, so choose it carefully.
- [ ] Change the MinIO/S3 credentials (`S3_ACCESS_KEY` / `S3_SECRET_KEY`) and the Postgres
      password; do **not** ship the dev defaults.
- [ ] Terminate TLS at a reverse proxy in front of the API; set `CORS_ORIGINS` to your real
      UI origin(s) and `VITE_API_URL` to the public API URL.
- [ ] Use a durable Temporal deployment (cluster or Temporal Cloud) rather than the dev
      server; enable mTLS and populate the `MOIRAFLOW_TLS_*` vars.
- [ ] Use managed/replicated PostgreSQL and Redis; back up the database regularly.
- [ ] Run multiple API and worker replicas behind a load balancer.
- [ ] Restrict network access so only the API is publicly reachable; keep Postgres,
      Temporal, Redis, and MinIO on a private network.
- [ ] Seed a real admin (`ADMIN_EMAIL` / `ADMIN_PASSWORD`) and remove the default one.

---

## 11. Installing a remote agent

A **remote agent** runs `command` jobs on a customer/edge machine. It connects only to
Temporal (over mTLS), never to your database or secrets. The control plane lives in the
API (enroll → register → approve → revoke); the agent process is the `moiraflow_worker.agent`
runtime on a dedicated task queue.

> **What works today:** the enrollment lifecycle, CA-signed certificate issuance, the
> revocation gate, and the local agent (`agent-local`, the Compose `agent` service). The
> **end-to-end mTLS handshake** additionally requires a TLS-enabled Temporal (the dev
> server has none) — see the note in §4.

### 11.1 Enroll (admin)

In the UI go to **Agents → Enroll**, or via API:

```bash
curl -s -X POST localhost:8001/api/v1/agents/enroll "${AUTH[@]}"
# -> { "enrollment_token": "...", "temporal_host": "temporal:7233", "expires_in": 600 }
```

The token is **single-use and short-lived**. Hand it to the agent host out-of-band.

### 11.2 Register (on the agent host)

Generate a keypair + CSR, then register with the enrollment token:

```bash
openssl genrsa -out agent.key 2048
openssl req -new -key agent.key -subj "/CN=edge-1" -out agent.csr

curl -s -X POST localhost:8001/api/v1/agents/register \
  -H 'content-type: application/json' \
  -d "{\"token\":\"<enrollment_token>\",\"name\":\"edge-1\",
       \"public_key\":\"$(awk '{printf "%s\\n",$0}' agent.key.pub 2>/dev/null)\",
       \"csr\":\"$(awk '{printf "%s\\n",$0}' agent.csr)\"}"
# -> { "agent_id": "...", "task_queue": "agent-<id>", "status": "pending_approval",
#      "certificate": "-----BEGIN CERTIFICATE-----...", "ca_certificate": "...",
#      "fingerprint": "..." }
```

Save the returned `certificate`, `ca_certificate`, and your `agent.key`. The agent is
**not** authorized yet (`pending_approval`) — no trust-on-first-use.

### 11.3 Approve (admin)

In the UI **Agents → Approve**, or:

```bash
curl -s -X POST localhost:8001/api/v1/agents/<agent_id>/approve "${AUTH[@]}"
```

### 11.4 Run the agent

Point the agent at the central Temporal, its assigned queue, and its mTLS material:

```bash
docker run --rm \
  -e TEMPORAL_HOST=temporal.yourco.com:7233 \
  -e TEMPORAL_NAMESPACE=default \
  -e MOIRAFLOW_AGENT_QUEUE=agent-<agent_id> \
  -e MOIRAFLOW_TLS_SERVER_CA=/certs/ca.pem \
  -e MOIRAFLOW_TLS_CLIENT_CERT=/certs/agent.pem \
  -e MOIRAFLOW_TLS_CLIENT_KEY=/certs/agent.key \
  -e SECRETS_MASTER_KEY=<payload-codec-key> \
  -v $(pwd)/certs:/certs:ro \
  moiraflow-worker python -m moiraflow_worker.agent
```

The agent logs `agent connected to <host>; polling task queue 'agent-<id>'`.

### 11.5 Route jobs to it

In a workflow, mark a job to run on the agent and select which one:

```yaml
jobs:
  - id: on_prem_backup
    type: command
    run_on: agent
    agent_selector: { agent_id: "<agent_id>" }   # routes to agent-<id>
    with: { command: ./backup.sh }
```

### 11.6 Revoke

Revoking immediately blocks the agent (the revocation gate at `POST /agents/verify`):

```bash
curl -s -X POST localhost:8001/api/v1/agents/<agent_id>/revoke "${AUTH[@]}"
```

---

## 12. Common installation problems

| Symptom | Cause / fix |
|---|---|
| A host port is already in use | change the matching `*_PORT` in `.env`, then `docker compose up -d` |
| Backend code change isn't reflected | the code is baked into the image — `docker compose up -d --build api worker` |
| `create_admin` says the admin already exists | harmless if you ran it before; the admin is already seeded |
| API doesn't respond right after `--build` | give it ~6s to start, then retry. A transient 404 right after the container is recreated clears on retry |
| Frontend can't reach the API (CORS) | ensure `CORS_ORIGINS` includes the UI origin and `VITE_API_URL` points at the API |
| Temporal "not ready" at startup | the worker retries the connection ~30 times — wait for Temporal to boot |
| A worker can't reach Postgres/MinIO after splitting hosts | check `DATABASE_URL` / `S3_ENDPOINT` resolve from the worker's network |

For **usage** problems (workflows that won't advance, replay, logs, agents), see the
**[User Guide → Troubleshooting](USER-GUIDE.md#9-troubleshooting)**.
