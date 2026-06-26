"""Agent entrypoint: an activities-only worker on a dedicated task queue.

Same runtime as the server worker but registers only the `command` activity and
polls `agent-local` (ADR-0017, local-worker-first). Validates the full
`run_on: agent` routing contract without remote enrollment/mTLS (that is Hito 5).
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
    client = await _connect_with_retry(address, namespace)
    with ThreadPoolExecutor(max_workers=8) as pool:
        worker = build_agent_worker(client, AGENT_TASK_QUEUE, activity_executor=pool)
        print(f"agent connected to {address}; polling task queue '{AGENT_TASK_QUEUE}'", flush=True)
        await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
