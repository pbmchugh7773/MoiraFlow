# 06 — Roadmap (solo dev) y Decisiones de Arquitectura (ADR)

> Estado: Borrador para arranque · Fecha: 2026-06-24
> Equipo: 1 desarrollador. Cronograma orientativo; ajustar a dedicación real.

## Parte A — Roadmap por hitos

La estrategia es construir la **vertical fina end-to-end** (ver
`01-factibilidad-alcance-mvp.md` §3) y luego ensanchar. Cada hito termina en algo
demostrable y desplegable con `docker compose up`.

### Hito 0 — Fundaciones (semanas 1–2)
- Monorepo, estructura de carpetas (`07-...md`), CI básico (lint + tests).
- `docker-compose` con Postgres, Temporal, Redis, MinIO levantando.
- Esqueleto FastAPI + esqueleto worker Temporal "hola mundo".
- Migración Alembic inicial (todas las tablas de `03-...md`).
- **Entregable:** entorno reproducible; un workflow trivial corre en Temporal.

### Hito 1 — Motor + workflow-as-code server-side (semanas 3–6)
- Parser/validador del esquema de workflow (JSON Schema) + `validate`.
- Temporal Workflow "interpreter": resuelve DAG (`needs`), contexto compartido,
  retry/timeout mapeados a `RetryPolicy`.
- Jobs `rest` y `sql` como actividades server-side.
- API: CRUD workflows + versiones, lanzar/consultar ejecuciones.
- Persistencia completa de ejecuciones, job_executions y eventos.
- **Entregable:** crear un workflow por API, lanzarlo manual, ver resultado y
  auditoría. Cumple criterios 1, 2, 4 (parcial), 6 del DoD.

### Hito 2 — UI de operación (semanas 7–9)
- Frontend React: login, lista/editor YAML de workflows, lanzar ejecución,
  monitor de ejecuciones + logs en vivo (WebSocket/Redis), render DAG (lectura).
- AuthN/Z (JWT + roles) en API y UI.
- **Entregable:** flujo completo usable desde el navegador. Cumple criterio 5.

### Hito 3 — Contrato de agente vía worker local (semanas 10–12) · *valida la vertical distribuida sin la operación remota*
Estrategia revisada (v2, ver ADR-0017): se valida **todo el contrato** `run_on: agent`
con un worker que corre en el mismo host pero con **task queue propia**, sin construir
todavía CA/enrolamiento remoto. Esto desbloquea el DoD distribuido reduciendo el riesgo.
- Worker "agente" local en una task queue dedicada (`agent-local`), distinta de la del servidor.
- Job `command` con `run_on: agent`; routing por `agent_selector`/labels (resuelto a `agent-local`).
- **Modelo de seguridad ya correcto en el contrato** (aunque el transporte sea local): outputs
  declarados, resolución tardía de secretos con **envelope encryption por agente** (ADR-0012/0013),
  redacción en logs, usuario sin privilegios + límites de recursos, aislamiento por tenant en routing.
- Estado/heartbeat del agente en UI.
- **Entregable:** workflow con ≥3 jobs, uno `command` en el "agente" (worker dedicado). **MVP completo**
  a efectos funcionales del DoD (el agente *remoto* real llega en el Hito 5).

### Hito 4 — Endurecimiento, triggers y observabilidad (semanas 13–14)
- Trigger `cron` vía **Temporal Schedules** (ADR-0015) + `webhook` (stretch del MVP).
- `simulate` (dry-run) y catálogos para Architect.
- **Replay tests en CI** para cazar no-determinismo del interpreter (ADR-0011).
- **Observabilidad mínima**: OpenTelemetry (Temporal lo integra) + métricas Prometheus + healthchecks (ADR-0018).
- Pruebas de carga ligeras, recuperación ante caídas, retención de eventos.
- **Cifrado de payloads en Temporal** (Data Converter/Codec, ADR-0016).

