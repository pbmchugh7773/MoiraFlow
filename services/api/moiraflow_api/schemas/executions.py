"""Request/response models for executions."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CreateExecutionRequest(BaseModel):
    workflow_id: uuid.UUID
    version: int | None = None
    input_context: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = None


class ExecutionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    workflow_id: uuid.UUID
    workflow_version_id: uuid.UUID
    temporal_workflow_id: str
    temporal_run_id: str | None
    status: str
    input_context: dict[str, Any]
    created_at: datetime
