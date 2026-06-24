# 03 — Modelo de Datos (PostgreSQL)

> Estado: Borrador para arranque · Fecha: 2026-06-24
> Principio rector: **multi-tenant ready** (`tenant_id` en todas las tablas de
> negocio desde el día 1) y **auditabilidad total** (nada crítico solo en memoria).

## 1. Convenciones

- Claves primarias: `UUID` (`gen_random_uuid()` con extensión `pgcrypto`).
- Toda tabla de negocio incluye `tenant_id UUID NOT NULL` (FK a `tenants`).
- Timestamps `created_at` / `updated_at` `TIMESTAMPTZ NOT NULL DEFAULT now()`.
- Borrado lógico donde aplique (`deleted_at TIMESTAMPTZ NULL`), nunca físico en
  tablas auditables (ejecuciones, eventos).
- Datos JSON flexibles en `JSONB` (definiciones, contexto, payloads).
- Postgres con **Row-Level Security (RLS)** preparada por `tenant_id` (activable
  cuando la multi-tenancy pase a operativa; en MVP se filtra en la capa de API).

## 2. Diagrama entidad-relación (resumen)

```
tenants 1───* users
tenants 1───* workflows 1───* workflow_versions
workflows 1───* executions 1───* job_executions
executions 1───* execution_events
job_executions 1───* artifacts (refs MinIO)
tenants 1───* agents 1───* job_executions (las ejecutadas en ese agente)
tenants 1───* plugins
tenants 1───* secrets (cifrados)
users *───* roles (role en users por simplicidad MVP)
* ───* audit_log (append-only, cualquier acción relevante)
```

## 3. Tablas

### 3.1 `tenants`
| columna | tipo | notas |
|---------|------|-------|
| id | UUID PK | |
| name | TEXT | |
| slug | TEXT UNIQUE | |
| status | TEXT | `active` / `suspended` |
| created_at / updated_at | TIMESTAMPTZ | |

> En el MVP existe un único tenant "default", pero el esquema ya lo soporta.

### 3.2 `users`
| columna | tipo | notas |
|---------|------|-------|
| id | UUID PK | |
| tenant_id | UUID FK | |
| email | CITEXT | único por tenant |
| password_hash | TEXT | argon2id |
| role | TEXT | `admin` / `operator` / `developer` / `viewer` |
| is_active | BOOLEAN | |
| last_login_at | TIMESTAMPTZ NULL | |
| created_at / updated_at | TIMESTAMPTZ | |

Índice único `(tenant_id, email)`.

### 3.3 `workflows`
Definición lógica (apunta a la versión activa).
| columna | tipo | notas |
|---------|------|-------|
| id | UUID PK | |
| tenant_id | UUID FK | |
| name | TEXT | único por tenant |
| description | TEXT NULL | |
| active_version_id | UUID FK NULL | → workflow_versions |
| trigger_type | TEXT | `cron` / `manual` / `webhook` / `event` |
| trigger_config | JSONB | p.ej. `{ "cron": "0 6 * * *" }` |
| is_enabled | BOOLEAN | habilita/inhabilita el trigger |
| criticality | TEXT | `low`/`medium`/`high` (base para SLA futuro) |
| created_by | UUID FK users | |
| created_at / updated_at / deleted_at | TIMESTAMPTZ | |

### 3.4 `workflow_versions` (inmutable)
| columna | tipo | notas |
|---------|------|-------|
| id | UUID PK | |
| tenant_id | UUID FK | |
| workflow_id | UUID FK | |
| version | INTEGER | incremental por workflow |
| definition | JSONB | el workflow-as-code normalizado |
| definition_hash | TEXT | sha256 del contenido canónico |
| source_format | TEXT | `yaml` / `json` |
| created_by | UUID FK users | |
| created_at | TIMESTAMPTZ | |

Único `(workflow_id, version)`. Nunca se actualiza ni se borra.

### 3.5 `executions`
Una ejecución de una versión de workflow.
| columna | tipo | notas |
|---------|------|-------|
| id | UUID PK | |
| tenant_id | UUID FK | |
| workflow_id | UUID FK | |
| workflow_version_id | UUID FK | versión exacta ejecutada |
| temporal_workflow_id | TEXT | id en Temporal |
| temporal_run_id | TEXT | run id en Temporal |
| trigger_source | TEXT | `cron` / `manual` / `webhook` / `replay` |
| triggered_by | UUID FK users NULL | |
| status | TEXT | `pending`/`running`/`success`/`failed`/`cancelled` |
| input_context | JSONB | contexto inicial |
| output_context | JSONB NULL | contexto final |
| started_at / finished_at | TIMESTAMPTZ NULL | |
| error | JSONB NULL | resumen del fallo |
| replay_of_execution_id | UUID FK NULL | si es un replay |
| created_at | TIMESTAMPTZ | |

Índices: `(tenant_id, workflow_id, created_at)`, `(status)`. Único `(temporal_workflow_id)`
para el **upsert idempotente** (la fila es una proyección del workflow de Temporal — ADR-0014;
no hace falta una tabla de `idempotency_keys`).

### 3.6 `job_executions`
Una ejecución de un job dentro de una ejecución.
| columna | tipo | notas |
|---------|------|-------|
| id | UUID PK | |
| tenant_id | UUID FK | |
| execution_id | UUID FK | |
| job_id | TEXT | id del job dentro del workflow (estable) |
| job_type | TEXT | `command`/`rest`/`sql`/... |
| agent_id | UUID FK agents NULL | NULL = server-side |
| attempt | INTEGER | nº de intento (retry) |
| status | TEXT | `pending`/`running`/`success`/`failed`/`skipped` |
| input | JSONB | parámetros resueltos del job |
| output | JSONB NULL | resultado (datos pequeños; binarios → artifacts) |
| logs_ref | TEXT NULL | clave MinIO de logs voluminosos |
| error | JSONB NULL | |
| started_at / finished_at | TIMESTAMPTZ NULL | |
| created_at | TIMESTAMPTZ | |