### Hito 5 — Agente remoto seguro (semanas 15–17, timebox estricto) · *mayor riesgo, ahora aislado*
Solo se aborda con los Hitos 1–4 verdes. Si se desvía, **no bloquea** un MVP ya demostrable.
- CA interna + emisión/renovación de certificados; enrolamiento con token de un solo uso y aprobación.
- Agente como Temporal worker **remoto** (Linux) sobre mTLS, su propia task queue.
- Envelope encryption real contra la clave pública del agente; revocación efectiva (CRL/denylist) probada.
- **Entregable:** el mismo workflow del Hito 3, ahora con el `command` en una **máquina remota** real.
- Documentación de instalación y guía de inicio rápido.
- **Entregable:** MVP estable, instalable por un tercero.

### Más allá del MVP (resumen de fases del documento original, reordenadas)
- **Fase 2:** Designer visual (drag&drop con React Flow), versionado/diff visual,
  Secret Vault dedicado, SLA monitoring, jobs Email/SFTP/File-Watcher, agente
  Windows/macOS + contenedor por job.
- **Fase 3:** Marketplace de plugins, multi-tenancy operativa + aislamiento +
  billing, SaaS.
- **Fase 4:** MoiraFlow Architect (IA) sobre los catálogos/validación/simulación ya
  expuestos; despliegue automático; Kubernetes; RabbitMQ/Kafka si se necesita.

> Realismo: para 1 dev, ~14 semanas a un **MVP funcionalmente completo** (Hitos 0–4,
> agente vía worker local) es optimista-pero-posible con foco; el agente *remoto*
> (Hito 5) añade ~3 semanas y es opcional para demostrar valor. La mayor incertidumbre
> sigue siendo la operación del agente remoto, pero ahora está **aislada al final**: el
> contrato distribuido se valida antes (Hito 3) y un retraso en el Hito 5 no bloquea un
> MVP ya entregable. Esta es la consecuencia directa de ADR-0017.

---

## Parte B — Architecture Decision Records (ADR)

Formato breve: contexto → decisión → consecuencias. Las decisiones marcadas
"Aceptada" provienen de las respuestas del promotor; el resto son propuestas.

### ADR-0001 — Usar Temporal como motor de ejecución
**Estado:** Aceptada.
**Contexto:** *durable execution* (dependencias, retry, timeout, recuperación,
replay) es lo más difícil y arriesgado; el equipo es 1 dev.
**Decisión:** construir MoiraFlow como capa sobre Temporal en lugar de un motor propio.
**Consecuencias:** -70% de riesgo técnico y tiempo; +1 dependencia de
infraestructura (Temporal Server) en el `docker-compose`; el modelo de ejecución
se expresa como un Temporal Workflow "interpreter".

### ADR-0002 — Despliegue inicial self-hosted con Docker Compose
**Estado:** Aceptada.
**Contexto:** SMBs, on-prem/cloud, 1 dev.
**Decisión:** un `docker compose up` levanta todo el stack; multi-tenant ready
pero un solo tenant operativo.
**Consecuencias:** instalación simple; SaaS/multi-tenancy operativa y Kubernetes
quedan para fases posteriores (arquitectura no se cierra).

### ADR-0003 — Agentes en el MVP, en versión "delgada"
**Estado:** Aceptada (con mitigación). **Refinada por ADR-0017** (orden de construcción).
**Contexto:** los agentes remotos son el mayor riesgo de seguridad y esfuerzo.
**Decisión:** incluir agentes pero como Temporal workers remotos (mTLS, un OS:
Linux, solo `command`, aprobación explícita). Plan B = worker local si el
cronograma se tensa.
**Consecuencias:** se valida el caso de uso distribuido sin construir un protocolo
propio; multi-OS, contenedor-por-job y auto-update se posponen.

### ADR-0004 — Redis solo para pub/sub de UI, no como cola de ejecución
**Estado:** Propuesta.
**Contexto:** Temporal ya aporta cola durable y recuperación.
**Decisión:** Redis se limita a empujar estado/logs en vivo a la UI.
**Consecuencias:** menos componentes críticos; si Redis cae, no se pierde nada
durable. RabbitMQ/Kafka quedan fuera hasta tener necesidad real.

