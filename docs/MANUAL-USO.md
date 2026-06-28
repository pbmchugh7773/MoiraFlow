# MoiraFlow — Manual de Uso y Troubleshooting

Cómo usar MoiraFlow día a día: crear workflows, lanzarlos, monitorearlos en vivo, y
resolver los problemas más comunes. Para instalar el stack ver
**[MANUAL-INSTALACION.md](MANUAL-INSTALACION.md)**.

---

## 1. Conceptos en 30 segundos

- **Workflow** = un DAG de **jobs** definido **como código** (YAML/JSON). Cada versión
  guardada es **inmutable** (content-hashed).
- **Job** = una unidad de trabajo. Tipos en el MVP: `command` (shell), `rest` (HTTP),
  `sql`. Los jobs se encadenan con `needs` (dependencias).
- **Ejecución** = una corrida durable del workflow sobre Temporal. Idempotente: misma
  versión + mismos inputs = la misma corrida.
- **Replay** = volver a correr una ejecución (nueva corrida fresca, no muta la original).
- **Trigger** = qué dispara el workflow: `manual`, `cron` (Temporal Schedule) o `webhook`.
- **Agente** = worker remoto que corre jobs `command` en una máquina del cliente
  (`run_on: agent`).

---

## 2. Login y roles

Entrá en **http://localhost:5173** con tu usuario. Los roles (RBAC) determinan qué podés
hacer:

| Rol | Leer | Lanzar ejecuciones | Crear/editar workflows | Admin (users/secrets/agents) |
|---|:--:|:--:|:--:|:--:|
| `viewer` | ✅ | ❌ | ❌ | ❌ |
| `operator` | ✅ | ✅ | ❌ | ❌ |
| `developer` | ✅ | ✅ | ✅ | ❌ |
| `admin` | ✅ | ✅ | ✅ | ✅ |

---

## 3. Crear un workflow

### Opción A — Editor visual (recomendado)

En **Workflows → New workflow**:

1. **Nombre** y **Trigger** (manual / cron) arriba.
2. **Workflow inputs (context)**: declarás parámetros del workflow (clave → valor por
   defecto). Se referencian en los jobs con `{{ context.<clave> }}` y se pueden
   sobreescribir al lanzar.
3. **Pestaña Visual**: arrastrá tipos de job (command/rest/sql) desde la paleta al lienzo.
   Arrastrá del conector de un nodo al de otro para crear una dependencia (`needs`). Doble
   click en un conector — o seleccionarlo y `Supr` — para borrarlo.
4. **Click en un nodo** → panel de **propiedades** a la derecha (id, tipo, run_on,
   campos del job, parámetros, outputs, condition, timeout, reintentos).
5. **Pestaña Code**: muestra el YAML generado en vivo (read-only). Botón **Copy**.
6. **Validate** chequea contra el esquema; **Create** guarda el workflow (v1, activa).

Para **modificar** un workflow existente: abrilo → **Edit** → guardás como **nueva
versión** (se activa automáticamente). Las versiones viejas quedan inmutables.

### Opción B — YAML/JSON o API

Pegá/escribí el YAML y mandalo a `POST /workflows`. Ejemplo mínimo:

```yaml
apiVersion: moiraflow/v1
kind: Workflow
metadata: { name: daily_import }
spec:
  trigger: { type: manual }
  context: { mode: run }            # inputs declarados (override al lanzar)
  jobs:
    - id: fetch
      type: rest
      retry: { max_attempts: 2 }
      with:
        method: GET
        url: https://api.example.com/data
        expect_status: [200]
    - id: process
      type: command
      needs: [fetch]
      condition: "{{ context.mode }} == run"   # corre solo si la condición es true
      with:
        command: echo processing
        env: { STAGE: prod }                   # parámetros (env del proceso)
      outputs: { ok: "yes" }
```

---

## 4. Tipos de job y sus campos

| Tipo | `with` | Parámetros (panel) → | Notas |
|---|---|---|---|
| `command` | `command`, `artifacts?` | `env` (variables de entorno) | corre un shell command aislado (non-root, rlimits, workdir efímero). `artifacts` = archivos a subir a MinIO |
| `rest` | `method`, `url`, `body?`, `expect_status?` | `headers` | captura la respuesta en `outputs.status` y `outputs.body` |
| `sql` | `connection`, `statement` | `params` | `connection` puede ser un DSN o `secret://<clave>` |

