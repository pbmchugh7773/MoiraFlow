"""Server-side job activities. All I/O lives here (never in workflow code).

MVP implements `command`; `rest` and `sql` arrive in the next slice. Activities
run with retries/timeouts supplied by the workflow (mapped from each job's retry
policy). A `command` job intentionally runs a shell command — isolation
(unprivileged user, resource limits, redaction) is handled per docs 05 §4.4 and
is orthogonal to this execution contract.
"""

from __future__ import annotations

import collections
import json
import os
import shutil
import subprocess
import tempfile
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

import httpx
from temporalio import activity
from temporalio.exceptions import ApplicationError

from .events import get_redis, publish_to_redis
from .interpreter import JobRequest, JobResult
from .isolation import apply_limits
from .file_transfer import parse_credentials, transfer
from .secrets import redact, resolve_reference
from .storage import upload_artifacts
from .transform import extract_path, parse_source

# Misconfigurations that can never succeed by retrying — fail fast on the first
# attempt instead of burning the retry budget and delaying the run's failure.
_PERMANENT_URL_ERRORS = (httpx.UnsupportedProtocol, httpx.InvalidURL)


@activity.defn(name="publish_event")
def publish_event(event: dict[str, Any]) -> None:
    """Best-effort: publish a lifecycle event to Redis; never fail the workflow."""
    try:
        publish_to_redis(get_redis(), event)
    except Exception:  # pragma: no cover - depends on Redis availability
        activity.logger.warning("event publish failed", exc_info=True)


def _attempt() -> int:
    """Temporal attempt number for the running activity (1 = first try). Returns 1
    outside an activity context (e.g. direct unit-test calls)."""
    try:
        return activity.info().attempt
    except RuntimeError:
        return 1


def _workflow_id() -> str | None:
    """The running activity's Temporal workflow id (None outside an activity, e.g.
    direct unit-test calls) — used to route streamed log lines to the execution."""
    try:
        return activity.info().workflow_id
    except RuntimeError:
        return None


# Cap streamed lines so a chatty command can't flood Redis/Postgres with events.
_MAX_LOG_LINES = 2000


def _emit_log(job_id: str, workflow_id: str | None, line: str) -> None:
    """Publish one redacted log line to Redis (best-effort; never fails the job)."""
    if not workflow_id:
        return
    try:
        publish_to_redis(
            get_redis(),
            {
                "type": "job_log",
                "job_id": job_id,
                "temporal_workflow_id": workflow_id,
                # Stamp when the line was produced (activities run outside the
                # deterministic workflow sandbox, so wall-clock time is fine here).
                "payload": {"line": line, "ts": datetime.now(timezone.utc).isoformat()},
            },
        )
    except Exception:  # pragma: no cover - depends on Redis availability
        activity.logger.warning("log publish failed", exc_info=True)


def _stream_command(
    command: str,
    env: dict[str, str] | None,
    workdir: str | None,
    emit_line: Callable[[str], None],
) -> tuple[int, list[str]]:
    """Run a shell command, streaming each redacted output line to `emit_line` as it
    is produced. stderr is merged into stdout so ordering is preserved and no pipe
    deadlocks. Returns ``(returncode, tail)`` where tail is the last few lines (used
    to build the error message). Resource limits are applied to the child."""
    proc = subprocess.Popen(
        command,
        shell=True,  # a `command` job runs a shell command by definition
        cwd=workdir,
        env=env,
        preexec_fn=apply_limits,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    tail: collections.deque[str] = collections.deque(maxlen=20)
    emitted = 0
    assert proc.stdout is not None
    for raw in proc.stdout:
        line = redact(raw.rstrip("\n"))
        tail.append(line)
        if emitted < _MAX_LOG_LINES:
            emit_line(line)
            emitted += 1
            if emitted == _MAX_LOG_LINES:
                emit_line(f"... [log truncated at {_MAX_LOG_LINES} lines]")
    return proc.wait(), list(tail)


@activity.defn(name="run_command_job")
def run_command_job(request: JobRequest) -> JobResult:
    inputs = request.inputs
    command = inputs.get("command", "")
    env = inputs.get("env")
    explicit_wd = inputs.get("working_dir")
    # Run in an ephemeral working dir (cleaned up after) unless one is pinned, with
    # CPU/memory/file-size limits applied to the child (docs 05 §4.4).
    workdir = explicit_wd or tempfile.mkdtemp(prefix="moiraflow-cmd-")
    workflow_id = _workflow_id()
    try:
        returncode, tail = _stream_command(
            command, env, workdir, lambda line: _emit_log(request.job_id, workflow_id, line)
        )
        if returncode != 0:
            # Raising lets Temporal apply the job's RetryPolicy.
            raise RuntimeError(f"command exited {returncode}: {' | '.join(tail)[:500]}")
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
            job_id=request.job_id,
            outputs=dict(request.outputs_spec),
            artifacts=artifacts,
            attempt=_attempt(),
        )
    finally:
        if explicit_wd is None:
            shutil.rmtree(workdir, ignore_errors=True)


def _parse_response_body(response: httpx.Response) -> Any:
    """Decode the response body: parsed JSON when the response is JSON, else text."""
    if "json" in response.headers.get("content-type", "").lower():
        try:
            return response.json()
        except ValueError:
            return response.text
    return response.text


