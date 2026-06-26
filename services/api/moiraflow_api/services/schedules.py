"""Cron triggers as Temporal Schedules (ADR-0015).

A `cron` workflow that is enabled gets a Temporal Schedule that periodically starts
the interpreter with the active version's definition. The Schedule is the single
source of truth for the recurring trigger; the API reconciles it on create /
activate / enable / disable. Behind a protocol so it is testable without Temporal.
"""

from __future__ import annotations

import uuid
from typing import Any, Protocol


class ScheduleManager(Protocol):
    def upsert(
        self,
        *,
        schedule_id: str,
        cron: str,
        timezone: str | None,
        definition: dict[str, Any],
        input_context: dict[str, Any],
        task_queue: str,
    ) -> None: ...

    def pause(self, schedule_id: str) -> None: ...

    def delete(self, schedule_id: str) -> None: ...


def schedule_id_for(workflow_id: uuid.UUID) -> str:
    return f"moiraflow-wf-{workflow_id}"
