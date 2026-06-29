"""Pydantic v2 models — the single source of truth for the workflow-as-code schema.

The published JSON Schema (catalog/workflow-schema) is generated from these models.
Structural rules live here (extra="forbid", patterns, enums); semantic rules
(DAG acyclicity, reference resolution) live in validator.py.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

JobType = Literal["command", "rest", "sql", "transform", "file_transfer"]
RunOn = Literal["server", "agent"]
TriggerType = Literal["cron", "manual", "webhook", "event"]
OnError = Literal["fail", "continue", "compensate"]
RetryStrategy = Literal["fixed", "exponential", "custom"]

_NAME_PATTERN = r"^[a-z0-9_-]+$"

_STRICT = ConfigDict(extra="forbid", populate_by_name=True)


class RetryPolicy(BaseModel):
    model_config = _STRICT
    strategy: RetryStrategy = "fixed"
    max_attempts: int = Field(default=1, ge=1, le=100)
    initial_interval: str | None = None
    interval: str | None = None


class Job(BaseModel):
    model_config = _STRICT
    id: str = Field(pattern=_NAME_PATTERN)
    type: JobType
    run_on: RunOn = "server"
    agent_selector: dict[str, str] | None = None
    needs: list[str] = Field(default_factory=list)
    with_: dict[str, Any] = Field(alias="with")
    timeout: str | None = None
    retry: RetryPolicy | None = None
    outputs: dict[str, str] = Field(default_factory=dict)
    condition: str | None = None


class Trigger(BaseModel):
    model_config = _STRICT
    type: TriggerType
    cron: str | None = None
    timezone: str | None = None


class Sla(BaseModel):
    model_config = _STRICT
    expected_duration: str | None = None
    deadline: str | None = None
    criticality: Literal["low", "medium", "high"] | None = None


class Notification(BaseModel):
    model_config = _STRICT
    on: Literal["failed", "success", "always"] = "failed"
    type: Literal["webhook"] = "webhook"
    url: str  # the webhook to POST the execution outcome to


class Spec(BaseModel):
    model_config = _STRICT
    trigger: Trigger
    context: dict[str, Any] = Field(default_factory=dict)
    on_error: OnError = "fail"
    sla: Sla | None = None
    notifications: list[Notification] = Field(default_factory=list)
    jobs: list[Job] = Field(min_length=1)


class Metadata(BaseModel):
    model_config = _STRICT
    name: str = Field(pattern=_NAME_PATTERN)
    description: str | None = None
    labels: dict[str, str] = Field(default_factory=dict)


class WorkflowDefinition(BaseModel):
    model_config = _STRICT
    api_version: Literal["moiraflow/v1"] = Field(alias="apiVersion")
    kind: Literal["Workflow"]
    metadata: Metadata
    spec: Spec