async def execute_rest(inputs: dict[str, Any], client: httpx.AsyncClient) -> tuple[int, Any]:
    """Perform the HTTP request and enforce `expect_status`. Returns
    ``(status_code, body)`` where body is parsed JSON (or text).

    Separated from the activity so it can be tested offline with httpx.MockTransport.
    """
    try:
        response = await client.request(
            inputs["method"],
            inputs["url"],
            headers=inputs.get("headers"),
            json=inputs.get("body"),
        )
    except _PERMANENT_URL_ERRORS as exc:
        # A malformed URL is a config error — non-retryable so it fails immediately.
        raise ApplicationError(
            f"invalid url for {inputs.get('method')} {redact(str(inputs.get('url')))}: {exc}",
            type="InvalidRequest",
            non_retryable=True,
        ) from exc
    expected = inputs.get("expect_status")
    if expected and response.status_code not in expected:
        raise RuntimeError(
            f"rest {inputs['method']} {inputs['url']} -> {response.status_code}, "
            f"expected {expected}"
        )
    return response.status_code, _parse_response_body(response)


@activity.defn(name="run_rest_job")
async def run_rest_job(request: JobRequest) -> JobResult:
    async with httpx.AsyncClient() as client:
        status, body = await execute_rest(request.inputs, client)
    # Expose the response so downstream jobs can read jobs.<id>.outputs.status/.body,
    # plus echo a redacted log line so the response is visible in the UI.
    outputs: dict[str, Any] = {**dict(request.outputs_spec), "status": status, "body": body}
    summary = json.dumps(body, ensure_ascii=False) if not isinstance(body, str) else body
    _emit_log(request.job_id, _workflow_id(), redact(f"→ {status} {summary[:1000]}"))
    return JobResult(job_id=request.job_id, outputs=outputs, attempt=_attempt())


@activity.defn(name="run_transform_job")
async def run_transform_job(request: JobRequest) -> JobResult:
    """Parse a file/payload (csv/json/xml) and extract values into outputs.

    Reads `with.content` (inline, often templated from a prior job) or downloads
    `with.url`, parses it per `with.format`, then evaluates each declared `output`
    as a path expression against the parsed data (see `transform.py`).
    """
    inputs = request.inputs
    fmt = str(inputs.get("format", "json"))
    raw: Any = inputs.get("content")
    url = inputs.get("url")
    if url:
        async with httpx.AsyncClient() as client:
            response = await client.get(str(url))
            response.raise_for_status()
            raw = response.text
    try:
        data = parse_source(raw, fmt)
    except Exception as exc:  # malformed input can't succeed on retry
        raise ApplicationError(
            f"transform: cannot parse {fmt}: {exc}", type="ParseError", non_retryable=True
        ) from None

    outputs: dict[str, Any] = {}
    for name, path in request.outputs_spec.items():
        try:
            outputs[name] = extract_path(data, str(path))
        except Exception as exc:
            raise ApplicationError(
                f"transform: path {path!r} for output {name!r} failed: {exc}",
                type="ExtractError",
                non_retryable=True,
            ) from None
    return JobResult(job_id=request.job_id, outputs=outputs, attempt=_attempt())


@activity.defn(name="run_file_transfer_job")
def run_file_transfer_job(request: JobRequest) -> JobResult:
    """Move a file between a source and destination (http/s3/artifact/sftp).

    SFTP credentials come from `secret://` (`with.credentials`, or per-side
    `with.source_credentials` / `with.destination_credentials`). A destination of
    `artifact://...` becomes a downloadable execution artifact.
    """
    inputs = request.inputs
    shared = inputs.get("credentials")
    src_ref = inputs.get("source_credentials", shared)
    dst_ref = inputs.get("destination_credentials", shared)
    src_creds = (
        parse_credentials(resolve_reference(str(src_ref), request.tenant_id)) if src_ref else {}
    )
    dst_creds = (
        parse_credentials(resolve_reference(str(dst_ref), request.tenant_id)) if dst_ref else {}
    )
    try:
        result = transfer(
            str(inputs["source"]),
            str(inputs["destination"]),
            src_creds=src_creds,
            dst_creds=dst_creds,
            tenant_id=request.tenant_id,
            job_id=request.job_id,
        )
    except ValueError as exc:  # bad scheme / oversize — config error, won't retry better
        raise ApplicationError(
            f"file_transfer: {exc}", type="TransferConfig", non_retryable=True
        ) from None

    ref = result["ref"]
    outputs: dict[str, Any] = {**dict(request.outputs_spec), "size": result["size"]}
    if ref:
        outputs["artifact_key"] = ref["object_key"]
    return JobResult(
        job_id=request.job_id,
        outputs=outputs,
        artifacts=[ref] if ref else [],
        attempt=_attempt(),
    )


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
    return JobResult(job_id=request.job_id, outputs=dict(request.outputs_spec), attempt=_attempt())


# Activities registered on the server-side worker (and the local "agent" worker).
SERVER_ACTIVITIES: list[Callable[..., Any]] = [
    run_command_job,
    run_rest_job,
    run_sql_job,
    run_transform_job,
    run_file_transfer_job,
    publish_event,
]