**Campos comunes** (en el panel de propiedades): `needs` (vía conectores), `condition`,
`timeout` (ej. `30s`), `max_attempts` (reintentos), `outputs` (expresiones
`{{ jobs.<id>.outputs.<k> }}`), `run_on` (`server` o `agent`).

### Condiciones (`condition`)
Un job con `condition` corre solo si la expresión es verdadera; si no, se **salta**
(status `skipped`) y sus dependientes también (cascada). Formas soportadas:
- Una expresión: `{{ context.enabled }}` (truthy: no vacío, no `false`/`0`/`no`/`off`).
- Una comparación: `{{ context.env }} == prod`, `{{ context.count }} > 0`
  (operadores `== != >= <= > <`).

### Manejo de fallos (`spec.on_error`)
A nivel workflow, decide qué pasa cuando un job falla:
- **`fail`** (default): un job que falla **aborta** toda la ejecución (status `failed`).
- **`continue`**: el fallo se **tolera** — la corrida sigue con los branches alcanzables
  (los dependientes del job fallido se saltan en cascada), y la ejecución **completa**
  (`success`). Los jobs fallidos quedan visibles como `failed` en el detalle. Útil para
  pasos opcionales/best-effort.

```yaml
spec:
  on_error: continue
  jobs:
    - { id: optional_sync, type: rest, with: { method: GET, url: https://flaky.io } }
    - { id: report, type: command, with: { command: echo always-runs } }  # corre igual
```

---

## 5. Lanzar y monitorear

### Lanzar
Desde el detalle del workflow: **Launch**. Si el workflow declara `context`, se abre un
panel donde podés **sobreescribir los inputs** para esa corrida (texto o JSON). Si no
declara inputs, podés agregar pares ad-hoc o simplemente correr.

### Monitor en vivo (detalle de ejecución)
- **Estado** + badge **live** (WebSocket) cuando está corriendo.
- **The weave**: el DAG con el estado por job (running/success/failed/skipped).
- **Logs**: stdout/stderr de los `command` en streaming, **con timestamp por línea** y
  los secretos **redactados** (`***`). Los `rest` muestran una línea `→ 200 {...}` con la
  respuesta.
- **Artifacts**: archivos subidos, con descarga (URL presignada).
- **Event stream**: la línea de tiempo de eventos de ciclo de vida.

### Replay y Cancel
- **Replay** (en el detalle): vuelve a correr la **misma versión + mismos inputs** como
  una corrida **nueva** (id nuevo). No muta la original. Aparece como una fila nueva con
  trigger `replay`.
- **Cancel**: detiene una ejecución en curso (marca `cancelled` y pide la cancelación a
  Temporal).

> **Idempotencia:** lanzar el mismo workflow+versión+inputs **devuelve la misma corrida**
> (por diseño, ADR-0014). Para forzar una corrida nueva: usá **Replay** o cambiá los inputs.

---

## 6. Triggers

- **manual**: lo lanzás vos (UI/API).
- **cron**: `trigger: { type: cron, cron: "0 6 * * *", timezone: "Europe/Madrid" }` →
  se registra como un **Temporal Schedule**. Activar/desactivar el workflow pausa/reanuda
  el schedule.
- **webhook**: `POST /hooks/{workflow_id}?token=<token>` (sin JWT). El token lo emite el
  server al crear el workflow y vive fuera de la definición. Lanza con trigger `webhook`.

---

## 7. Secretos, usuarios y agentes (admin)

- **Secrets**: guardás `clave → valor` cifrados; los referenciás como `secret://<clave>`
  (ej. en `connection` de un `sql`). El worker los resuelve **tarde** y en memoria; nunca
  tocan disco y se **redactan** en logs/errores.
- **Users**: crear usuarios, asignar rol, activar/desactivar.
- **Agents**: ciclo de vida del agente remoto — enroll (token de un solo uso) → register
  (CSR firmado por el CA interno) → **approve** (aprobación explícita, sin trust-on-first-use)
  → revoke. Un agente revocado no puede operar (gate de revocación).

---

## 8. Troubleshooting

### 🔴 "La ejecución no avanza / queda en `running`"
Casi siempre es **un job que falla y reintenta**. Causas típicas:
- **URL inalcanzable o inválida** en un `rest`. Desde el contenedor worker, `localhost`
  **es el propio contenedor**, no tu host → usá **`host.docker.internal`** (o el nombre de
  servicio del compose, p.ej. `http://api:8000`). Una URL incompleta como `https://` (el
  placeholder sin llenar) falla.
