# 04 — API REST y Esquema de Workflow

> Estado: Borrador para arranque · Fecha: 2026-06-24
> Principios: **API First** (todo vía API), **Workflow as Code**, **AI First**
> (catálogo y validación legibles por máquina para FlowOps Architect).

## Parte A — API REST (FastAPI)

### A.1 Convenciones
- Base path versionado: `/api/v1`.
- Auth: `Authorization: Bearer <JWT>`. Roles: `admin`, `operator`, `developer`,
  `viewer` (ver matriz en §A.8).
- Respuestas JSON; errores con forma `{ "error": { "code", "message", "details" } }`.
- Paginación por cursor: `?limit=&cursor=`.
- Todo recurso está acotado al `tenant_id` del token (multi-tenant ready).
- Idempotencia en `POST /executions` vía cabecera `Idempotency-Key`. **Implementación
  (ADR-0014):** el `temporal_workflow_id` se deriva de forma determinista de la
  `Idempotency-Key` (o de `(workflow_version_id, hash(inputs))` si no se envía) y se usa
  `WorkflowIdReusePolicy` para que Temporal rechace duplicados — sin tabla de claves. La
  fila `executions` es una **proyección** (upsert idempotente por `temporal_workflow_id`).
- OpenAPI autogenerado por FastAPI en `/api/v1/openapi.json` (contrato vivo).

### A.2 Autenticación
```
POST /api/v1/auth/login        → { access_token, refresh_token, expires_in }
POST /api/v1/auth/refresh      → nuevo access_token
POST /api/v1/auth/logout
GET  /api/v1/auth/me           → usuario + rol actual
```

### A.3 Workflows y versiones
```
GET    /api/v1/workflows                      lista (filtros: enabled, q)
POST   /api/v1/workflows                      crea (body: YAML/JSON definición)
GET    /api/v1/workflows/{id}                 detalle + versión activa
PUT    /api/v1/workflows/{id}                 metadatos (nombre, trigger, enabled)
DELETE /api/v1/workflows/{id}                 borrado lógico
POST   /api/v1/workflows/{id}/versions        crea nueva versión (nuevo YAML/JSON)
GET    /api/v1/workflows/{id}/versions        historial de versiones
GET    /api/v1/workflows/{id}/versions/{v}    una versión concreta
POST   /api/v1/workflows/{id}/activate/{v}    fija versión activa
GET    /api/v1/workflows/{id}/export?format=yaml|json
POST   /api/v1/workflows/import               import (YAML/JSON)
```

### A.4 Validación y simulación (clave para AI First)
```
POST /api/v1/workflows/validate    body: definición → { valid, errors[] }
POST /api/v1/workflows/simulate    dry-run: resuelve el DAG, valida refs de
                                   jobs/conectores/secrets SIN ejecutar efectos
                                   → { plan: [...], warnings: [...] }
```

### A.5 Ejecuciones
```
POST   /api/v1/executions                     lanza (body: workflow_id [+version], input_context)
GET    /api/v1/executions                     lista (filtros: workflow_id, status, rango fechas)
GET    /api/v1/executions/{id}                detalle + estado + contexto
GET    /api/v1/executions/{id}/jobs           job_executions de la ejecución
GET    /api/v1/executions/{id}/events         eventos (auditoría/timeline)
POST   /api/v1/executions/{id}/cancel
POST   /api/v1/executions/{id}/replay         re-ejecuta (misma versión + inputs)
GET    /api/v1/executions/{id}/artifacts      lista de artefactos (refs MinIO)
WS     /api/v1/executions/{id}/stream         estado + logs en vivo (vía Redis)
```

### A.6 Catálogos (legibles por máquina — para Architect)
```
GET /api/v1/catalog/job-types        tipos de job + input/output schema
GET /api/v1/catalog/connectors       conectores/plugins disponibles
GET /api/v1/catalog/workflow-schema  JSON Schema del workflow-as-code
```

