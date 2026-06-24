"""End-to-end test against a real (local) Temporal dev server.

Slower than the pure interpreter tests; it exists to prove the Temporal wiring
(workflow + activity dispatch + data conversion) actually works. Skips cleanly if
the dev server binary cannot be started (e.g. offline CI).
"""

import asyncio
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest

from flowops_worker.runtime import build_worker

temporalio_testing = pytest.importorskip("temporalio.testing")
WorkflowEnvironment = temporalio_testing.WorkflowEnvironment

TASK_QUEUE = "flowops-itest"

DEFINITION = {
    "apiVersion": "flowops/v1",
    "kind": "Workflow",
    "metadata": {"name": "itest"},
    "spec": {
        "trigger": {"type": "manual"},
        "context": {"greeting": "hello"},
        "jobs": [
            {
                "id": "first",
                "type": "command",
                "with": {"command": "echo {{ context.greeting }}"},
                "outputs": {"done": "yes"},
            },
            {
                "id": "second",
                "type": "command",
                "needs": ["first"],
                "with": {"command": "echo {{ jobs.first.outputs.done }}"},
                "outputs": {"final": "ok"},
            },
        ],
    },
}


async def _run_once():
    try:
        env = await WorkflowEnvironment.start_local()
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"local Temporal server unavailable: {exc}")
    async with env:
        with ThreadPoolExecutor(max_workers=4) as pool:
            worker = build_worker(env.client, TASK_QUEUE, activity_executor=pool)
            async with worker:
                return await env.client.execute_workflow(
                    "FlowInterpreter",
                    args=[DEFINITION, {"greeting": "hello"}],
                    id=f"itest-{uuid.uuid4()}",
                    task_queue=TASK_QUEUE,
                )


def test_two_job_dag_executes_end_to_end():
    result = asyncio.run(_run_once())
    assert result["context"] == {"greeting": "hello"}
    assert result["jobs"]["first"]["outputs"] == {"done": "yes"}
    assert result["jobs"]["second"]["outputs"] == {"final": "ok"}
