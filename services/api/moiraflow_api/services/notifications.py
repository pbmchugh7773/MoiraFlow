"""Fire webhook notifications when an execution reaches a terminal state.

A workflow declares targets in `spec.notifications`; when a run finishes (success or
failure) the matching ones get a POST with the outcome. Delivery is best-effort — a
dead webhook never affects the run. `_default_sender` is module-level so tests can
monkeypatch it.
"""

from __future__ import annotations

from typing import Any, Callable

from ..db import models

WebhookSender = Callable[[str, dict[str, Any]], None]


def _default_sender(url: str, payload: dict[str, Any]) -> None:  # pragma: no cover - network
    import httpx

    httpx.post(url, json=payload, timeout=5.0)


def _payload(execution: models.Execution, status: str, failed_jobs: list[str]) -> dict[str, Any]:
    return {
        "execution_id": str(execution.id),
        "workflow_id": str(execution.workflow_id),
        "workflow_name": execution.workflow_name,
        "status": status,
        "failed_jobs": failed_jobs,
        "trigger_source": execution.trigger_source,
    }


def dispatch(
    execution: models.Execution,
    definition: dict[str, Any],
    status: str,
    *,
    failed_jobs: list[str] | None = None,
    sender: WebhookSender | None = None,
) -> int:
    """POST the outcome to each notification rule that matches `status`. Returns how
    many were sent. Matching: `on` is one of failed/success/always."""
    rules = (definition.get("spec") or {}).get("notifications") or []
    payload = _payload(execution, status, failed_jobs or [])
    send = sender or _default_sender
    sent = 0
    for rule in rules:
        on = rule.get("on", "failed")
        if on != "always" and on != status:
            continue
        if rule.get("type", "webhook") != "webhook":
            continue
        try:
            send(rule["url"], payload)
            sent += 1
        except Exception:  # best-effort — a failing webhook must not break the run
            pass
    return sent
