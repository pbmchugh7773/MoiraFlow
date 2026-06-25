# 02 — Arquitectura

> Estado: Borrador para arranque · Fecha: 2026-06-24
> Decisiones base: 1 dev · Motor sobre Temporal · Self-hosted Docker · Agente delgado en MVP.

## 1. Principios que gobiernan la arquitectura

Se conservan los del documento de proyecto y guían cada decisión:

- **API First** — toda capacidad existe vía API; la UI solo la consume.
- **Plugin First** — el core no depende de conectores concretos; jobs y
  conectores son plugins con un contrato común.
- **Workflow as Code** — YAML/JSON como fuente de verdad, exportable/importable.
- **AI First** — el motor expone catálogo y esquemas legibles por máquina para el
  futuro MoiraFlow Architect, sin que la IA toque tablas internas.
- **Event Driven** — ejecución programada, por evento e híbrida.
- **Auditability** — nada crítico vive solo en memoria; todo es trazable y *replayable*.

## 2. Diagrama lógico (MVP)

```
                         ┌───────────────────────────┐
                         │        Frontend (UI)       │
                         │  React + TS + React Flow   │
                         └─────────────┬─────────────┘
                                       │ HTTPS (REST + WS)
                         ┌─────────────▼─────────────┐
                         │        API Layer           │
                         │     FastAPI (Python)       │
                         │  Auth · Workflows · Exec   │
                         │  Plugins · Catalog · Valid │
                         └───┬───────────┬────────┬───┘
            escribe/lee      │           │        │  pub/sub estado+logs
        ┌────────────────────▼──┐   ┌────▼────┐  ┌▼─────────────┐
        │   PostgreSQL           │   │ Temporal │  │   Redis      │
        │ workflows, versiones,  │   │  (motor) │  │ pub/sub UI   │
        │ ejecuciones, jobs,     │   └────┬────┘  └──────────────┘
        │ auditoría, usuarios    │        │ tareas / actividades
        └────────────────────────┘        │
                              ┌────────────┴───────────────┐
                              │                            │
                   ┌──────────▼──────────┐      ┌──────────▼──────────┐
                   │  Worker server-side  │      │  Agente delgado      │
                   │ (Temporal worker)    │      │ (Temporal worker     │
                   │ jobs: rest, sql,     │      │  remoto, task queue  │
                   │ command local        │      │  propia) command     │
                   └──────────┬───────────┘      └──────────────────────┘
                              │ artefactos
                   ┌──────────▼──────────┐
                   │   MinIO (S3)         │
                   │ archivos/outputs     │
                   └─────────────────────┘
```

> Nota: la "cadena" del documento original (API → Workflow Engine → Execution
> Engine → Event Bus → Agent Manager → Agents → Connectors) se mapea aquí así:
> *Workflow Engine* = nuestro modelado + traducción a un Temporal Workflow;
> *Execution Engine + Event Bus* = Temporal; *Agent Manager* = registro de
> agentes en API + asignación por **task queue** de Temporal; *Connectors* =
> plugins de job (actividades de Temporal).

## 3. Componentes

### 3.1 Frontend (React + TypeScript + React Flow)
Consumidor puro de la API. En el MVP: lista/editor YAML de workflows, lanzar
ejecución, monitor de ejecuciones y logs en vivo (WebSocket), estado de agentes,
administración básica de usuarios/roles. React Flow se incorpora ya (aunque el
designer visual completo es post-MVP) para renderizar el DAG en modo lectura.

### 3.2 API Layer (FastAPI)
Responsable de autenticación/autorización, CRUD de workflows y versiones,
validación contra el esquema, lanzar/consultar ejecuciones (delegando en
Temporal), registro y catálogo de plugins (jobs/conectores), catálogo legible por
máquina (para Architect) y endpoints de simulación/validación. Es **stateless**;
todo el estado vive en Postgres/Temporal/MinIO/Redis.

### 3.3 Motor de ejecución — Temporal
Temporal aporta *durable execution*: el estado del workflow sobrevive a caídas, y
las **actividades** (cada job) tienen reintentos, timeouts y backoff nativos.

- Cada workflow de MoiraFlow se traduce a **un Temporal Workflow genérico**
  (un "interpreter") que recibe la definición (DAG de jobs) y la ejecuta
  resolviendo dependencias y propagando el **contexto compartido**.
- Cada job es una **Activity**. El tipo de job determina qué plugin/actividad se
  invoca (`command`, `rest`, `sql`).
- La **task queue** de Temporal enruta la actividad al worker correcto: las de
  servidor a los workers server-side; las que deben correr en una máquina concreta
  del cliente, a la task queue de ese **agente**.
- Reintentos/backoff/timeout se configuran por job a partir de su política
  (mapeo directo a `RetryPolicy` de Temporal).
- **Replay**: re-ejecutar una ejecución pasada = arrancar un nuevo workflow con la
  misma definición+inputs versionados (no se reusa el historial mutado).
- **Determinismo (crítico, ADR-0011):** el código del interpreter debe ser **determinista**
  o el replay se corrompe. Partición estricta: en el **workflow** solo orquestación pura del
  DAG sobre datos ya materializados (resolver `needs`, decidir jobs listos, recoger outputs)
  y **interpolación pura** de plantillas; en **activities** todo I/O, resolución de `secret://`,
  tiempo y aleatoriedad. Filtros no deterministas en plantillas (`now()`, random) están prohibidos.
  Se valida con **replay tests** en CI.
