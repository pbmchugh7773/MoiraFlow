# MoiraFlow

[![CI](https://github.com/pbmchugh7773/MoiraFlow/actions/workflows/ci.yml/badge.svg)](https://github.com/pbmchugh7773/MoiraFlow/actions/workflows/ci.yml)
[![License: BSL 1.1](https://img.shields.io/badge/license-BSL%201.1-blue.svg)](docs/06-roadmap-y-adr.md)
![Python 3.12](https://img.shields.io/badge/python-3.12-3776AB?logo=python&logoColor=white)
![React 18](https://img.shields.io/badge/react-18-61DAFB?logo=react&logoColor=black)
![Engine: Temporal](https://img.shields.io/badge/engine-Temporal-000000)

An **Automation Operating System** for SMBs: workflows are defined **as code** (YAML/JSON),
executed as **durable DAGs** on [Temporal](https://temporal.io), with jobs running
server-side or on remote "thin agents".

**Built:** workflow validation + immutable content-hashed versioning · Temporal interpreter
(`command` / `rest` / `sql`) · idempotent executions with live event feed
(worker→Redis→WebSocket) · JWT auth + RBAC · cron triggers (Temporal Schedules) ·
`simulate` (dry-run) + machine-readable catalogs · users / secrets / workflow management ·
`job_executions`, `cancel`, append-only `audit_log` · **artifacts in MinIO** (declare files →
upload → presigned download) · **command isolation** (non-root, rlimits, ephemeral workdir) ·
the **secure remote agent** (enroll→approve→revoke lifecycle, internal CA, per-agent envelope
encryption, revocation gate) · and a React UI for all of it.

> The Moirai wove the thread of destiny — MoiraFlow weaves the threads of your workflows'
> durable execution. Design docs live in [`docs/`](docs/) (Spanish; product/code in English).

📖 **Guides:** [Installation & Setup](docs/INSTALLATION.md) ·
[User Guide & Troubleshooting](docs/USER-GUIDE.md)

## Quickstart (Docker)

```bash
cp .env.example .env                 # adjust secrets for anything beyond local dev
docker compose up -d                 # postgres · temporal · redis · minio · api · worker · agent
docker compose exec api python -m moiraflow_api.scripts.create_admin   # first admin
```

Then start the web UI (Vite dev server):

```bash
cd services/frontend && npm install && npm run dev   # http://localhost:5173
```

Open:

| What | URL | Notes |
|------|-----|-------|
| **Web UI** | http://localhost:5173 | log in, author/launch workflows, watch executions live |
| **API docs (Swagger)** | http://localhost:8001/api/v1/docs | log in, then `Authorize` with the token |
| **Temporal UI** | http://localhost:8233 | watch workflow executions |
| **MinIO console** | http://localhost:9001 | `minioadmin` / `minioadmin` |

Default admin: `admin@moiraflow.local` / `admin` (override via `ADMIN_EMAIL`/`ADMIN_PASSWORD`).
The UI reads `VITE_API_URL` (defaults to the compose API port `8001`).

### Try it (curl)

```bash
# 1) login
TOKEN=$(curl -s localhost:8001/api/v1/auth/login \
  -H 'content-type: application/json' \
  -d '{"email":"admin@moiraflow.local","password":"admin"}' | jq -r .access_token)

# 2) create a workflow (validated + versioned)
WF='{"apiVersion":"moiraflow/v1","kind":"Workflow","metadata":{"name":"hello"},
"spec":{"trigger":{"type":"manual"},"jobs":[{"id":"greet","type":"command",
"with":{"command":"echo hello"},"outputs":{"done":"yes"}}]}}'
WID=$(curl -s localhost:8001/api/v1/workflows -H "authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' -d "{\"content\":$(jq -Rs . <<<"$WF"),\"format\":\"json\"}" | jq -r .id)

# 3) launch it — runs durably on Temporal (watch it in the Temporal UI)
curl -s localhost:8001/api/v1/executions -H "authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' -d "{\"workflow_id\":\"$WID\"}" | jq
```

Ports are configurable in `.env` (defaults avoid clashing with common 5432/8000).

### End-to-end smoke

With the stack up + the admin seeded, `scripts/e2e_smoke.sh` exercises the whole
platform against the running API — health, auth, catalog/simulate, secrets, workflow
create/export, launch + live projection (`job_executions`, events), artifacts in MinIO
(upload → presigned download), cancel, user management, the full remote-agent lifecycle
(enroll → register → CA-signed cert → revocation gate), and the audit log:

```bash
bash scripts/e2e_smoke.sh        # 30 checks; exits non-zero on any failure
```

## Architecture

MoiraFlow does **not** build its own execution engine — it runs on Temporal. A single
generic interpreter workflow resolves each definition's DAG and dispatches every job as
an activity. See [`CLAUDE.md`](CLAUDE.md) for the big picture and [`docs/`](docs/) for the
full design + ADRs.

## Development

Each service is a Python package tested without an editable install:

```bash
cd services/api    && python3 -m pytest -q   # + ruff/black/mypy --strict
cd services/worker && python3 -m pytest -q
```

Schema changes go through Alembic:
`docker compose exec api alembic revision --autogenerate -m "..."` (review, commit).

## License

Open core; core under **BSL 1.1** (converts to Apache 2.0). See [ADR-0009](docs/06-roadmap-y-adr.md).
