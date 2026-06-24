# 05 — Protocolo de Agente y Seguridad

> Estado: Borrador para arranque · Fecha: 2026-06-24
> **Este es el componente de mayor riesgo del MVP.** Diseño deliberadamente
> "delgado" para que sea factible con 1 dev sin comprometer seguridad.

## 1. Concepto: "agente delgado"

En lugar de inventar un protocolo agente↔servidor (HTTPS+WebSocket+gRPC propio,
como en el documento original), el agente es **un Temporal worker remoto**:

- Se conecta al **Temporal Server** (no directamente a la API de FlowOps) por
  gRPC sobre TLS.
- Escucha una **task queue exclusiva**: `agent-<agent_id>`.
- Cuando un job tiene `run_on: agent` y un `agent_selector` que resuelve a ese
  agente, el workflow encola la actividad en su task queue; solo ese agente la toma.
- Reintentos, timeouts, heartbeats y recuperación los aporta Temporal.

Ventajas: reutiliza un transporte probado, con seguridad y *durable execution*
gratis; el "Agent Manager" del documento original se reduce a (a) registro/
aprobación en la API y (b) enrutado por task queue/labels.

```
Job (run_on: agent, selector)            Temporal Server
        │  encola actividad      ┌──────────────────────────┐
        └───────────────────────►│ task queue: agent-<id>   │
                                 └─────────────┬────────────┘
                                               │ gRPC/TLS (long-poll)
                                  ┌────────────▼────────────┐
                                  │   Agente (worker)        │
                                  │  ejecuta command job     │
                                  │  reporta heartbeat+result│
                                  └─────────────────────────┘
```

## 2. Alcance del agente en el MVP

| Aspecto | MVP | Fase 2+ |
|--------|-----|---------|
| SO | Linux (binario/contenedor) | Windows, macOS nativos |
| Job types | `command` | scripts firmados, SFTP, file-watcher local |
| Aislamiento | usuario sin privilegios + límites de recursos | contenedor por job |
| Distribución | descarga manual + enrolamiento | auto-update firmado |
| Routing | por `agent_selector` (labels) | pools, afinidad, balanceo |

## 3. Ciclo de vida y enrolamiento

1. **Solicitud (API):** admin llama `POST /api/v1/agents/enroll` → recibe un
   **enrollment token** de un solo uso (corta expiración) + endpoint de Temporal.
2. **Instalación:** el operador ejecuta el agente en la máquina destino con el
   token (variable de entorno o flag). El agente genera un par de claves y una CSR.
3. **Registro:** el agente presenta el enrollment token a la API; la API crea el
   registro en estado `pending_approval`, firma el certificado del agente (CA
   interna) con un **fingerprint** asociado y lo devuelve.
4. **Aprobación:** admin revisa y llama `POST /api/v1/agents/{id}/approve`. Hasta
   aquí el agente **no** puede tomar tareas.
5. **Conexión:** el agente, ya aprobado, se conecta a Temporal con **mTLS** usando
   su certificado y empieza a hacer long-poll de su task queue.
6. **Heartbeat:** durante cada actividad larga, reporta heartbeats (Temporal);
   además, latido periódico → `agents.last_heartbeat_at`. Sin latido → `offline`.
7. **Revocación:** `POST /api/v1/agents/{id}/revoke` invalida el certificado
   (lista de revocación) y marca `revoked`; deja de poder conectarse.

## 4. Modelo de seguridad

### 4.1 Identidad y transporte
- **mTLS** agente↔Temporal: cada agente tiene su certificado emitido por una CA
  interna de FlowOps. El `fingerprint` se persiste y se valida.
- El agente **nunca** recibe credenciales del tenant ni acceso a la base de datos.
- Toda comunicación cifrada en tránsito (TLS 1.2+).

### 4.2 Aprobación explícita (no trust on first use)
Ningún agente ejecuta nada hasta ser aprobado por un admin. Enrollment tokens de
un solo uso y caducidad corta evitan auto-registro malicioso.

### 4.3 Manejo de secretos (v2 — envelope encryption por agente, ADR-0013)
- Los `command`/`sql` jobs que requieran credenciales usan `secret://<key>`.
- La resolución del secreto ocurre **lo más tarde posible**:
  - server-side: el worker del servidor resuelve el secreto desde `secrets`.
  - agente: el secreto se entrega **cifrado contra la clave pública del agente destino**
    (envelope encryption: clave de datos aleatoria + wrap con la pública del agente,
    registrada en `agents.public_key` durante el enrolamiento). El agente lo descifra
    **en memoria** solo durante la ejecución; **nunca** se persiste en disco ni en logs.
- **Modelo de clave (crítico):** el agente **nunca** recibe la clave maestra del sistema
  ni acceso a la tabla `secrets`. Solo puede descifrar lo destinado específicamente a él.
  Compromiso de un agente ⇒ exposición acotada a los secretos que ese agente ya usaba,
  **no** a todos los del tenant.
- Logs y outputs pasan por un **redactor** que enmascara valores de secretos.
- Los payloads de actividad (que portan estos secretos cifrados y el contexto) van además
  por un **Data Converter/Codec cifrado** hacia Temporal, para que no queden en claro en la
  historia persistida de Temporal (ADR-0016).

