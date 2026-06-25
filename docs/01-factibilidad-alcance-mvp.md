# 01 — Factibilidad, Alcance y MVP

> Estado: Borrador para arranque · Fecha: 2026-06-24 · Todo es tentativo y revisable.

## 1. Resumen ejecutivo

MoiraFlow es una visión ambiciosa y coherente: una "Automation Operating System"
para SMBs que combina orquestación tipo Control-M, integraciones tipo n8n/Zapier
y ejecución distribuida con agentes. La visión es sólida. El riesgo **no** está
en la idea, sino en el **alcance frente a los recursos disponibles**.

Decisiones de arranque acordadas con el promotor del proyecto:

| Dimensión | Decisión |
|-----------|----------|
| Equipo | **1 desarrollador** (con asistencia de IA) |
| Motor de ejecución | **Sobre Temporal** (no desde cero) |
| Despliegue inicial | **Self-hosted / Docker** |
| Agentes distribuidos | **Incluidos en el MVP** (versión "delgada") |

La conclusión principal: el proyecto **es factible** para un solo desarrollador
**solo si** (a) se apalanca agresivamente en Temporal para toda la durabilidad de
ejecución, y (b) el MVP se reduce a una **vertical fina end-to-end** en lugar de
intentar cubrir toda la "Fase 1" del documento original.

## 2. Análisis de factibilidad

### 2.1 Lo que está bien planteado

- **API First / Plugin First / Workflow as Code / AI First / Event Driven /
  Auditability**: son principios correctos y modernos. Se conservan tal cual.
- **Stack** (React + TS + React Flow / Python + FastAPI / PostgreSQL / MinIO):
  razonable y bien soportado por un solo dev.
- **Multi-tenant "listo pero no requerido"**: correcto. Se implementa como
  `tenant_id` en el esquema desde el día 1 (barato ahora, carísimo después).

### 2.2 Riesgos principales (ordenados por impacto)

1. **Alcance vs. 1 desarrollador (riesgo crítico).** La "Fase 1" del documento
   original (motor + agentes + 3 tipos de job + retry + logs + UI básica) es,
   realistamente, 6–12 meses para un equipo pequeño. Para 1 dev hay que recortar
   a una vertical mínima. → Ver §3.

2. **Construir el motor de ejecución desde cero (mitigado).** Resolución de
   dependencias, reintentos, timeouts, recuperación y *replay* duraderos son lo
   más difícil de acertar. **Mitigación adoptada: usar Temporal**, que ya resuelve
   durabilidad, reintentos, timeouts, *replay* y recuperación. MoiraFlow queda como
   capa de modelado, API, UI, plugins y agentes por encima.

3. **Agentes distribuidos en el MVP (riesgo alto, vigilar).** Ejecutar
   scripts/binarios en máquinas del cliente es la mayor superficie de seguridad
   (mTLS, registro/aprobación de agentes, firma de jobs, sandboxing, aislamiento
   de secretos). **Mitigación adoptada: "agente delgado"** — un único tipo de
   agente que actúa como *Temporal worker* remoto, un solo OS bien soportado al
   inicio (Linux), sin marketplace ni auto-update. → Ver `05-protocolo-agente-seguridad.md`.

4. **Dispersión de tipos de job.** El documento lista 8 tipos (Command, SQL, REST,
   Email, File Watcher, SFTP, Webhook). Implementarlos todos a la vez dispersa el
   esfuerzo. → El MVP solo incluye **Command, REST y SQL** (los demás como plugins
   posteriores con el mismo contrato).

5. **Redis Streams como bus + cola (simplificable).** Con Temporal, gran parte de
   la cola/recuperación la absorbe Temporal. Redis se mantiene solo para
   *pub/sub* de eventos en tiempo real hacia la UI (logs/estado), no como columna
   vertebral de ejecución. Esto reduce piezas que mantener.

### 2.3 Veredicto

Factible para 1 dev con el MVP redefinido en §3 y Temporal como base. El mayor
peligro a vigilar continuamente es el de **agentes**; si el cronograma se tensa,
la primera palanca es degradar agentes a "worker local en el mismo host" y posponer
el agente remoto multi-OS.

## 3. MVP redefinido (vertical fina end-to-end)

**Objetivo del MVP:** que un usuario pueda definir un workflow como código,
dispararlo (cron o manual), ejecutarlo con dependencias y reintentos sobre
Temporal —incluyendo al menos un job ejecutado en un **agente** (`run_on: agent`;
worker local con task queue dedicada en el MVP, remoto real en el Hito 5 — ADR-0017)—
y ver el resultado, los logs y el historial auditable en una UI.

### En alcance (MVP)

- **Workflow-as-Code**: definición en YAML/JSON, validación, import/export.
- **Triggers**: cron + manual (vía API/UI). Webhook como *stretch*.
- **Tipos de job**: `command`, `rest`, `sql` (Postgres). Cada uno como plugin con
  contrato común.
- **Motor**: orquestación sobre Temporal (dependencias, retry con backoff,
  timeouts, recuperación, replay).
