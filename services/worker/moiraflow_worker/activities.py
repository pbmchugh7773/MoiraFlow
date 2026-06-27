"""Server-side job activities. All I/O lives here (never in workflow code).

MVP implements `command`; `rest` and `sql` arrive in the next slice. Activities
run with retries/timeouts supplied by the workflow (mapped from each job's retry
policy). A `command` job intentionally runs a shell command — isolation
(unprivileged user, resource limits, redaction) is handled per docs 05 §4.4 and
is orthogonal to this execution contract.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import uuid
from collections.abc import Callable
from typing import Any

import httpx
from temporalio import activity

from .events import get_redis, publish_to_redis
from .interpreter import JobRequest, JobResult
from .isolation import apply_limits
from .secrets import redact, resolve_reference
from .storage import upload_artifacts


@activity.defn(name="publish_event")
def publish_event(event: dict[str, Any]) -> None:
    """Best-effort: publish a lifecycle event to Redis; never fail the workflow."""
    try:
        publish_to_redis(get_redis(), event)
    except Exception:  # pragma: no cover - depends on Redis availability
        activity.logger.warning("event publish failed", exc_info=True)


@activity.defn(name="run_command_job")
def run_command_job(request: JobRequest) -> JobResult:
    inputs = request.inputs
    command = inputs.get("command", "")
    env = inputs.get("env")
    explicit_wd = inputs.get("working_dir")
    # Run in an ephemeral working dir (cleaned up after) unless one is pinned, with
    # CPU/memory/file-size limits applied to the child (docs 05 §4.4).
    workdir = explicit_wd or tempfile.mkdtemp(prefix="moiraflow-cmd-")
    try:
        completed = subprocess.run(
            command,
            shell=True,  # a `command` job runs a shell command by definition
            capture_output=True,
            text=True,
            cwd=workdir,
            env=env,
            preexec_fn=apply_limits,
        )
        if completed.returncode != 0:
            # Raising lets Temporal apply the job's RetryPolicy.
            raise RuntimeError(
                f"command exited {completed.returncode}: {completed.stderr.strip()[:500]}"
            )
        # Upload declared artifacts (relative paths resolve against the workdir).
        artifacts: list[dict[str, Any]] = []
        declared = inputs.get("artifacts") or []
        if declared:
            paths = [p if os.path.isabs(p) else os.path.join(workdir, p) for p in declared]
            prefix = f"{request.tenant_id or 'default'}/{request.job_id}/{uuid.uuid4().hex[:8]}"
            try:
                artifacts = upload_artifacts(paths, prefix)
            except Exception:  # pragma: no cover - best effort; depends on MinIO
                activity.logger.warning("artifact upload failed", exc_info=True)
        return JobResult(
            job_id=request.job_id, outputs=dict(request.outputs_spec), artifacts=artifacts
        )
    finally:
        if explicit_wd is None:
            shutil.rmtree(workdir, ignore_errors=True)


async def execute_rest(inputs: dict[str, Any], client: httpx.AsyncClient) -> int:
    """Perform the HTTP request and enforce `expect_status`. Returns the status code.

    Separated from the activity so it can be tested offline with httpx.MockTransport.
    """
    response = await client.request(
        inputs["method"],
        inputs["url"],
        headers=inputs.get("headers"),
        json=inputs.get("body"),
    )
    expected = inputs.get("expect_status")
    if expected and response.status_code not in expected:
        raise RuntimeError(
            f"rest {inputs['method']} {inputs['url']} -> {response.status_code}, "
            f"expected {expected}"
        )
    return response.status_code


@activity.defn(name="run_rest_job")
async def run_rest_job(request: JobRequest) -> JobResult:
    async with httpx.AsyncClient() as client:
        await execute_rest(request.inputs, client)
    return JobResult(job_id=request.job_id, outputs=dict(request.outputs_spec))


@activity.defn(name="run_sql_job")
def run_sql_job(request: JobRequest) -> JobResult:
    """Run a SQL statement against a connection. `connection` is a DSN or a
    `secret://<key>` resolved server-side; secret values are redacted from errors."""
    from sqlalchemy import create_engine, text

    inputs = request.inputs
    dsn = resolve_reference(str(inputs["connection"]), request.tenant_id)
    statement = str(inputs["statement"])
    params = inputs.get("params") or {}
    engine = create_engine(dsn)
    try:
        with engine.begin() as conn:
            conn.execute(text(statement), params)
    except Exception as exc:
        raise RuntimeError(f"sql job failed: {redact(str(exc))}") from None
    finally:
        engine.dispose()
    return JobResult(job_id=request.job_id, outputs=dict(request.outputs_spec))


# Activities registered on the server-side worker (and the local "agent" worker).
SERVER_ACTIVITIES: list[Callable[..., Any]] = [
    run_command_job,
    run_rest_job,
    run_sql_job,
    publish_event,
]