- **Contexto sin mutación global (ADR-0013):** el `context` inicial es solo-lectura; los jobs
  no mutan un blob compartido, **declaran `outputs`** (`jobs.<id>.outputs.*`). Evita races en
  ramas paralelas y mantiene el replay correcto. Datos grandes → MinIO + referencia (no inflar
  la historia de Temporal).
- **Cifrado de payloads (ADR-0016):** un Data Converter/Codec cifra inputs/outputs de actividad
  y contexto antes de persistirse en Temporal, para no dejar secretos/datos en claro en su historia.

> Por qué Temporal y no construir el motor: ver ADR-0001 en `06-roadmap-y-adr.md`.
> Determinismo, contexto, idempotencia y cifrado de payloads: ADR-0011/0013/0014/0016.

### 3.4 Worker server-side
Proceso Python que registra el Temporal Workflow "interpreter" y las actividades
de los jobs que corren en el servidor (`rest`, `sql`, y `command` locales). Escala
horizontalmente con solo arrancar más réplicas.

### 3.5 Agente delgado
Mismo runtime de worker, empaquetado para correr en una máquina remota del
cliente. Se conecta al servidor de Temporal (TLS/mTLS) y escucha una **task queue
exclusiva** (`agent-<agent_id>`). Solo ejecuta `command` jobs en el MVP. Registro
y aprobación se gestionan vía API. Detalle en `05-protocolo-agente-seguridad.md`.

### 3.6 PostgreSQL
Fuente de verdad de metadatos y auditoría: definiciones y versiones de workflow,
ejecuciones, ejecuciones de job, referencias a inputs/outputs, errores, eventos,
usuarios, roles, plugins registrados, agentes. **No** guarda artefactos binarios
(solo referencias a MinIO). Todo lleva `tenant_id`. Detalle en `03-modelo-datos.md`.

### 3.7 Redis (solo pub/sub de UI)
Canal de baja latencia para empujar estado de ejecución y logs hacia la UI por
WebSocket. **No** es la cola de ejecución (eso es Temporal). Si se cae, no se
pierde nada durable: la verdad sigue en Postgres/Temporal.

> **Ruta de eventos (v2):** el **worker/activity** escribe el evento en `execution_events`
> (Postgres) **y** lo publica en Redis; el WebSocket de la API solo se **suscribe** a Redis.
> Temporal no empuja eventos a externos: no hay un salto "Temporal → API → Redis" (ADR/doc 05 §5).

### 3.8 MinIO (S3 compatible)
Almacenamiento de artefactos: archivos de entrada/salida, reportes, adjuntos.
Postgres guarda la clave/URL y metadatos. Permite migrar a S3 real sin cambios.

## 4. Flujos clave

### 4.1 Crear y versionar un workflow
1. UI/API envía YAML/JSON → API valida contra el esquema (`04-api-...md`).
2. Se persiste una **nueva versión inmutable** (hash del contenido) en Postgres.
3. La definición activa apunta a una versión; el historial se conserva siempre.

### 4.2 Disparar una ejecución (cron o manual)
1. Trigger (**Temporal Schedule** para cron — ADR-0015 — o `POST /executions` para manual)
   → se arranca el Temporal Workflow con `(definición_versionada, inputs)` usando un
   `workflow_id` **determinista** (idempotencia, ADR-0014). La fila `executions` es una
   **proyección** (upsert por `temporal_workflow_id`), no una segunda fuente de verdad; así
   se evita el problema de doble escritura API↔Temporal.
2. El "interpreter" resuelve el DAG y, por cada job listo, llama a su Activity en
   la task queue correspondiente (servidor o agente).
3. Cada Activity ejecuta el plugin, actualiza el **contexto compartido** y devuelve
   output (artefactos a MinIO, referencias a Postgres).
4. Eventos de estado/logs se publican en Redis → UI en vivo; y se persisten en
   Postgres para auditoría.
5. Al terminar, la ejecución queda `SUCCESS`/`FAILED` con todo trazado.

### 4.3 Recuperación ante fallo
- Caída de un worker/agente → Temporal reasigna la actividad pendiente cuando hay
  capacidad; el estado del workflow no se pierde.
- Fallo de un job → `RetryPolicy` (fixed / exponential / custom) hasta agotar;
  luego política de error del workflow (continuar, fallar, compensar).

## 5. Cómo encaja MoiraFlow Architect (futuro, sin construir aún)
El motor expone, **vía API y solo lectura**: catálogo de conectores, catálogo de
jobs (con input/output schema), esquema de workflow, endpoint de **validación** y
endpoint de **simulación** (dry-run que resuelve el DAG sin ejecutar efectos). La
IA generará workflows produciendo YAML/JSON válido contra esos esquemas; nunca
accede a tablas internas. Esto ya se reserva en la API del MVP (endpoints de
catálogo/validación), aunque la IA se construya en Fase 4.

## 6. Plataformas soportadas
MVP: el stack corre en **Docker** (Linux) en cualquier host (Windows/macOS/Linux/
cloud/on-prem vía Docker Desktop o Docker Engine). El **agente** se entrega como
binario/contenedor Linux en el MVP; Windows/macOS nativos en Fase 2.

## 7. Decisiones diferidas (no MVP)
RabbitMQ/Kafka, gRPC propio agente↔servidor (Temporal ya usa gRPC/TLS), Secret
Vault dedicado, Kubernetes, multi-tenancy operativa. La arquitectura no se cierra
a ninguna; ver tabla de cambios en `01-factibilidad-alcance-mvp.md` §4.