### ADR-0005 — Alcance de tipos de job en el MVP: command, rest, sql
**Estado:** Propuesta.
**Contexto:** 8 tipos dispersan a 1 dev.
**Decisión:** MVP con 3 tipos bajo un contrato de plugin común; Email/SFTP/
File-Watcher/Webhook después, sin cambiar el contrato.
**Consecuencias:** foco y un patrón de extensión validado pronto.

### ADR-0006 — `tenant_id` en todo el esquema desde el día 1
**Estado:** Propuesta (deriva de "multi-tenant ready").
**Contexto:** añadir tenancy después es carísimo.
**Decisión:** todas las tablas de negocio llevan `tenant_id`; RLS preparada.
**Consecuencias:** coste marginal hoy; multi-tenancy operativa "solo" requiere
activar RLS + onboarding/billing en Fase 3.

### ADR-0007 — Secretos: tabla cifrada provisional, contrato `secret://`
**Estado:** Propuesta.
**Contexto:** un Vault dedicado es demasiado para el MVP.
**Decisión:** tabla `secrets` cifrada (clave maestra en env/KMS local) y resolución
en runtime vía `secret://key`.
**Consecuencias:** seguridad razonable para empezar; el Vault de Fase 2 sustituye
la implementación sin cambiar cómo los workflows referencian secretos.

### ADR-0008 — Workflow-as-code como fuente de verdad; UI lo consume
**Estado:** Propuesta (deriva de API First + Workflow as Code).
**Contexto:** evitar divergencia entre UI visual y definición.
**Decisión:** YAML/JSON normalizado y versionado (hash) es la verdad; el designer
visual (Fase 2) edita esa misma representación.
**Consecuencias:** import/export e IA-generación triviales; el visual no introduce
un formato paralelo.

### ADR-0009 — Licencia: Open core con núcleo BSL 1.1
**Estado:** Aceptada.
**Contexto:** producto con marketplace y SaaS a futuro; se busca adopción sin que
un proveedor cloud pueda revenderlo como servicio competidor; equipo de 1 dev que
necesita una vía de monetización. Dependencias clave son permisivas (Temporal=MIT,
FastAPI/React), por lo que cualquier licencia propia es viable.
**Decisión:** núcleo bajo **Business Source License 1.1** con cláusula de
no-competencia y *change date* a **Apache 2.0** (~4 años); features premium (SSO/
OIDC, multi-tenancy avanzada, soporte) bajo licencia comercial (modelo open core).
**Consecuencias:** protege el modelo comercial manteniendo el código visible y
adoptable (jugada de n8n); requiere cabeceras de licencia y `LICENSE`/`NOTICE`
claros, y separar el código premium del core desde la estructura del repo.

### ADR-0010 — Idioma del producto: inglés (i18n-ready)
**Estado:** Aceptada.
**Contexto:** mercado objetivo amplio (SMBs); facilitar adopción y comunidad.
**Decisión:** UI y textos de producto en **inglés**; frontend estructurado con
claves de i18n desde el inicio aunque solo exista el locale `en`. La documentación
interna de arranque permanece en español.
**Consecuencias:** traducciones futuras no requieren refactor; coste marginal hoy.

---

## Parte C — ADRs v2 (revisión arquitectónica 2026-06-24)

> Origen: revisión de arquitectura tras releer el paquete completo. Resuelven cinco
> hallazgos de fondo y formalizan mejoras best-practice. Todas **Aceptadas** salvo nota.
> Decisiones de producto que las gatillaron: *producto real a monetizar* (fundaciones
> sólidas) + *arrancar con worker local* (diferir operación de agente remoto).