Índices: `(execution_id)`, `(tenant_id, job_type)`, `(agent_id)`.

> **Reintentos (v2):** una fila por **intento**. Como Temporal gestiona los retries *dentro*
> de la actividad, la propia activity escribe (insert) una fila `job_executions` con
> `attempt = info.attempt` al **iniciar cada intento** y la actualiza al terminar. Así el
> historial por-intento queda en Postgres aunque Temporal solo exponga el resultado final.
> Único parcial sugerido: `(execution_id, job_id, attempt)`.

### 3.7 `execution_events` (append-only)
Trazabilidad fina; alimenta el live-feed (vía Redis) y la auditoría.
| columna | tipo | notas |
|---------|------|-------|
| id | BIGSERIAL PK | orden temporal |
| tenant_id | UUID FK | |
| execution_id | UUID FK | |
| job_execution_id | UUID FK NULL | |
| event_type | TEXT | `started`/`job_started`/`job_succeeded`/`job_failed`/`retry`/`finished`/... |
| payload | JSONB | |
| created_at | TIMESTAMPTZ | |

### 3.8 `artifacts`
Referencias a objetos en MinIO (Postgres nunca guarda el binario).
| columna | tipo | notas |
|---------|------|-------|
| id | UUID PK | |
| tenant_id | UUID FK | |
| execution_id | UUID FK | |
| job_execution_id | UUID FK NULL | |
| name | TEXT | |
| bucket | TEXT | |
| object_key | TEXT | |
| size_bytes | BIGINT | |
| content_type | TEXT | |
| checksum | TEXT | |
| created_at | TIMESTAMPTZ | |

### 3.9 `agents`
| columna | tipo | notas |
|---------|------|-------|
| id | UUID PK | |
| tenant_id | UUID FK | |
| name | TEXT | |
| status | TEXT | `pending_approval`/`approved`/`online`/`offline`/`revoked` |
| os | TEXT | `linux` (MVP) |
| task_queue | TEXT | `agent-<id>` en Temporal (enrutado, **no** frontera de seguridad — ADR-0012) |
| fingerprint | TEXT | huella del cert mTLS del agente |
| public_key | TEXT NULL | clave pública del agente para **envelope encryption** de secretos (ADR-0013) |
| labels | JSONB | p.ej. `{ "env": "prod", "region": "eu" }` para routing |
| last_heartbeat_at | TIMESTAMPTZ NULL | |
| enrolled_by | UUID FK users NULL | |
| created_at / updated_at | TIMESTAMPTZ | |

### 3.10 `plugins`
Registro del catálogo de jobs/conectores (Plugin First).
| columna | tipo | notas |
|---------|------|-------|
| id | UUID PK | |
| tenant_id | UUID FK NULL | NULL = plugin global del sistema |
| name | TEXT | p.ej. `postgres` |
| version | TEXT | semver |
| kind | TEXT | `job` / `connector` |
| actions | JSONB | lista de acciones |
| input_schema | JSONB | JSON Schema |
| output_schema | JSONB | JSON Schema |
| metadata | JSONB | |
| enabled | BOOLEAN | |
| created_at / updated_at | TIMESTAMPTZ | |

### 3.11 `secrets` (cifrado en reposo — provisional MVP)
| columna | tipo | notas |
|---------|------|-------|
| id | UUID PK | |
| tenant_id | UUID FK | |
| key | TEXT | único por tenant |
| ciphertext | BYTEA | cifrado con clave maestra (env/KMS local) |
| metadata | JSONB | p.ej. tipo, descripción |
| created_by | UUID FK users | |
| created_at / updated_at | TIMESTAMPTZ | |

> Reemplazable por un Secret Vault dedicado en Fase 2 sin cambiar el contrato de
> consumo (la API resuelve `secret://key` en tiempo de ejecución).

### 3.12 `audit_log` (append-only, gobierno)
Distinto de `execution_events`: registra acciones de usuarios/sistema (login,
crear/editar workflow, aprobar agente, cambiar rol, etc.).
| columna | tipo | notas |
|---------|------|-------|
| id | BIGSERIAL PK | |
| tenant_id | UUID FK | |
| actor_user_id | UUID FK NULL | NULL = sistema |
| action | TEXT | `workflow.create`, `agent.approve`, ... |
| target_type | TEXT | |
| target_id | TEXT | |
| metadata | JSONB | antes/después si aplica |
| ip_address | INET NULL | |
| created_at | TIMESTAMPTZ | |

## 4. Estados (máquinas de estado)

- **execution.status**: `pending → running → (success | failed | cancelled)`.
- **job_execution.status**: `pending → running → (success | failed | skipped)`;
  un `failed` puede generar un nuevo `job_executions` con `attempt+1` (retry).
- **agent.status**: `pending_approval → approved → (online ↔ offline) → revoked`.

## 5. Particionado / retención (preparado, no obligatorio en MVP)
`execution_events` y `audit_log` crecen rápido. Diseñar desde ya pensando en
particionar por mes (`PARTITION BY RANGE (created_at)`) y políticas de retención.
En MVP basta con índices; se documenta para no rehacer el esquema después.

## 6. Migraciones
Gestionar el esquema con **Alembic**. Cada cambio = una migración versionada en el
repo. Nunca editar el esquema a mano en entornos. La migración inicial crea todas
las tablas anteriores + extensiones `pgcrypto` y `citext`.