### A.7 Agentes, plugins, secretos, usuarios
```
GET    /api/v1/agents                         lista + estado
POST   /api/v1/agents/enroll                  inicia enrolamiento → token+instrucciones
POST   /api/v1/agents/{id}/approve            aprueba un agente pendiente
POST   /api/v1/agents/{id}/revoke
GET    /api/v1/plugins                         catálogo registrado
POST   /api/v1/plugins                         registra/actualiza (admin)
GET    /api/v1/secrets                         lista claves (nunca valores)
PUT    /api/v1/secrets/{key}                   crea/actualiza valor (cifrado)
DELETE /api/v1/secrets/{key}
GET/POST/PUT/DELETE /api/v1/users             gestión de usuarios (admin)
```

### A.8 Matriz de permisos (resumen)
| Acción | admin | operator | developer | viewer |
|--------|:-----:|:--------:|:---------:|:------:|
| Ver workflows/ejecuciones | ✓ | ✓ | ✓ | ✓ |
| Crear/editar workflows | ✓ | – | ✓ | – |
| Lanzar/cancelar/replay ejecución | ✓ | ✓ | ✓ | – |
| Aprobar/revocar agentes | ✓ | – | – | – |
| Gestionar usuarios/roles/secretos | ✓ | – | – | – |
| Registrar plugins | ✓ | – | ✓* | – |

\* developer solo en entornos no productivos (configurable).

---

## Parte B — Esquema de Workflow (Workflow as Code)

Fuente de verdad en YAML o JSON, intercambiables. Se valida contra un **JSON
Schema** (expuesto en `/catalog/workflow-schema`). Se normaliza y versiona (hash).

### B.1 Estructura general
```yaml
apiVersion: flowops/v1
kind: Workflow
metadata:
  name: daily_import
  description: "Descarga, valida y carga un archivo a la base de datos"
  labels: { team: data, env: prod }
spec:
  trigger:
    type: cron            # cron | manual | webhook | event
    cron: "0 6 * * *"
    timezone: "Europe/Madrid"

  # Contexto inicial compartido; los jobs leen/escriben aquí.
  context:
    source_url: "https://example.com/data.csv"
    target_table: "imports.daily"

  # Política de error a nivel workflow
  on_error: fail          # fail | continue | compensate
  sla:                    # opcional (base para Fase 2)
    expected_duration: "10m"
    deadline: "30m"
    criticality: high

  jobs:
    - id: download_file
      type: command
      run_on: agent        # server | agent
      agent_selector: { env: prod }   # routing por labels (si run_on=agent)
      with:
        command: "curl -fsSL {{ context.source_url }} -o /tmp/data.csv"
      timeout: "2m"
      retry: { strategy: exponential, max_attempts: 3, initial_interval: "5s" }
      outputs:
        file_path: "/tmp/data.csv"

    - id: validate_file
      type: command
      run_on: agent
      needs: [download_file]            # dependencias (DAG)
      with:
        command: "python /opt/validate.py {{ jobs.download_file.outputs.file_path }}"
      retry: { strategy: fixed, max_attempts: 2, interval: "10s" }

    - id: load_database
      type: sql
      run_on: server
      needs: [validate_file]
      with:
        connection: "secret://pg_main"   # resuelto desde secrets en runtime
        statement: "COPY {{ context.target_table }} FROM '/tmp/data.csv' CSV HEADER"
      timeout: "5m"
```

### B.2 Campos del workflow
| campo | obligatorio | descripción |
|-------|:-----------:|-------------|
| `apiVersion` / `kind` | ✓ | versión del esquema (`flowops/v1`) |
| `metadata.name` | ✓ | único por tenant, `[a-z0-9_-]` |
| `spec.trigger` | ✓ | tipo y config del disparador |
| `spec.context` | – | variables iniciales compartidas |
| `spec.on_error` | – | `fail` (def.) / `continue` / `compensate` |
| `spec.sla` | – | umbrales (Fase 2) |
| `spec.jobs` | ✓ | lista de jobs (≥1) |

