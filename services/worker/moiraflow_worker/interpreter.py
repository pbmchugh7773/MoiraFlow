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
from .templating import RenderScope, evaluate_condition, render_job_inputs


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
    tenant_id: str | None = None  # set by the workflow from meta; for secret:// scoping


@dataclass
class JobResult:
    job_id: str
    outputs: dict[str, Any] = field(default_factory=dict)
    status: str = "success"
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    attempt: int = 1  # Temporal attempt the job succeeded on (1 = first try)


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
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute a validated workflow definition and return the final scope.

    Returns ``{"context": <initial, read-only>, "jobs": {id: {"outputs": {...}}}}``.
    The initial context is never mutated (ADR-0013); downstream jobs read upstream
    results only through declared outputs. Lifecycle events are emitted via `emit`;
    `meta` (tenant/workflow/version ids) rides on `execution_started` so the API can
    auto-register runs that started outside `POST /executions` (e.g. cron schedules).
    """
    emit = emit or _noop_emit
    jobs: list[dict[str, Any]] = definition["spec"]["jobs"]
    # `fail` (default): a failed job aborts the whole run. `continue`: tolerate it —
    # keep running the reachable jobs; dependents of a failed job cascade-skip. The
    # run still completes (the failed jobs are recorded per-job).
    on_error = definition["spec"].get("on_error", "fail")
    # Effective context = workflow-declared defaults overlaid with launch inputs
    # (override wins). The merged map is read-only for the whole run (ADR-0013).
    context = {**definition["spec"].get("context", {}), **input_context}
    outputs_by_job: dict[str, dict[str, Any]] = {}
    completed: set[str] = set()
    skipped: set[str] = set()
    failed: set[str] = set()

    await emit(
        {
            "type": "execution_started",
            "job_id": None,
            "payload": {"job_count": len(jobs), "meta": meta or {}},
        }
    )
    try:
        while len(completed) + len(skipped) + len(failed) < len(jobs):
            done = completed | skipped | failed
            scope = RenderScope(context=context, outputs=outputs_by_job)
            batch = ready_jobs(jobs, completed=done, running=set())
            if not batch:  # pragma: no cover - a validated DAG always makes progress
                raise RuntimeError("no runnable jobs but workflow is incomplete (cyclic?)")

            to_run = []
            for job in batch:
                reason = _skip_reason(job, skipped, failed, scope)
                if reason is not None:
                    skipped.add(job["id"])
                    await emit(
                        {"type": "job_skipped", "job_id": job["id"], "payload": {"reason": reason}}
                    )
                else:
                    to_run.append(job)

            # return_exceptions so one failure doesn't cancel its sibling branch.
            results = await asyncio.gather(
                *(_execute(job, scope, run_job, emit) for job in to_run),
                return_exceptions=True,
            )
            for job, result in zip(to_run, results):
                if isinstance(result, BaseException):
                    if on_error != "continue":
                        raise result  # `fail`: abort the run
                    failed.add(job["id"])  # `continue`: tolerate; dependents skip
                else:
                    outputs_by_job[result.job_id] = result.outputs
                    completed.add(result.job_id)
    except Exception as exc:
        await emit({"type": "execution_failed", "job_id": None, "payload": {"error": str(exc)}})
        raise

    await emit(
        {
            "type": "execution_finished",
            "job_id": None,
            "payload": {"status": "success", "failed_jobs": sorted(failed)},
        }
    )
    return {
        "context": context,
        "jobs": {job_id: {"outputs": outs} for job_id, outs in outputs_by_job.items()},
    }


def _skip_reason(
    job: dict[str, Any], skipped: set[str], failed: set[str], scope: RenderScope
) -> str | None:
    """Why this ready job should be skipped, or None to run it. A job is skipped when
    an upstream dependency failed (under on_error: continue) or was skipped (cascade),
    or its `condition` is false."""
    needs = job.get("needs", [])
    if any(dep in failed for dep in needs):
        return "upstream_failed"
    if any(dep in skipped for dep in needs):
        return "upstream_skipped"
    condition = job.get("condition")
    if condition and not evaluate_condition(condition, scope):
        return "condition_false"
    return None


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
        {
            "type": "job_succeeded",
            "job_id": request.job_id,
            "payload": {
                "outputs": result.outputs,
                "artifacts": result.artifacts,
                "attempt": result.attempt,
            },
        }
    )
    return result