### 4.4 Aislamiento de ejecución (`command` jobs)
- MVP: el agente ejecuta comandos como **usuario dedicado sin privilegios**, con
  límites de CPU/memoria/tiempo (cgroups/ulimit) y un `working_dir` efímero que se
  limpia al terminar.
- Fase 2: ejecución de cada job en un **contenedor** descartable (mayor aislamiento).
- Lista negra/allow-list de comandos configurable por agente (defensa en profundidad).

### 4.5 Autorización en la API
- JWT + RBAC (matriz en `04-...md` §A.8). Solo `admin` aprueba/revoca agentes.
- Toda acción sensible (aprobar agente, editar secreto, etc.) → `audit_log`.

### 4.6 Aislamiento y multi-tenant (v2 — la task queue NO es frontera de seguridad, ADR-0012)
> **Corrección importante.** En Temporal, **cualquier worker autenticado puede hacer poll
> de cualquier task queue cuyo nombre conozca**: el nombre `agent-<id>` **no** es un límite
> de autorización. Un agente comprometido podría intentar robar tareas de otro. La seguridad
> **no** puede depender del nombre de la cola. El aislamiento real se consigue así:

- **Cripto, no nombres:** los secretos viajan con envelope encryption por agente (§4.3), de
  modo que robar una tarea ajena **no** descifra sus secretos.
- **Validación por fingerprint:** el resultado de una actividad se valida contra el
  `fingerprint` del cert esperado para ese agente; un resultado de otra identidad se rechaza.
- **Namespace por tenant (multi-tenancy operativa, Fase 3):** el aislamiento *fuerte* entre
  tenants usa **un namespace de Temporal por tenant** (el namespace **sí** es frontera de
  autorización), no la task queue. En el MVP (un solo tenant operativo) basta con la cripto
  por agente y el filtrado en la capa de API.
- **Autorización mTLS (cuando aplique):** con el plugin de autorización de Temporal se puede
  restringir qué identidad de cert hace poll de qué cola, como defensa en profundidad.
- Cada agente pertenece a un `tenant_id`; un job de un tenant **no** puede enrutarse a un
  agente de otro (validado en la asignación, reforzado por namespace en Fase 3).

## 5. Resultado, logs y artefactos
- La actividad del agente devuelve un resultado estructurado (status, exit code,
  output corto, refs de artefactos).
- Logs voluminosos y artefactos se suben directamente a **MinIO** (URL
  pre-firmada emitida por la API); en Postgres solo quedan referencias.
- **Ruta de eventos en vivo (v2, aclarada):** el **worker/activity** escribe el evento en
  `execution_events` (Postgres, auditoría) y lo **publica directamente en Redis**; el
  WebSocket de la API se **suscribe a Redis** y lo empuja a la UI. Temporal **no** empuja
  eventos a suscriptores externos; el salto "vía API" no es el camino (la API solo expone
  el WebSocket). Para **tail de stdout en vivo** de un `command` largo, el agente emite
  líneas vía **heartbeat de actividad** (últimas N líneas) y/o las vuelca a MinIO; el
  resultado final lleva la referencia al log completo.

## 6. Orden de construcción (v2 — worker local primero, ADR-0017)
El "plan B" pasa a ser la **ruta primaria del MVP**: se construye el contrato completo
con un worker local y el agente remoto se aísla a un hito final con timebox.
1. **Hito 3 — worker local:** ejecutar el "agente" como un worker en el **mismo host** que
   el servidor (mismo binario, **task queue dedicada** `agent-local`), validando todo el flujo
   `run_on: agent` **con el modelo de seguridad ya correcto** (outputs declarados, envelope
   encryption por agente, redacción, usuario sin privilegios + límites, aislamiento por tenant).
2. **Hito 5 — agente remoto:** añadir CA interna, enrolamiento, mTLS y la operación
   multi-máquina. Un retraso aquí **no bloquea** un MVP ya demostrable.

Esto preserva el contrato (`run_on: agent`, selectors, envelope encryption) y permite demostrar
la vertical distribuida completa **antes** de invertir en la operación de agentes remotos.
Posponer multi-OS y auto-update a Fase 2.

## 7. Checklist de seguridad

**Contrato (Hito 3, worker local) — el modelo de seguridad ya debe ser correcto:**
- [ ] Outputs declarados (sin mutación de contexto global) — base determinista (ADR-0011/0013).
- [ ] Resolución tardía de secretos con **envelope encryption por agente** + redacción en logs.
- [ ] Ejecución como usuario sin privilegios + límites de recursos (cgroups/ulimit) + workdir efímero.
- [ ] Aislamiento por tenant en la asignación (no confiar en el nombre de la task queue — ADR-0012).
- [ ] Cifrado de payloads hacia Temporal (Data Converter/Codec — ADR-0016).
- [ ] Auditoría de todas las acciones sobre agentes y secretos.

**Operación remota (Hito 5, agente real):**
- [ ] CA interna y emisión/renovación de certificados de agente.
- [ ] Enrollment tokens de un solo uso con expiración.
- [ ] Aprobación explícita de admin antes de ejecutar (no trust-on-first-use).
- [ ] mTLS verificado por fingerprint; clave pública del agente registrada para envelope encryption.
- [ ] Revocación efectiva (CRL/denylist) probada.
- [ ] (Multi-tenancy operativa) Namespace de Temporal por tenant.