### ADR-0011 — Determinismo del interpreter (orquestación pura ↔ efectos en activities)
**Estado:** Aceptada.
**Contexto:** un Temporal Workflow debe ser **determinista** o el replay se corrompe en
silencio. El interpreter interpola plantillas `{{ }}`, resuelve el DAG y propaga contexto.
**Decisión:** partición estricta. En **código de workflow** (el interpreter): solo lógica
pura de orquestación del DAG sobre datos ya materializados (resolver `needs`, decidir qué
jobs están listos, recoger outputs). En **activities**: todo I/O, resolución de `secret://`,
acceso a tiempo/aleatoriedad, y **toda interpolación de plantillas con efectos**. La
interpolación pura (sustituir `context.*`/`jobs.*.outputs.*` por valores ya conocidos) puede
ocurrir en el workflow porque es determinista; cualquier filtro no determinista (`now()`,
random) está **prohibido** en el motor de plantillas. Se añaden **replay tests en CI**
(Temporal replay test) que reproducen historiales reales contra el código actual.
**Consecuencias:** replay y recuperación fiables; coste: disciplina en dónde vive cada cosa
y un suite de replay que debe correr en cada cambio del interpreter o del motor de plantillas.

### ADR-0012 — La task queue NO es frontera de seguridad; aislamiento por cripto y namespace
**Estado:** Aceptada.
**Contexto:** el diseño se apoyaba en `agent-<id>` como aislamiento. Pero en Temporal
**cualquier worker autenticado puede hacer poll de cualquier task queue cuyo nombre conozca**;
no es un límite de autorización. Un agente comprometido podría robar tareas de otro agente,
incluidos `command` jobs con secretos.
**Decisión:** la seguridad **no** depende del nombre de la task queue. (a) Los secretos viajan
con **envelope encryption por agente** (ADR-0013): aunque otro worker robe la tarea, no puede
descifrarlos. (b) El resultado se valida contra el **fingerprint** del cert esperado. (c) Para
multi-tenancy *operativa* (Fase 3) se usa **namespace de Temporal por tenant** (el namespace sí
es frontera de autorización), no la task queue. (d) Si/ cuando se adopte mTLS, se restringe por
plugin de autorización qué identidad puede hacer poll de qué cola.
**Consecuencias:** modelo de amenaza honesto; el robo de tareas deja de ser exfiltración de
secretos. Corrige `05-...md` §4.6.

### ADR-0013 — Secretos al agente: par de claves por agente + envelope encryption
**Estado:** Aceptada.
**Contexto:** "el secreto se entrega cifrado y se descifra en memoria" no decía **con qué clave**.
Si fuera la clave maestra del sistema, cada agente la sostendría → un agente comprometido filtra
**todos** los secretos.
**Decisión:** en el enrolamiento, cada agente genera un **par de claves** (junto a su material mTLS).
El servidor, al despachar una actividad a ese agente, cifra **cada secreto** contra la **clave
pública del agente destino** (envelope: clave de datos aleatoria + wrap con la pública del agente).
El agente descifra en memoria solo lo destinado a él, durante la ejecución, y nunca lo persiste.
El agente **jamás** recibe la clave maestra ni acceso a la tabla `secrets`.
**Consecuencias:** compromiso de un agente ⇒ exposición acotada a los secretos que ese agente ya
usaba, no a todos. Requiere registrar la clave pública del agente en `agents` (nueva columna).

### ADR-0014 — Idempotencia y consistencia: WorkflowId determinista; Postgres como proyección
**Estado:** Aceptada.
**Contexto:** la API promete idempotencia en `POST /executions` (cabecera `Idempotency-Key`)
pero no había almacén para ello; y crear la fila `executions(pending)` **y** arrancar el workflow
son dos sistemas → fallo parcial posible (doble escritura).
**Decisión:** el `temporal_workflow_id` se **deriva de forma determinista** de la
`Idempotency-Key` (o de `(workflow_version_id, hash(inputs))` si no se envía). Temporal, con
`WorkflowIdReusePolicy`, **rechaza duplicados** → idempotencia sin tabla extra. La fila de
`executions` se trata como **proyección**: se crea de forma idempotente (upsert por
`temporal_workflow_id`) y su estado lo actualiza el propio workflow/activities. Un reconciliador
ligero repara filas huérfanas consultando a Temporal.
**Consecuencias:** una sola fuente de verdad de "arrancado/no" (Temporal); reintentos de la API
son seguros. Elimina la necesidad de una tabla de idempotency-keys.

