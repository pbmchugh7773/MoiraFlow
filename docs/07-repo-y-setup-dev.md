# 07 — Estructura de Repositorio y Setup de Desarrollo

> Estado: Borrador para arranque · Fecha: 2026-06-24
> Objetivo: que un solo dev (o la IA) pueda clonar, `docker compose up` y empezar.

## 1. Stack confirmado

| Capa | Tecnología |
|------|-----------|
| Frontend | React + TypeScript + Vite + React Flow |
| API | Python 3.12 + FastAPI + Pydantic v2 + Uvicorn |
| Motor | Temporal (server + SDK Python) |
| Worker/Agente | Python (Temporal worker) |
| Base de datos | PostgreSQL 16 + Alembic (migraciones) + SQLAlchemy 2 |
| Cola pub/sub UI | Redis 7 |
| Artefactos | MinIO (S3 compatible) |
| Auth | JWT (argon2id para hashing) |
| Tests | pytest (backend), Vitest/Playwright (frontend) |
| Lint/format | ruff + black + mypy (py), eslint + prettier (ts) |
| Orquestación local | Docker Compose |

## 2. Estructura del monorepo

```
moiraflow/
├─ docker-compose.yml            # stack completo para dev local
├─ .env.example                  # variables (DB, Temporal, MinIO, JWT secret...)
├─ README.md                     # quickstart
├─ docs/                         # esta documentación
│
├─ services/
│  ├─ api/                       # FastAPI
│  │  ├─ moiraflow_api/
│  │  │  ├─ main.py
│  │  │  ├─ config.py
│  │  │  ├─ db/                  # SQLAlchemy models, session
│  │  │  ├─ migrations/          # Alembic
│  │  │  ├─ auth/                # JWT, RBAC, password hashing
│  │  │  ├─ routers/             # workflows, executions, agents, catalog...
│  │  │  ├─ schemas/             # Pydantic (request/response)
│  │  │  ├─ services/            # lógica (workflow svc, execution svc...)
│  │  │  └─ workflow/            # parser + JSON Schema + validate/simulate
│  │  ├─ tests/
│  │  └─ pyproject.toml
│  │
│  ├─ worker/                    # Temporal workflows + activities (server-side)
│  │  ├─ moiraflow_worker/
│  │  │  ├─ workflows/           # el "interpreter" del DAG
│  │  │  ├─ activities/          # rest_job, sql_job, command_job
│  │  │  ├─ context.py           # contexto compartido
│  │  │  └─ runtime.py           # registro de workflows/activities
│  │  ├─ tests/
│  │  └─ pyproject.toml
│  │
│  ├─ agent/                     # agente delgado (Temporal worker remoto)
│  │  ├─ moiraflow_agent/
│  │  │  ├─ main.py              # conexión mTLS + task queue agent-<id>
│  │  │  ├─ enroll.py            # enrolamiento/certificados
│  │  │  ├─ activities/          # command_job (con aislamiento)
│  │  │  └─ secrets.py           # descifrado en memoria + redacción
│  │  ├─ Dockerfile
│  │  └─ pyproject.toml
│  │
│  └─ frontend/                  # React + TS + Vite + React Flow
│     ├─ src/
│     │  ├─ pages/               # Login, Workflows, Editor, Executions, Agents
│     │  ├─ components/          # DAG viewer, log stream, ...
│     │  ├─ api/                 # cliente generado del OpenAPI
│     │  └─ lib/
│     ├─ package.json
│     └─ vite.config.ts
│
├─ packages/
│  └─ shared-schemas/            # JSON Schema del workflow + tipos compartidos
│
└─ deploy/
   ├─ docker/                    # Dockerfiles por servicio
   └─ ca/                        # scripts CA interna (certs de agente)
```

> Un solo dev: el monorepo simplifica versionado y refactors. Cada servicio
> conserva su propio `pyproject.toml`/`package.json` para poder separarlos después.

## 3. `docker-compose` (servicios)

- `postgres` (16) — volumen persistente.
- `temporal` + `temporal-ui` — motor y panel de Temporal.
- `redis` (7) — pub/sub UI.
- `minio` + consola — artefactos.
- `api` — FastAPI (depende de postgres, temporal, redis, minio).
- `worker` — Temporal worker server-side.
- `frontend` — Vite dev server (o build estático servido por la API en prod).
- `agent` — opcional en dev (se puede correr el worker local primero; ver
  `05-...md` §6 plan B).

## 4. Variables de entorno (`.env.example`)
```
# Database
POSTGRES_USER=moiraflow
POSTGRES_PASSWORD=changeme
POSTGRES_DB=moiraflow
DATABASE_URL=postgresql+psycopg://moiraflow:changeme@postgres:5432/moiraflow

# Temporal
TEMPORAL_HOST=temporal:7233
TEMPORAL_NAMESPACE=default

# Redis
REDIS_URL=redis://redis:6379/0

# MinIO / S3
S3_ENDPOINT=http://minio:9000
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin
S3_BUCKET=moiraflow-artifacts

# Auth / cifrado
JWT_SECRET=change-this
SECRETS_MASTER_KEY=change-this-32-bytes-base64

# Agente / CA
CA_CERT_PATH=/deploy/ca/ca.crt
CA_KEY_PATH=/deploy/ca/ca.key
```

## 5. Quickstart (objetivo del Hito 0)
```bash
git clone <repo> && cd moiraflow
cp .env.example .env            # ajustar secretos
docker compose up -d            # levanta todo
# aplicar migraciones
docker compose exec api alembic upgrade head
# crear usuario admin inicial
docker compose exec api python -m moiraflow_api.scripts.create_admin
# UI:        http://localhost:5173
# API docs:  http://localhost:8000/api/v1/docs
# Temporal:  http://localhost:8080
# MinIO:     http://localhost:9001
```

## 6. Flujo de trabajo de desarrollo
- Rama por feature; PR con CI (lint + type-check + tests) en verde antes de merge.
- Migraciones: `alembic revision --autogenerate -m "..."`, revisar y commitear.
- Cliente del frontend generado desde el OpenAPI de la API (contrato único).
- Tests mínimos por capa: validación de schema, interpreter del DAG (con Temporal
  test environment), endpoints de la API, e2e ligero del flujo crear→lanzar→ver.

## 7. Primeros tickets sugeridos (arranque inmediato)
1. Scaffold del monorepo + `docker-compose` levantando los 4 servicios base.
2. Migración Alembic inicial con el esquema de `03-modelo-datos.md`.
3. JSON Schema del workflow + endpoint `POST /workflows/validate`.
4. Temporal Workflow "interpreter" mínimo: ejecuta un DAG de 2 jobs `rest`.
5. Endpoint `POST /executions` + persistencia de ejecución/eventos.
6. Página React de lista de ejecuciones con stream de logs.

> A partir de aquí se sigue el roadmap de `06-roadmap-y-adr.md`.
