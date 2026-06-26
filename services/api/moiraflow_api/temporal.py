"""Real Temporal-backed WorkflowStarter (used in production; tests inject a fake).

Kept behind the WorkflowStarter protocol and imported lazily by the dependency so
the API package and its tests do not require a Temporal connection. The
deterministic id + REJECT_DUPLICATE reuse policy is the idempotency guarantee
from ADR-0014, complementing the executions-row projection.
"""

from __future__ import annotations

import asyncio
from typing import Any

from temporalio.client import (
    Client,
    Schedule,
    ScheduleActionStartWorkflow,
    ScheduleSpec,
    ScheduleUpdate,
    ScheduleUpdateInput,
)
from temporalio.common import WorkflowIDReusePolicy

INTERPRETER_WORKFLOW = "FlowInterpreter"


class TemporalWorkflowStarter:
    def __init__(self, address: str, namespace: str = "default") -> None:
        self._address = address
        self._namespace = namespace

    def start(
        self,
        *,
        temporal_workflow_id: str,
        definition: dict[str, Any],
        input_context: dict[str, Any],
        task_queue: str,
        meta: dict[str, str],
    ) -> str:
        return asyncio.run(
            self._start(temporal_workflow_id, definition, input_context, task_queue, meta)
        )

    async def _start(
        self,
        temporal_workflow_id: str,
        definition: dict[str, Any],
        input_context: dict[str, Any],
        task_queue: str,
        meta: dict[str, str],
    ) -> str:
        client = await Client.connect(self._address, namespace=self._namespace)
        handle = await client.start_workflow(
            INTERPRETER_WORKFLOW,
            args=[definition, input_context, meta],
            id=temporal_workflow_id,
            task_queue=task_queue,
            id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
        )
        return handle.first_execution_run_id or ""


class TemporalScheduleManager:
    """Real Temporal Schedule lifecycle for cron triggers (ADR-0015)."""

    def __init__(self, address: str, namespace: str = "default") -> None:
        self._address = address
        self._namespace = namespace

    def upsert(
        self,
        *,
        schedule_id: str,
        cron: str,
        timezone: str | None,
        definition: dict[str, Any],
        input_context: dict[str, Any],
        task_queue: str,
        meta: dict[str, str],
    ) -> None:
        asyncio.run(
            self._upsert(schedule_id, cron, timezone, definition, input_context, task_queue, meta)
        )

    def pause(self, schedule_id: str) -> None:
        asyncio.run(self._act(schedule_id, "pause"))

    def delete(self, schedule_id: str) -> None:
        asyncio.run(self._act(schedule_id, "delete"))

    async def _upsert(
        self,
        schedule_id: str,
        cron: str,
        timezone: str | None,
        definition: dict[str, Any],
        input_context: dict[str, Any],
        task_queue: str,
        meta: dict[str, str],
    ) -> None:
        client = await Client.connect(self._address, namespace=self._namespace)
        schedule = Schedule(
            action=ScheduleActionStartWorkflow(
                INTERPRETER_WORKFLOW,
                args=[definition, input_context, meta],
                id=f"sched-{schedule_id}",
                task_queue=task_queue,
            ),
            spec=ScheduleSpec(cron_expressions=[cron], time_zone_name=timezone or "UTC"),
        )
        try:
            await client.create_schedule(schedule_id, schedule)
        except Exception:  # already exists -> update its definition/cron
            handle = client.get_schedule_handle(schedule_id)

            def _update(_: ScheduleUpdateInput) -> ScheduleUpdate:
                return ScheduleUpdate(schedule=schedule)

            await handle.update(_update)

    async def _act(self, schedule_id: str, action: str) -> None:
        client = await Client.connect(self._address, namespace=self._namespace)
        handle = client.get_schedule_handle(schedule_id)
        try:
            if action == "pause":
                await handle.pause()
            else:
                await handle.delete()
        except Exception:  # pragma: no cover - tolerant if the schedule is absent
            pass
