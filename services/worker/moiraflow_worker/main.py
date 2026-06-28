"""Worker entrypoint: connect to Temporal and run the interpreter + activities."""

from __future__ import annotations

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor

from temporalio.client import Client

from .encryption import data_converter
from .runtime import SERVER_TASK_QUEUE, build_worker
from .tls import build_tls_config


async def _connect_with_retry(
    address: str, namespace: str, attempts: int = 30, delay: float = 2.0
) -> Client:
    # mTLS when certs are configured (docs 05 §5); False = plaintext (dev default).
    tls = build_tls_config(os.environ) or False
    last_error: Exception | None = None
    for _ in range(attempts):
        try:
            return await Client.connect(
                address, namespace=namespace, data_converter=data_converter(), tls=tls
            )
        except Exception as exc:  # Temporal may not be ready yet at startup
            last_error = exc
            await asyncio.sleep(delay)
    raise RuntimeError(f"could not connect to Temporal at {address}: {last_error}")


async def main() -> None:
    address = os.getenv("TEMPORAL_HOST", "localhost:7233")
    namespace = os.getenv("TEMPORAL_NAMESPACE", "default")
    client = await _connect_with_retry(address, namespace)
    with ThreadPoolExecutor(max_workers=8) as pool:
        worker = build_worker(client, SERVER_TASK_QUEUE, activity_executor=pool)
        print(
            f"worker connected to {address}; polling task queue '{SERVER_TASK_QUEUE}'", flush=True
        )
        await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
