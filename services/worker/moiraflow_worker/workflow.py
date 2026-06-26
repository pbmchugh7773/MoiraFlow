"""The generic Temporal Workflow that interprets any MoiraFlow definition.

There is ONE interpreter workflow for ALL definitions (not one per workflow). It
is a thin, deterministic adapter: it delegates orchestration to the pure
`run_dag` and only adds the Temporal-specific concern of dispatching each job as
an Activity on the correct task queue (server vs agent — ADR-0012/0017).
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, cast

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from .durations import parse_duration
    from .interpreter import JobRequest, JobResult, run_dag
    from .policies import build_retry_policy

# Default per-activity ceiling; per-job `timeout` overrides this in a later slice.
_DEFAULT_ACTIVITY_TIMEOUT = timedelta(minutes=5)
# Event publishing is best-effort: short timeout, no retry, never blocks progress.
_EVENT_TIMEOUT = timedelta(seconds=10)


@workflow.defn(name="FlowInterpreter")
class FlowInterpreter:
    @workflow.run
    async def run(
        self,
        definition: dict[str, Any],
        input_context: dict[str, Any],
        meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        workflow_id = workflow.info().workflow_id

        async def run_job(request: JobRequest) -> JobResult:
            task_queue = None  # None => the workflow's own (server) task queue
            if request.run_on == "agent":
                # Agent selector resolution is the agent slice; until then a job
                # explicitly routed to an agent must name its queue out-of-band.
                task_queue = _agent_task_queue(request)
            result = await workflow.execute_activity(
                f"run_{request.type}_job",
                request,
                task_queue=task_queue,
                start_to_close_timeout=parse_duration(request.timeout) or _DEFAULT_ACTIVITY_TIMEOUT,
                retry_policy=build_retry_policy(request.retry),
                result_type=JobResult,
            )
            return cast(JobResult, result)

        async def emit(event: dict[str, Any]) -> None:
            # Lightweight local activity; correlate to the execution via workflow id.
            await workflow.execute_local_activity(
                "publish_event",
                {**event, "temporal_workflow_id": workflow_id},
                start_to_close_timeout=_EVENT_TIMEOUT,
            )

        return await run_dag(definition, input_context, run_job, emit=emit, meta=meta)


def _agent_task_queue(request: JobRequest) -> str:
    selector = request.agent_selector or {}
    agent_id = selector.get("agent_id")
    if not agent_id:
        raise ValueError(f"job '{request.job_id}' is run_on=agent but no agent could be resolved")
    return f"agent-{agent_id}"
