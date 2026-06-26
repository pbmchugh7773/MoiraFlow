"""The interpreter's orchestration core — pure and deterministic (ADR-0011).

`run_dag` resolves the DAG, renders each job's inputs with the deterministic
template engine, runs every ready job (fan-out in parallel), and propagates each
job's declared `outputs` to downstream jobs via the `jobs.<id>.outputs.*` scope.

It performs **no I/O itself**: the actual job execution is an injected coroutine
`run_job`. In the Temporal workflow that callable dispatches an Activity; in tests
it is a fake. This keeps all orchestration logic replay-safe and unit-testable
without a Temporal server.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from .scheduling import ready_jobs
from .templating import RenderScope, render_job_inputs


@dataclass
class JobRequest:
    job_id: str
    type: str
    inputs: dict[str, Any]
    outputs_spec: dict[str, str] = field(default_factory=dict)
    run_on: str = "server"
    agent_selector: dict[str, str] | None = None
    timeout: str | None = None
    retry: dict[str, Any] | None = None


@dataclass
class JobResult:
    job_id: str
    outputs: dict[str, Any] = field(default_factory=dict)
    status: str = "success"


RunJob = Callable[[JobRequest], Awaitable[JobResult]]

# A lifecycle event: {"type", "job_id" | None, "payload"}. Emitting is an injected
# coroutine so the side effect (a Temporal activity that publishes to Redis) stays
# out of the deterministic workflow body (ADR-0011); tests pass a recording fake.
Event = dict[str, Any]
Emit = Callable[[Event], Awaitable[None]]


async def _noop_emit(_: Event) -> None:
    return None


async def run_dag(
    definition: dict[str, Any],
    input_context: dict[str, Any],
    run_job: RunJob,
    emit: Emit | None = None,
) -> dict[str, Any]:
    """Execute a validated workflow definition and return the final scope.

    Returns ``{"context": <initial, read-only>, "jobs": {id: {"outputs": {...}}}}``.
    The initial context is never mutated (ADR-0013); downstream jobs read upstream
    results only through declared outputs. Lifecycle events are emitted via `emit`.
    """
    emit = emit or _noop_emit
    jobs: list[dict[str, Any]] = definition["spec"]["jobs"]
    outputs_by_job: dict[str, dict[str, Any]] = {}
    completed: set[str] = set()

    await emit({"type": "execution_started", "job_id": None, "payload": {"job_count": len(jobs)}})
    try:
        while len(completed) < len(jobs):
            scope = RenderScope(context=input_context, outputs=outputs_by_job)
            batch = ready_jobs(jobs, completed=completed, running=set())
            if not batch:  # pragma: no cover - a validated DAG always makes progress
                raise RuntimeError("no runnable jobs but workflow is incomplete (cyclic?)")

            results = await asyncio.gather(*(_execute(job, scope, run_job, emit) for job in batch))
            for result in results:
                outputs_by_job[result.job_id] = result.outputs
                completed.add(result.job_id)
    except Exception as exc:
        await emit({"type": "execution_failed", "job_id": None, "payload": {"error": str(exc)}})
        raise

    await emit({"type": "execution_finished", "job_id": None, "payload": {"status": "success"}})
    return {
        "context": input_context,
        "jobs": {job_id: {"outputs": outs} for job_id, outs in outputs_by_job.items()},
    }


async def _execute(
    job: dict[str, Any], scope: RenderScope, run_job: RunJob, emit: Emit
) -> JobResult:
    rendered = render_job_inputs(job.get("with", {}), scope)
    request = JobRequest(
        job_id=job["id"],
        type=job["type"],
        inputs=rendered,
        outputs_spec=job.get("outputs", {}),
        run_on=job.get("run_on", "server"),
        agent_selector=job.get("agent_selector"),
        timeout=job.get("timeout"),
        retry=job.get("retry"),
    )
    await emit({"type": "job_started", "job_id": request.job_id, "payload": {"type": request.type}})
    try:
        result = await run_job(request)
    except Exception as exc:
        await emit({"type": "job_failed", "job_id": request.job_id, "payload": {"error": str(exc)}})
        raise
    await emit(
        {"type": "job_succeeded", "job_id": request.job_id, "payload": {"outputs": result.outputs}}
    )
    return result
