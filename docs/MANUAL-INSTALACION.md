# MoiraFlow — Manual de Instalación y Setup

Guía completa para levantar MoiraFlow en local (Docker) y para preparar el entorno
de desarrollo. La plataforma corre como un stack de contenedores
(PostgreSQL · Temporal · Redis · MinIO · API · worker · agente) más el frontend
(Vite/React).

> **Importante sobre las imágenes:** el código de `api`, `worker` y `agent` se
> **hornea dentro de la imagen** en build time (no hay volumen montado). Si cambiás
> código de backend, tenés que **reconstruir la imagen** (`docker compose up -d --build <servicio>`)
> para verlo. El frontend, en cambio, corre con hot-reload via `npm run dev`.

---

## 1. Requisitos previos

| Herramienta | Versión mínima | Para qué |
|---|---|---|
| Docker + Docker Compose | Docker 24+, Compose v2 | levantar todo el stack |
| Node.js + npm | Node 20+ / npm 10+ | frontend (dev server + tests) |
| Python | 3.10+ | *opcional* — correr tests de backend fuera de Docker |
| `git` | — | clonar el repo |

No necesitás instalar PostgreSQL, Temporal, Redis ni MinIO: vienen en el compose.

---

## 2. Instalación rápida (Docker)

```bash
git clone <repo-url> FlowOps
cd FlowOps

cp .env.example .env          # ajustá secretos para cualquier cosa que no sea dev local
docker compose up -d          # postgres · temporal · redis · minio · api · worker · agent
docker compose exec api python -m moiraflow_api.scripts.create_admin   # primer admin
```

Luego levantá el frontend:

```bash
cd services/frontend
npm install
npm run dev                   # http://localhost:5173
```

**Admin por defecto:** `admin@moiraflow.local` / `admin`
(se puede cambiar con `ADMIN_EMAIL` / `ADMIN_PASSWORD` en `.env` antes de `create_admin`).

---

## 3. URLs y puertos

| Qué | URL por defecto | Notas |
|---|---|---|
| **Web UI** | http://localhost:5173 | login, autoría/lanzamiento, monitor en vivo |
| **API (Swagger)** | http://localhost:8001/api/v1/docs | autenticá con el token (botón *Authorize*) |
| **API health** | http://localhost:8001/healthz | liveness; `/readyz`, `/metrics` también |
| **Temporal UI** | http://localhost:8233 | ver workflows durables corriendo |
| **MinIO console** | http://localhost:9001 | `minioadmin` / `minioadmin` |

Los puertos del **host** son configurables en `.env` (la izquierda del `:` en compose).
Los defaults evitan choques con los típicos 5432/8000/6379.

---

## 4. Variables de entorno (`.env`)

| Variable | Default | Descripción |
|---|---|---|
| `POSTGRES_USER/PASSWORD/DB` | `moiraflow` | credenciales de la DB |
| `DATABASE_URL` | `postgresql+psycopg://moiraflow:moiraflow@postgres:5432/moiraflow` | DSN que usan api/worker (host **interno** `postgres`) |
| `TEMPORAL_HOST` | `temporal:7233` | endpoint gRPC de Temporal (host interno) |
| `TEMPORAL_NAMESPACE` | `default` | namespace |
| `MOIRAFLOW_TASK_QUEUE` | `moiraflow-server` | cola del worker server-side |
| `REDIS_URL` | `redis://redis:6379/0` | feed de eventos (Redis Streams) |
| `S3_ENDPOINT` | `http://minio:9000` | MinIO **interno** (el worker sube artifacts acá) |
| `S3_PUBLIC_ENDPOINT` | `http://localhost:9000` | MinIO **público** (URLs presignadas para el browser) |
| `S3_ACCESS_KEY/SECRET_KEY/BUCKET` | `minioadmin` / `minioadmin` / `moiraflow-artifacts` | credenciales + bucket |
| `JWT_SECRET` | *dev* | firma de tokens — **cambiar en prod** |
| `JWT_EXPIRES_SECONDS` | `3600` | vida del token |
| `SECRETS_MASTER_KEY` | *dev* | master key de secretos + codec de Temporal — **cambiar en prod** |
| `ADMIN_EMAIL/PASSWORD` | `admin@moiraflow.local` / `admin` | admin que crea `create_admin` |
| `API_PORT` | `8001` | puerto host del API |
| `POSTGRES_PORT` | `5433` | puerto host de Postgres |
| `REDIS_PORT` | `6380` | puerto host de Redis |
| `TEMPORAL_GRPC_PORT` / `TEMPORAL_UI_PORT` | `7233` / `8233` | puertos host de Temporal |
| `MINIO_PORT` / `MINIO_CONSOLE_PORT` | `9000` / `9001` | puertos host de MinIO |
| `CORS_ORIGINS` | `http://localhost:5173,...` | orígenes permitidos para el SPA |

