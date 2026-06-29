# MoiraFlow — User Guide & Troubleshooting

How to use MoiraFlow day to day: authoring workflows, launching them, monitoring them
live, and resolving the most common problems. To install the stack, see the
**[Installation & Setup Guide](INSTALLATION.md)**.

---

## 1. Concepts in 30 seconds

- A **workflow** is a DAG of **jobs** defined **as code** (YAML/JSON). Every saved version
  is **immutable** (content-hashed).
- A **job** is one unit of work. The MVP supports three types: `command` (shell), `rest`
  (HTTP), and `sql`. Jobs are chained with `needs` (dependencies).
- An **execution** is a durable run of the workflow on Temporal. It is idempotent: the same
  version and inputs always map to the same run.
- A **replay** re-runs a past execution as a fresh, independent run — it never mutates the
  original.
- A **trigger** is what starts a workflow: `manual`, `cron` (a Temporal Schedule), or
  `webhook`.
- An **agent** is a remote worker that runs `command` jobs on a customer machine
  (`run_on: agent`).

---

## 2. Signing in and roles

Open **http://localhost:5173** and sign in. Your role (RBAC) determines what you can do:

| Role | Read | Launch executions | Author/edit workflows | Admin (users/secrets/agents) |
|---|:--:|:--:|:--:|:--:|
| `viewer` | ✅ | ❌ | ❌ | ❌ |
| `operator` | ✅ | ✅ | ❌ | ❌ |
| `developer` | ✅ | ✅ | ✅ | ❌ |
| `admin` | ✅ | ✅ | ✅ | ✅ |

---

## 3. Authoring a workflow

### Option A — Visual editor (recommended)

In **Workflows → New workflow**:

1. Set the **Name** and **Trigger** (manual / cron) at the top.
2. **Workflow inputs (context):** declare the workflow's parameters (key → default value).
   Reference them in jobs as `{{ context.<key> }}`, and override them at launch time.
3. **Visual tab:** drag job types (command/rest/sql) from the palette onto the canvas. Drag
   from one node's connector handle to another's to create a dependency (`needs`).
   Double-click a connector — or select it and press `Delete` — to remove it.