> **Triggers `cron` (ADR-0015):** se materializan como **Temporal Schedules**, no como un
> scheduler propio. `trigger_config` (cron + timezone) es la fuente de verdad; la API crea/
> actualiza/pausa el Schedule al crear/editar/`activate`/habilitar el workflow.

### B.3 Campos de un job
| campo | obligatorio | descripción |
|-------|:-----------:|-------------|
| `id` | ✓ | único en el workflow, estable entre versiones |
| `type` | ✓ | `command` / `rest` / `sql` (MVP); más como plugins |
| `run_on` | – | `server` (def.) / `agent` |
| `agent_selector` | – | labels para enrutar a un agente (si `run_on: agent`) |
| `needs` | – | ids de jobs que deben completar antes (define el DAG) |
| `with` | ✓ | parámetros propios del tipo de job (validados por su schema) |
| `timeout` | – | duración máxima |
| `retry` | – | política: `fixed` / `exponential` / `custom` |
| `outputs` | – | mapa de salidas exportadas al contexto |
| `condition` | – | expresión para ejecución condicional (post-MVP, reservado) |

### B.4 Contexto y plantillas
- Sintaxis de interpolación `{{ ... }}` (motor: Jinja-like, sin ejecución arbitraria
  y **sin filtros no deterministas** como `now()`/`random` — ver ADR-0011).
- Espacios disponibles: `context.*`, `jobs.<id>.outputs.*`, `secrets://<key>`
  (resuelto en runtime, nunca expuesto en logs ni en la definición persistida).
- **Modelo de datos del contexto (v2, ADR-0013):** el `spec.context` inicial es
  **inmutable/solo-lectura** durante la ejecución. Los jobs **no mutan un blob global
  compartido**; en su lugar **declaran `outputs`** que quedan disponibles bajo
  `jobs.<id>.outputs.*` para los jobs siguientes. Esto evita races/merges no
  deterministas en ramas paralelas del DAG y mantiene el replay correcto.
- El estado final de la ejecución (`executions.output_context`) es la **composición**
  del contexto inicial + todos los `jobs.<id>.outputs` recogidos (no una mutación in-place).
- Mantener el contexto **pequeño y serializable (JSON)**: los datos voluminosos van a
  MinIO como artefactos y en el contexto viaja solo la **referencia** (clave/URL). Esto
  evita inflar la historia de Temporal (que persiste estos payloads — ver ADR-0016).

### B.5 Tipos de job — contrato `with` (MVP)
**command**
```yaml
with: { command: "<shell>", env: { KEY: VALUE }, working_dir: "/path" }
```
**rest**
```yaml
with:
  method: GET|POST|PUT|DELETE
  url: "https://..."
  headers: { ... }
  body: { ... }            # opcional
  expect_status: [200, 201]
```
**sql**
```yaml
with:
  connection: "secret://pg_main"   # o dsn directo (no recomendado)
  statement: "SELECT ..."          # o procedure: "schema.sp_name"
  params: { ... }
```
Cada tipo declara su `input_schema`/`output_schema` en el catálogo de plugins, de
modo que `validate`/`simulate` (y el futuro Architect) puedan razonar sobre ellos.

### B.6 Reglas de validación (qué comprueba `validate`)
1. Esquema estructural correcto (JSON Schema).
2. `id` de jobs únicos; `needs` referencian ids existentes; **sin ciclos** (DAG válido).
3. `type` existe en el catálogo y `with` cumple el `input_schema` del tipo.
4. `run_on: agent` requiere `agent_selector` resoluble (en `simulate`).
5. Referencias `{{ jobs.X.outputs.Y }}` apuntan a outputs declarados por X.
6. `secret://k` existe (en `simulate`, no en `validate` estructural).
