"""Server-side job activities. All I/O lives here (never in workflow code).

MVP implements `command`; `rest` and `sql` arrive in the next slice. Activities
run with retries/timeouts supplied by the workflow (mapped from each job's retry
policy). A `command` job intentionally runs a shell command — isolation
(unprivileged user, resource limits, redaction) is handled per docs 05 §4.4 and
is orthogonal to this execution contract.
"""

from __future__ import annotations

import subprocess
from typing import Any

import httpx
from temporalio import activity

from .interpreter import JobRequest, JobResult


@activity.defn(name="run_command_job")
def run_command_job(request: JobRequest) -> JobResult:
    command = request.inputs.get("command", "")
    env = request.inputs.get("env")
    working_dir = request.inputs.get("working_dir")
    completed = subprocess.run(
        command,
        shell=True,  # a `command` job runs a shell command by definition
        capture_output=True,
        text=True,
        cwd=working_dir,
        env=env,
    )
    if completed.returncode != 0:
        # Raising lets Temporal apply the job's RetryPolicy.
        raise RuntimeError(
            f"command exited {completed.returncode}: {completed.stderr.strip()[:500]}"
        )
    # MVP: a command job exposes its declared outputs verbatim. Extracting values
    # from stdout is a later enhancement.
    return JobResult(job_id=request.job_id, outputs=dict(request.outputs_spec))


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


# Activities registered on the server-side worker (and the local "agent" worker).
# `sql` arrives after the secrets+DB slices (its `connection: secret://...` depends
# on secret resolution, which is not built yet).
SERVER_ACTIVITIES = [run_command_job, run_rest_job]