### mTLS a Temporal (opcional, docs 05 §5)

El transporte agente/worker/API ↔ Temporal puede ir con mTLS. Inerte si no se setea
(en dev se conecta en texto plano al dev server, que no tiene TLS). Cada valor puede
ser PEM inline o una ruta a archivo PEM:

| Variable | Descripción |
|---|---|
| `MOIRAFLOW_TLS_SERVER_CA` | CA que firma el cert del servidor Temporal |
| `MOIRAFLOW_TLS_CLIENT_CERT` | cert cliente (emitido por el CA interno) |
| `MOIRAFLOW_TLS_CLIENT_KEY` | clave privada del cliente |
| `MOIRAFLOW_TLS_SERVER_NAME` | override del nombre del servidor (SNI) |

> El handshake mTLS end-to-end requiere un Temporal **con TLS habilitado**. El
> `temporal server start-dev` del compose **no** soporta TLS — para eso hay que migrar
> a `temporalio/auto-setup` (no incluido todavía).

---

## 5. Verificación

```bash
# salud del API
curl -s localhost:8001/healthz            # -> {"status":"ok"} (200)

# login
curl -s localhost:8001/api/v1/auth/login -H 'content-type: application/json' \
  -d '{"email":"admin@moiraflow.local","password":"admin"}'

# smoke end-to-end (30 chequeos contra el stack vivo)
bash scripts/e2e_smoke.sh
```

`e2e_smoke.sh` ejercita todo: auth, catálogo/simulate, secrets, crear/exportar
workflow, lanzar + proyección en vivo, artifacts en MinIO, cancel, gestión de
usuarios, ciclo completo del agente remoto y el audit log. Sale con código ≠0 si algo
falla.

---

## 6. Setup de desarrollo

### Backend (`services/api`, `services/worker`)

Los tests corren **sin install editable** (pytest `pythonpath`). Dependencias presentes
system-wide. Desde cada servicio:

```bash
cd services/api          # o services/worker
python3 -m pytest -q                          # tests
python3 -m ruff check moiraflow_api tests     # lint
python3 -m black --check moiraflow_api tests  # formato
python3 -m mypy moiraflow_api                 # tipos (strict)
```

> El Python local puede ser 3.10 aunque las imágenes usen 3.12 — el código corre en
> ambos (`from __future__ import annotations`).

### Frontend (`services/frontend`)

```bash
cd services/frontend
npm install
npm run dev            # dev server con hot-reload (http://localhost:5173)
npm run build          # tsc -b + vite build (verificación de tipos + bundle)
npm test               # Vitest (lógica del builder, cliente API, RBAC)
npm run test:watch     # Vitest en watch
```

El cliente API del frontend apunta a `VITE_API_URL` (default `http://localhost:8001/api/v1`).

---

## 7. Operaciones comunes

```bash
# ver estado / logs
docker compose ps
docker compose logs -f api          # o worker / temporal / redis ...

# RECONSTRUIR tras cambiar código de backend (imprescindible — el código está horneado)
docker compose up -d --build api worker

# reiniciar un servicio (sin reconstruir — solo si no cambiaste código)
docker compose restart api

# parar / borrar todo
docker compose down                 # para los contenedores
docker compose down -v              # + borra los volúmenes (DB/MinIO en cero)
```

### Reset de datos de prueba (manteniendo el stack)

Borrar ejecuciones/workflows de prueba en la DB (orden seguro de FKs), conservando uno:

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

## 8. Problemas de instalación frecuentes

| Síntoma | Causa / solución |
|---|---|
| Un puerto del host ya está en uso | cambiá el `*_PORT` correspondiente en `.env` y `docker compose up -d` |
| Cambié código de backend y no se refleja | el código está horneado en la imagen → `docker compose up -d --build api worker` |
| `create_admin` dice que el admin ya existe | normal si lo corriste antes; el admin ya está |
| El API no responde tras un `--build` | esperá ~6s a que arranque; reintentá. Un 404 transitorio justo tras recrear el contenedor se resuelve solo al reintentar |
| El frontend no conecta al API (CORS) | verificá `CORS_ORIGINS` incluya `http://localhost:5173`, y `VITE_API_URL` apunte al puerto del API (`8001`) |
| Temporal "no listo" en el arranque | el worker reintenta la conexión ~30 veces; esperá a que Temporal levante |

Para problemas de **uso** (workflows que no avanzan, replay, logs, etc.) ver
**[MANUAL-USO.md](MANUAL-USO.md) → Troubleshooting**.