4. **Click a node** to open its **properties** panel on the right (id, type, run_on, the
   job's fields, parameters, outputs, condition, timeout, retries).
5. **Code tab:** shows the generated YAML live (read-only), with a **Copy** button.
6. **Validate** checks the definition against the schema; **Create** saves the workflow
   (version 1, set active).

To **modify** an existing workflow, open it and click **Edit**. Saving creates a **new
version** (activated automatically); older versions remain immutable.

### Option B — YAML/JSON or API

Write the YAML and submit it to `POST /workflows`. A minimal example:

```yaml
apiVersion: moiraflow/v1
kind: Workflow
metadata: { name: daily_import }
spec:
  trigger: { type: manual }
  context: { mode: run }            # declared inputs (overridable at launch)
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
      condition: "{{ context.mode }} == run"   # runs only if the condition is true
      with:
        command: echo processing
        env: { STAGE: prod }                   # parameters (process environment)
      outputs: { ok: "yes" }
```

---

## 4. Job types and fields

| Type | `with` | Parameters (panel) map to → | Notes |
|---|---|---|---|
| `command` | `command`, `artifacts?` | `env` (environment variables) | runs a shell command in isolation (non-root, rlimits, ephemeral workdir). `artifacts` lists files to upload to MinIO |
| `rest` | `method`, `url`, `body?`, `expect_status?` | `headers` | captures the response into `outputs.status` and `outputs.body` |
| `sql` | `connection`, `statement` | `params` | `connection` is a DSN or a `secret://<key>` reference |
| `transform` | `format` (csv/json/xml), `content?` or `url?` | — (uses `outputs` for paths) | parses a file/payload and extracts values; see below |
| `file_transfer` | `source`, `destination`, `credentials?` | — | moves a file between schemes (http/s3/artifact/sftp); see below |

### Parsing and extracting data (`transform`)

A `transform` job parses a csv/json/xml payload and pulls values out into outputs. The
data comes from inline `content` (often templated from a previous job) or a `url` to
download; each declared **output is a path expression** evaluated against the parsed data.

```yaml
- id: parse
  type: transform
  with:
    format: csv
    content: "{{ jobs.fetch.outputs.body }}"   # or a URL, or pasted raw data
  outputs:
    rows: "$.length"            # number of rows/items
    first_email: "$[0].email"   # a field of the first row
    all_names: "items[*].name"  # project a field across a list
```

Path mini-language: `$` (whole document), `$.a.b` (nested keys), `$[0]` (index),
`$.length` (count of a list), `items[*].field` (project a key across a list). Malformed
data or an unresolvable path fails the job immediately (non-retryable).

### Moving files (`file_transfer`)

A `file_transfer` job reads a file from `source` and writes it to `destination`. Both
are URIs; supported schemes:

| Scheme | Read | Write | Notes |
|---|:--:|:--:|---|
| `https://` / `http://` | ✅ | — | download |
| `s3://bucket/key` | ✅ | ✅ | S3 / MinIO object |
| `artifact://key` | ✅ | ✅ | the MoiraFlow artifacts bucket — a write becomes a **downloadable execution artifact** |
| `sftp://host/path` | ✅ | ✅ | SFTP; credentials via `secret://` |

```yaml
- id: pull
  type: file_transfer
  with:
    source: sftp://files.acme.com/outbox/orders.csv
    destination: artifact://orders.csv          # appears under the run's Artifacts
    credentials: secret://acme_sftp             # JSON: {"username","password"} or {"username","private_key"}
```

Outputs: `size` (bytes) and, for an `artifact://` destination, `artifact_key`. Use
`credentials` for the SFTP side, or `source_credentials` / `destination_credentials` when
both sides are SFTP. Transfers are held in memory and capped at 100 MB. A bad scheme or an
oversized file fails immediately (non-retryable).

**SFTP credentials** are a `secret://` resolving to JSON:

```json
{ "username": "u", "password": "p" }
{ "username": "u", "private_key": "-----BEGIN OPENSSH PRIVATE KEY-----\n..." }
```

Add `"host_key"` to **pin the server's host key** — the value is the line from
`ssh-keyscan <host>` (e.g. `"ssh-ed25519 AAAA..."`). When pinned, a server presenting a
different key is rejected (protects against man-in-the-middle). Without a `host_key` the
client trusts the host on first connection; **pin it in production.**

**Common fields** (in the properties panel): `needs` (via connectors), `condition`,
`timeout` (e.g. `30s`), `max_attempts` (retries), `outputs` (expressions of the form
`{{ jobs.<id>.outputs.<key> }}`), and `run_on` (`server` or `agent`).

### Conditions (`condition`)

A job with a `condition` runs only if the expression is true; otherwise it is **skipped**
(status `skipped`), and so are its dependents (cascade). Supported forms:

- A single expression: `{{ context.enabled }}` (truthy = non-empty and not
  `false`/`0`/`no`/`off`).
- A comparison: `{{ context.env }} == prod`, `{{ context.count }} > 0`
  (operators `== != >= <= > <`).

### Error handling (`spec.on_error`)

Set at the workflow level, this decides what happens when a job fails:

- **`fail`** (default): a failed job **aborts** the whole execution (status `failed`).
- **`continue`**: the failure is **tolerated** — the run keeps going on the reachable
  branches (dependents of the failed job cascade-skip), and the execution **completes**
  (`success`). Failed jobs remain visible as `failed` in the execution detail. Useful for
  optional / best-effort steps.

```yaml
spec:
  on_error: continue
  jobs:
    - { id: optional_sync, type: rest, with: { method: GET, url: https://flaky.io } }
    - { id: report, type: command, with: { command: echo always-runs } }  # runs anyway
```

---

## 5. Launching and monitoring

### Launching

From the workflow detail page, click **Launch**. If the workflow declares `context`, a
panel opens where you can **override the inputs** for that run (plain text or JSON). If it
declares no inputs, you can add ad-hoc key/value pairs or simply run it.

### Live monitor (execution detail)

- **Status** plus a **live** badge (WebSocket) while the run is in progress.
- **The weave:** the DAG with per-job status (running / success / failed / skipped).
- **Logs:** streamed stdout/stderr of `command` jobs, **timestamped per line**, with
  secrets **redacted** (`***`). `rest` jobs emit a `→ 200 {...}` line with the response.
- **Artifacts:** uploaded files, downloadable via presigned URLs.
- **Event stream:** the lifecycle event timeline.

### Replay and cancel

- **Replay** (on the detail page) re-runs the **same version and inputs** as a **new** run
  (new id). It does not mutate the original; it appears as a new row with the `replay`
  trigger.
- **Cancel** stops an in-progress execution (marks it `cancelled` and requests cancellation
  from Temporal).

> **Idempotency:** launching the same workflow + version + inputs **returns the same run**
> (by design, ADR-0014). To force a fresh run, use **Replay** or change the inputs.

---

## 6. Triggers

- **manual:** you start it (UI or API).
- **cron:** `trigger: { type: cron, cron: "0 6 * * *", timezone: "Europe/Madrid" }` is
  registered as a **Temporal Schedule**. Enabling/disabling the workflow pauses/resumes the
  schedule.
- **webhook:** `POST /hooks/{workflow_id}?token=<token>` (no JWT). The server issues the
  token when the workflow is created and keeps it outside the definition. The run is tagged
  with the `webhook` trigger.

---

## 7. Secrets, users, and agents (admin)

- **Secrets:** store `key → value` pairs encrypted at rest, then reference them as
  `secret://<key>` (for example in a `sql` job's `connection`). The worker resolves them
  **late** and in memory only; they never touch disk and are **redacted** from logs and
  errors.
- **Users:** create users, assign roles, activate/deactivate.
- **Agents:** the remote-agent lifecycle — enroll (single-use token) → register (CSR signed
  by the internal CA) → **approve** (explicit approval, no trust-on-first-use) → revoke. A
  revoked agent cannot operate (the revocation gate blocks it). To install and run an agent
  on a machine, see the **[Installation Guide → Installing a remote agent](INSTALLATION.md#11-installing-a-remote-agent)**.

### Running a job on an agent (`run_on: agent`)

By default jobs run on the server worker. To run a `command` job on a specific agent
machine instead, set `run_on: agent` and select the target with `agent_selector`:

```yaml
jobs:
  - id: on_prem_backup
    type: command
    run_on: agent
    agent_selector: { agent_id: "<agent_id>" }   # routes to the queue agent-<id>
    with: { command: ./backup.sh }
```

How it routes: the interpreter still runs on the server, but the job's activity is enqueued
on the agent's exclusive task queue (`agent-<id>`), so only that agent picks it up. With no
`agent_selector`, it routes to the local agent (`agent-local`). The agent runs **only**
`command` jobs and never receives database access, tenant credentials, or the secrets
master key — secrets are sealed per-agent (envelope encryption) so a stolen task can't leak
them.

A job sent to an agent that is offline or revoked simply waits in the queue (and a revoked
agent can't reconnect to pick it up); approve/enable the agent to drain it, or cancel the
execution.

---

## 8. Quick API reference

```bash
TOKEN=$(curl -s localhost:8001/api/v1/auth/login -H 'content-type: application/json' \
  -d '{"email":"admin@moiraflow.local","password":"admin"}' | jq -r .access_token)
AUTH=(-H "authorization: Bearer $TOKEN")

curl -s localhost:8001/api/v1/workflows "${AUTH[@]}"                       # list workflows
curl -s localhost:8001/api/v1/workflows/validate "${AUTH[@]}" \           # validate (no save)
  -H 'content-type: application/json' -d '{"content":"...yaml...","format":"yaml"}'
curl -s localhost:8001/api/v1/executions "${AUTH[@]}" \                    # launch
  -H 'content-type: application/json' -d '{"workflow_id":"<id>","input_context":{"mode":"run"}}'
curl -s "localhost:8001/api/v1/executions/<id>/events" "${AUTH[@]}"        # events
curl -s "localhost:8001/api/v1/executions/<id>/jobs" "${AUTH[@]}"          # per-job status
curl -s -X POST "localhost:8001/api/v1/executions/<id>/replay" "${AUTH[@]}"  # replay
curl -s -X POST "localhost:8001/api/v1/executions/<id>/cancel" "${AUTH[@]}"  # cancel
```

The complete, interactive reference lives in **Swagger**:
http://localhost:8001/api/v1/docs

---

## 9. Troubleshooting

### An execution won't advance / stays `running`

This is almost always **a job that keeps failing and retrying**. Common causes:

- **An unreachable or malformed URL in a `rest` job.** From inside the worker container,
  `localhost` is **the container itself**, not your host — use **`host.docker.internal`**
  (or the Compose service name, e.g. `http://api:8000`). An incomplete URL such as
  `https://` (the unfilled placeholder) will fail.
- **What to do:** open the execution detail and see which job is `running`/`failed`; check
  `docker compose logs worker` for the real error.

> The platform already bounds this: jobs without an explicit `retry` get a default cap of
> **3 attempts**, and clearly **permanent** errors (invalid URL, missing secret) fail on the
> **first attempt** (non-retryable). A misconfiguration therefore **fails fast** instead of
> wedging the run. Still, declaring `retry` / `expect_status` on `rest` jobs is good practice.

### "Launch failed"

- The workflow has **no active version** — activate one (or create/edit the workflow).
- A run with the same version and inputs **already exists** (idempotency) — this is
  expected; use **Replay** for a fresh run.

### A replay shows up empty / without logs

UI events travel over Redis. If the API restarts mid-run, those events used to be lost;
the feed is now **durable (Redis Streams)** and replays them on reconnect. If you see an
older empty run, it still **executed successfully in Temporal** — its status
**self-reconciles** to `success` when you open or list it. For a fresh run with complete
logs, replay it again.

### Validation fails with `Input should be a valid string` on a `yes`/`no` output

In YAML 1.1 (the API's parser), `yes`/`no`/`on`/`off`/`true`/`false` are booleans. The
**visual editor quotes them automatically**. If you write YAML **by hand**, quote such
values: `done: "yes"`.

### I can't see the JSON a `rest` job returned

You can now: it is captured in `jobs.<id>.outputs.body` (alongside `outputs.status`) and
appears as a **Logs** line (`→ 200 {...}`). Reference it in downstream jobs as
`{{ jobs.<id>.outputs.body }}`.

### The executions list is slow to update

The list refreshes about every 1.5s; the execution **detail** page is **live** (WebSocket).
The engine itself finishes a trivial workflow in tens of milliseconds.

### Everything froze / the API stopped responding

Restart the API: `docker compose restart api`. (The subscriber deadlock that used to cause
this is fixed — the subscriber now does its database I/O off the event loop.)

### A `command` job can't find a file / fails oddly

It runs in an **ephemeral workdir** as an unprivileged user with CPU/memory limits. Use
relative paths for `artifacts` (resolved against the workdir) or absolute paths.

### A job routed to an agent never runs

A `run_on: agent` job is enqueued on `agent-<id>` and only that agent picks it up. If it
sits pending: the agent may be **offline** (not running / can't reach Temporal), **not yet
approved**, or **revoked** (a revoked agent can't reconnect). Check the agent's status under
**Agents**, confirm its process is up and pointed at the right `TEMPORAL_HOST` /
`MOIRAFLOW_AGENT_QUEUE`, and that `agent_selector.agent_id` matches. See the
**[Installation Guide → Installing a remote agent](INSTALLATION.md#11-installing-a-remote-agent)**.

### Secrets in logs

`secret://` values and passwords embedded in URLs are **redacted** automatically (`***`).
If you ever see a secret in clear text, please report it — that's a redactor bug.

### Resetting test data

See the **[Installation Guide → Common operations](INSTALLATION.md#8-common-operations)** for
the cleanup SQL script.
