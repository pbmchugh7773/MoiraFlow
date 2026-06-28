"""Real Temporal-backed WorkflowStarter + ScheduleManager (tests inject fakes).

Kept behind protocols and imported lazily by the dependencies so the API package
and its tests do not require a Temporal connection. The deterministic id +
REJECT_DUPLICATE reuse policy is the idempotency guarantee from ADR-0014,
complementing the executions-row projection.

Performance: all Temporal I/O runs on a single shared background event loop with a
cached client (`_TemporalRuntime`). The previous implementation reconnected on
every call (asyncio.run + Client.connect), which was the execution core's main
latency cost — paid on every launch, cancel, schedule sync, and (now) status
reconcile. One persistent gRPC connection is reused across all of them.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from temporalio.client import (
    Client,
    Schedule,
    ScheduleActionStartWorkflow,
    ScheduleSpec,
    ScheduleUpdate,
    ScheduleUpdateInput,
    WorkflowExecutionStatus,
)
from temporalio.common import WorkflowIDReusePolicy
from temporalio.exceptions import WorkflowAlreadyStartedError

from .encryption import data_converter

INTERPRETER_WORKFLOW = "FlowInterpreter"

T = TypeVar("T")

# Temporal's terminal statuses → MoiraFlow's projection status. RUNNING /
# CONTINUED_AS_NEW map to nothing (still in flight → leave the row unchanged).
_STATUS_MAP = {
    WorkflowExecutionStatus.COMPLETED: "success",
    WorkflowExecutionStatus.FAILED: "failed",
    WorkflowExecutionStatus.CANCELED: "cancelled",
    WorkflowExecutionStatus.TERMINATED: "cancelled",
    WorkflowExecutionStatus.TIMED_OUT: "failed",
}


class _TemporalRuntime:
    """A single background event loop + lazily-connected, cached Temporal client.

    API request handlers are synchronous (FastAPI threadpool); each `call()`
    submits a coroutine to the shared loop and blocks for the result. The client is
    connected once and reused, so we pay the gRPC handshake exactly once per process
    instead of once per request.
    """

    def __init__(self, address: str, namespace: str, master_key: str) -> None:
        self._address = address
        self._namespace = namespace
        self._master_key = master_key
        self._loop: asyncio.AbstractEventLoop | None = None
        self._client: Client | None = None
        self._lock = threading.Lock()

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is None:
            with self._lock:
                if self._loop is None:
                    loop = asyncio.new_event_loop()
                    threading.Thread(
                        target=loop.run_forever, daemon=True, name="temporal-loop"
                    ).start()
                    self._loop = loop
        return self._loop

    async def _ensure_client(self) -> Client:
        if self._client is None:
            self._client = await Client.connect(
                self._address,
                namespace=self._namespace,
                data_converter=data_converter(self._master_key),
            )
        return self._client

    def call(self, op: Callable[[Client], Awaitable[T]]) -> T:
        loop = self._ensure_loop()

        async def _run() -> T:
            client = await self._ensure_client()
            return await op(client)

        return asyncio.run_coroutine_threadsafe(_run(), loop).result()


_RUNTIMES: dict[tuple[str, str, str], _TemporalRuntime] = {}
_RUNTIMES_LOCK = threading.Lock()


def _runtime(address: str, namespace: str, master_key: str) -> _TemporalRuntime:
    """Process-wide singleton runtime per connection target, so the starter and the
    schedule manager share one client/loop."""
    key = (address, namespace, master_key)
    runtime = _RUNTIMES.get(key)
    if runtime is None:
        with _RUNTIMES_LOCK:
            runtime = _RUNTIMES.get(key)
            if runtime is None:
                runtime = _TemporalRuntime(*key)
                _RUNTIMES[key] = runtime
    return runtime


class TemporalWorkflowStarter:
    def __init__(self, address: str, namespace: str, master_key: str) -> None:
        self._rt = _runtime(address, namespace, master_key)

    def start(
        self,
        *,
        temporal_workflow_id: str,
        definition: dict[str, Any],
        input_context: dict[str, Any],
        task_queue: str,
        meta: dict[str, str],
    ) -> str:
        async def _op(client: Client) -> str:
            try:
                handle = await client.start_workflow(
                    INTERPRETER_WORKFLOW,
                    args=[definition, input_context, meta],
                    id=temporal_workflow_id,
                    task_queue=task_queue,
                    id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
                )
                return handle.first_execution_run_id or ""
            except WorkflowAlreadyStartedError:
                # The deterministic id already exists (ADR-0014): the executions
                # projection diverged from Temporal. Reconcile to the existing run
                # instead of failing, so the launch stays idempotent.
                description = await client.get_workflow_handle(temporal_workflow_id).describe()
                return description.run_id or ""

        return self._rt.call(_op)

    def describe_status(self, *, temporal_workflow_id: str) -> str | None:
        """Temporal's current status for the run, mapped to a projection status (or
        None if still running / unknown / absent)."""

        async def _op(client: Client) -> str | None:
            try:
                description = await client.get_workflow_handle(temporal_workflow_id).describe()
            except Exception:  # pragma: no cover - absent/unreachable -> leave row as-is
                return None
            if description.status is None:
                return None
            return _STATUS_MAP.get(description.status)

        return self._rt.call(_op)

    def cancel(self, *, temporal_workflow_id: str) -> None:
        async def _op(client: Client) -> None:
            try:
                await client.get_workflow_handle(temporal_workflow_id).cancel()
            except Exception:  # pragma: no cover - already finished/absent
                pass

        self._rt.call(_op)


class TemporalScheduleManager:
    """Real Temporal Schedule lifecycle for cron triggers (ADR-0015)."""

    def __init__(self, address: str, namespace: str, master_key: str) -> None:
        self._rt = _runtime(address, namespace, master_key)

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
        schedule = Schedule(
            action=ScheduleActionStartWorkflow(
                INTERPRETER_WORKFLOW,
                args=[definition, input_context, meta],
                id=f"sched-{schedule_id}",
                task_queue=task_queue,
            ),
            spec=ScheduleSpec(cron_expressions=[cron], time_zone_name=timezone or "UTC"),
        )

        async def _op(client: Client) -> None:
            try:
                await client.create_schedule(schedule_id, schedule)
            except Exception:  # already exists -> update its definition/cron
                handle = client.get_schedule_handle(schedule_id)

                def _update(_: ScheduleUpdateInput) -> ScheduleUpdate:
                    return ScheduleUpdate(schedule=schedule)

                await handle.update(_update)

        self._rt.call(_op)

    def pause(self, schedule_id: str) -> None:
        self._rt.call(lambda client: self._act(client, schedule_id, "pause"))

    def delete(self, schedule_id: str) -> None:
        self._rt.call(lambda client: self._act(client, schedule_id, "delete"))

    async def _act(self, client: Client, schedule_id: str, action: str) -> None:
        handle = client.get_schedule_handle(schedule_id)
        try:
            if action == "pause":
                await handle.pause()
            else:
                await handle.delete()
        except Exception:  # pragma: no cover - tolerant if the schedule is absent
            pass
