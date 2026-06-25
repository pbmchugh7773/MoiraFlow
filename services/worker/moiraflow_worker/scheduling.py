"""Pure DAG scheduling for the interpreter.

Operates on the already-validated workflow definition as plain dicts (Temporal
hands the workflow JSON, not Pydantic objects). Pure and deterministic so it is
safe to call from workflow code (ADR-0011). Acyclicity / reference integrity were
already guaranteed by the API's validation before the execution was started.
"""

from __future__ import annotations

from typing import Any


def ready_jobs(
    jobs: list[dict[str, Any]],
    completed: set[str],
    running: set[str],
) -> list[dict[str, Any]]:
    """Return the jobs whose dependencies are all satisfied and are not yet
    completed or in flight, preserving definition order (deterministic)."""
    ready: list[dict[str, Any]] = []
    for job in jobs:
        job_id = job["id"]
        if job_id in completed or job_id in running:
            continue
        if all(dep in completed for dep in job.get("needs", [])):
            ready.append(job)
    return ready
