# MoiraFlow

An **Automation Operating System** for SMBs: workflows are defined **as code** (YAML/JSON),
executed as **durable DAGs** on [Temporal](https://temporal.io), with jobs running
server-side or (later) on remote "thin agents".

> The Moirai wove the thread of destiny — MoiraFlow weaves the threads of your workflows'
> durable execution. Design docs live in [`docs/`](docs/) (Spanish; product/code in English).

## Quickstart (Docker)

```bash
cp .env.example .env                 # adjust secrets for anything beyond local dev
docker compose up -d                 # postgres · temporal · redis · minio · api · worker
docker compose exec api python -m moiraflow_api.scripts.create_admin   # first admin
```

Then open:

| What | URL | Notes |
|------|-----|-------|
| **API docs (Swagger)** | http://localhost:8001/api/v1/docs | log in, then `Authorize` with the token |
| **Temporal UI** | http://localhost:8233 | watch workflow executions |
| **MinIO console** | http://localhost:9001 | `minioadmin` / `minioadmin` |

Default admin: `admin@moiraflow.local` / `admin` (override via `ADMIN_EMAIL`/`ADMIN_PASSWORD`).

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
