"""Real Temporal-backed WorkflowStarter (used in production; tests inject a fake).

Kept behind the WorkflowStarter protocol and imported lazily by the dependency so
the API package and its tests do not require a Temporal connection. The
deterministic id + REJECT_DUPLICATE reuse policy is the idempotency guarantee
from ADR-0014, complementing the executions-row projection.
"""

from __future__ import annotations

import asyncio
from typing import Any

from temporalio.client import Client
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
    ) -> str:
        return asyncio.run(self._start(temporal_workflow_id, definition, input_context, task_queue))

    async def _start(
        self,
        temporal_workflow_id: str,
        definition: dict[str, Any],
        input_context: dict[str, Any],
        task_queue: str,
    ) -> str:
        client = await Client.connect(self._address, namespace=self._namespace)
        handle = await client.start_workflow(
            INTERPRETER_WORKFLOW,
            args=[definition, input_context],
            id=temporal_workflow_id,
            task_queue=task_queue,
            id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
        )
        return handle.first_execution_run_id or ""