- **Contexto de ejecución compartido** entre jobs.
- **Agente delgado**: un agente Linux que ejecuta `command` jobs de forma remota.
- **Persistencia/auditoría**: workflows, versiones, ejecuciones, ejecuciones de
  job, inputs/outputs (referencias), errores y eventos en PostgreSQL.
- **Artefactos**: subida/descarga a MinIO; en Postgres solo metadatos/referencias.
- **API**: FastAPI cubriendo CRUD de workflows, lanzar/consultar ejecuciones,
  catálogo de jobs/conectores (para Architect futuro) y validación.
- **AuthN/Z**: JWT + roles (Admin, Operator, Developer, Viewer).
- **UI básica (React)**: lista de workflows, editor de YAML, lanzar ejecución,
  ver ejecuciones/logs en vivo, estado de agentes.
- **Despliegue**: `docker compose up` levanta todo (API, worker, UI, Postgres,
  Temporal, Redis, MinIO).
- **Multi-tenant ready**: `tenant_id` en el esquema (un solo tenant operativo).

### Fuera del MVP (siguientes fases)

Designer visual completo (drag&drop), Secret Vault dedicado, SLA monitoring,
versionado avanzado/diff visual, jobs Email/SFTP/File Watcher, marketplace de
plugins, multi-tenancy operativa + billing, SaaS, agentes Windows/macOS con
auto-update, gRPC, RabbitMQ/Kafka, MoiraFlow Architect (IA), Kubernetes.

> Nota: la arquitectura se diseña para **no cerrar** ninguna de estas puertas.
> Lo que cambia es el *orden de construcción*, no la visión.

## 4. Cambios propuestos sobre el documento original

| Tema | Documento original | Propuesta | Motivo |
|------|--------------------|-----------|--------|
| Execution Engine | Construir (dependencias, retry, timeout, recovery) | **Temporal** como base | Elimina el 70% del riesgo técnico |
| Event Bus / Queue | Redis Streams como columna vertebral | Temporal para ejecución; Redis solo pub/sub UI | Menos piezas, durabilidad gratis |
| Tipos de job MVP | 8 tipos | 3 (command, rest, sql) + resto como plugins | Foco para 1 dev |
| Agentes | Multi-OS, varios responsables | Agente delgado Linux como Temporal worker | Reduce superficie de seguridad |
| UI MVP | Designer visual en Fase 1/2 | Editor YAML + monitor en MVP; visual después | El valor inicial es ejecutar, no dibujar |
| Comunicación agente | HTTPS + WebSocket (gRPC futuro) | Conexión Temporal (gRPC/TLS gestionado por Temporal) | Reusar transporte robusto existente |

## 5. Criterios de aceptación del MVP (Definition of Done)

1. Puedo crear un workflow en YAML vía API y UI, y se valida contra el esquema.
2. Un trigger cron y un disparo manual ejecutan el workflow.
3. El workflow ejecuta al menos 3 jobs con dependencias (DAG), con al menos un
   `command` corriendo en un **agente** (worker con `run_on: agent` y task queue dedicada;
   local en el Hito 3, remoto real en el Hito 5 — ADR-0017) y un `rest`/`sql` server-side.
4. Un job que falla reintenta con backoff según su política; si agota reintentos,
   el workflow refleja el fallo y queda auditado.
5. Veo en la UI el estado en vivo, los logs y el historial; puedo **re-ejecutar**
   (replay) una ejecución pasada.
6. Todo (definición, versión, ejecución, job, input/output ref, error, evento)
   queda persistido con `tenant_id`.
7. `docker compose up` levanta el sistema completo en una máquina limpia.

## 6. Decisiones cerradas (antes preguntas abiertas)

Resueltas el 2026-06-24:

1. **Aislamiento de secretos en el MVP**: tabla cifrada en Postgres (clave maestra
   en env/KMS local) + contrato `secret://`. El Secret Vault dedicado llega en
   Fase 2 sin cambiar el contrato de consumo. ✔ (ver ADR-0007)
2. **Identidad del usuario**: JWT propio (email+password, argon2id) en el MVP;
   OIDC (Keycloak/Authentik, Google, Microsoft) en fase posterior. ✔
3. **Sandboxing de `command` jobs**: usuario sin privilegios + límites de recursos
   en el MVP; contenedor por job en Fase 2. ✔ (ver `05-...md` §4.4)
4. **Idioma del producto/UI**: **inglés**. La UI y los textos de producto se
   escriben en inglés. (Esta documentación interna de arranque queda en español.)
   Se recomienda estructurar el frontend con claves de i18n desde el inicio para
   no bloquear traducciones futuras, aunque solo exista el locale `en`.
5. **Licencia y modelo**: **Open core con núcleo bajo BSL 1.1** (Business Source
   License), con cláusula de no-competencia y conversión automática a Apache 2.0
   tras ~4 años; features premium bajo licencia comercial. Compatible con las
   dependencias (Temporal=MIT, FastAPI/React=permisivas). ✔ (ver ADR-0009)