### ADR-0015 — Cron vía Temporal Schedules (no un scheduler aparte)
**Estado:** Aceptada.
**Contexto:** el trigger `cron` necesitaba durabilidad; añadir APScheduler/Celery-beat sería otra
pieza con su propio estado.
**Decisión:** los triggers `cron` se implementan con **Temporal Schedules**. Al habilitar/editar/
deshabilitar un workflow, la API crea/actualiza/pausa el Schedule correspondiente; `trigger_config`
(cron + timezone) es la fuente de verdad y se reconcilia con el Schedule.
**Consecuencias:** durabilidad y "catch-up" gratis; una pieza menos. Hay que mantener la
sincronización workflow↔Schedule (un reconciliador o hooks en el CRUD).

### ADR-0016 — Cifrado de payloads en Temporal (Data Converter/Codec)
**Estado:** Aceptada.
**Contexto:** la historia de Temporal **persiste** inputs/outputs de activities y el contexto; sin
cifrar, secretos y datos sensibles quedarían en claro en la base de datos de Temporal.
**Decisión:** se instala un **Data Converter / Payload Codec** que cifra los payloads en el cliente
antes de enviarlos a Temporal y los descifra al recibirlos. La Temporal UI ve solo ciphertext (o
usa el codec server autorizado). Aplica especialmente a payloads que portan secretos o contexto.
**Consecuencias:** datos sensibles cifrados en reposo dentro de Temporal; coste menor de CPU y la
necesidad de gestionar la clave del codec.

### ADR-0017 — Orden de construcción del agente: worker local primero, remoto al final
**Estado:** Aceptada (decisión de producto 2026-06-24).
**Contexto:** producto real a monetizar (exige el agente bien hecho) **pero** 1 dev y cronograma
optimista; la operación del agente remoto (CA, mTLS, enrolamiento) es el mayor sumidero de riesgo.
**Decisión:** construir y validar **todo el contrato** `run_on: agent` con un worker en el mismo
host y task queue dedicada (Hito 3), con el **modelo de seguridad ya correcto** (outputs declarados,
envelope encryption, redacción, aislamiento). El agente **remoto** real (mTLS/enrolamiento) se hace
en un **Hito 5 con timebox**; un retraso ahí no bloquea un MVP funcionalmente completo.
**Consecuencias:** el riesgo crítico queda aislado al final sin sacrificar la solidez del contrato;
la inversión en operación remota se hace solo cuando todo lo demás está verde. Refina ADR-0003.

### ADR-0018 — Observabilidad mínima desde el MVP (OTel + Prometheus + healthchecks)
**Estado:** Aceptada.
**Contexto:** producto "instalable por terceros" ⇒ debe ser operable y diagnosticable.
**Decisión:** trazas con **OpenTelemetry** (Temporal lo integra de forma nativa), métricas
**Prometheus** de API/worker/Temporal, y `/healthz`/`/readyz` por servicio. Se incorpora en el
Hito 4 (endurecimiento).
**Consecuencias:** diagnóstico y SLOs posibles desde el día 1 de uso real; coste de wiring pequeño.

### ADR-0019 — "Plugin" en el MVP = activity built-in + fila de catálogo (no cargador dinámico)
**Estado:** Aceptada (aclaración).
**Contexto:** "Plugin First" podía leerse como un cargador dinámico de código de terceros, lo que
es un problema de seguridad/arquitectura mucho mayor.
**Decisión:** en el MVP, un plugin es una **activity built-in** (command/rest/sql) **más** una fila
en `plugins` con su `input_schema`/`output_schema` (para validación y catálogo de IA). El
contrato común se respeta, pero **no** se carga código externo. El cargador dinámico / marketplace
de plugins de terceros es **Fase 3**.
**Consecuencias:** se evita sobre-ingeniería y superficie de ataque temprana; el patrón de
extensión queda validado con plugins propios y el catálogo ya sirve al futuro Architect.

> Plantilla para nuevos ADR: copiar un bloque, numerar, fijar Estado
> (Propuesta/Aceptada/Rechazada/Reemplazada por ADR-XXXX).