- **Qué hacer:** abrí el detalle de la ejecución y mirá qué job está en `running`/`failed`;
  revisá `docker compose logs worker` para el error real.

> La plataforma ya acota esto: los jobs sin `retry` tienen **tope de 3 intentos** por
> defecto, y errores **permanentes** (URL inválida, secreto inexistente) fallan en el
> **intento 1** (no-reintentables). Así una mala config **falla rápido** en vez de colgar
> la corrida. Igual conviene declarar `retry`/`expect_status` en jobs `rest`.

### 🟠 "Launch failed"
- El workflow **no tiene versión activa** → activá una versión (o creá/edítalo).
- Una corrida con esa misma versión+inputs **ya existe** (idempotencia) → es esperado; usá
  **Replay** para una corrida nueva.

### 🟡 "Hice replay y sale vacío / sin logs"
Los eventos de UI viajan por Redis. Si el API se reinició justo mientras corría, antes se
perdían (ahora el feed es **durable con Redis Streams** y se recuperan al reconectar). Si
ves una corrida vieja vacía: **igual se ejecutó OK en Temporal** — el estado se
**auto-reconcilia** a `success` al abrir/listar la ejecución. Para una corrida nueva con
logs completos, hacé Replay de nuevo.

### "La validación falla con `Input should be a valid string` en un output `yes`/`no`"
En YAML 1.1 (el parser del API), `yes/no/on/off/true/false` son booleanos. El **editor
visual ya los cita** automáticamente. Si escribís YAML **a mano**, poné comillas:
`done: "yes"`.

### "No veo el JSON que devolvió un `rest`"
Ahora sí: queda en `jobs.<id>.outputs.body` (+ `outputs.status`) y aparece como una línea
de **Logs** (`→ 200 {...}`). Referencialo en jobs posteriores con
`{{ jobs.<id>.outputs.body }}`.

### "La lista de ejecuciones tarda en actualizar"
La lista refresca cada ~1.5s; el **detalle** de la ejecución es en **vivo** (WebSocket).
El motor en sí termina un workflow trivial en decenas de milisegundos.

### "Se pegó todo / el API no responde"
Reiniciá el API: `docker compose restart api`. (El deadlock del subscriber que causaba
esto ya está corregido; el subscriber hace su I/O fuera del event loop.)

### "Un job `command` no encuentra un archivo / falla raro"
Corre en un **workdir efímero** como usuario no privilegiado con límites de CPU/memoria.
Usá rutas relativas para `artifacts` (se resuelven contra el workdir) o rutas absolutas.

### Secretos en logs
Los valores `secret://` y contraseñas en URLs se **redactan** automáticamente (`***`).
Si ves un secreto en claro, reportalo: es un bug del redactor.

### Reset de datos de prueba
Ver **[MANUAL-INSTALACION.md](MANUAL-INSTALACION.md) → §7** (script SQL de limpieza).

---

## 9. Referencia rápida (API)

```bash
TOKEN=$(curl -s localhost:8001/api/v1/auth/login -H 'content-type: application/json' \
  -d '{"email":"admin@moiraflow.local","password":"admin"}' | jq -r .access_token)
AUTH=(-H "authorization: Bearer $TOKEN")

curl -s localhost:8001/api/v1/workflows "${AUTH[@]}"                       # listar workflows
curl -s localhost:8001/api/v1/workflows/validate "${AUTH[@]}" \           # validar sin guardar
  -H 'content-type: application/json' -d '{"content":"...yaml...","format":"yaml"}'
curl -s localhost:8001/api/v1/executions "${AUTH[@]}" \                    # lanzar
  -H 'content-type: application/json' -d '{"workflow_id":"<id>","input_context":{"mode":"run"}}'
curl -s "localhost:8001/api/v1/executions/<id>/events" "${AUTH[@]}"        # eventos
curl -s "localhost:8001/api/v1/executions/<id>/jobs" "${AUTH[@]}"          # estado por job
curl -s -X POST "localhost:8001/api/v1/executions/<id>/replay" "${AUTH[@]}"  # replay
curl -s -X POST "localhost:8001/api/v1/executions/<id>/cancel" "${AUTH[@]}"  # cancelar
```

La referencia completa (interactiva) está en **Swagger**:
http://localhost:8001/api/v1/docs
