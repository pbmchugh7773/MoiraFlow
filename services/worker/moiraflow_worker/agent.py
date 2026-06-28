"""Agent entrypoint: an activities-only worker on a dedicated task queue.

Same runtime as the server worker but registers only the `command` activity. By
default it polls `agent-local` (ADR-0017, local-worker-first); a remote agent sets
`MOIRAFLOW_AGENT_QUEUE` to the `task_queue` returned by `POST /agents/register`
(`agent-<id>`) and `TEMPORAL_HOST` to the central Temporal, with mTLS via the
`MOIRAFLOW_TLS_*` vars. It never holds DB/secret access.
"""

from __future__ import annotations

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor

from .main import _connect_with_retry
from .runtime import AGENT_TASK_QUEUE, build_agent_worker


async def main() -> None:
    address = os.getenv("TEMPORAL_HOST", "localhost:7233")
    namespace = os.getenv("TEMPORAL_NAMESPACE", "default")
    task_queue = os.getenv("MOIRAFLOW_AGENT_QUEUE", AGENT_TASK_QUEUE)
    client = await _connect_with_retry(address, namespace)
    with ThreadPoolExecutor(max_workers=8) as pool:
        worker = build_agent_worker(client, task_queue, activity_executor=pool)
        print(f"agent connected to {address}; polling task queue '{task_queue}'", flush=True)
        await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
