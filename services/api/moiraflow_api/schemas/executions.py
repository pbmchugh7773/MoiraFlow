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
    trigger_source: str
    input_context: dict[str, Any]
    created_at: datetime


class ExecutionEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    event_type: str
    payload: dict[str, Any]
    job_execution_id: uuid.UUID | None
    created_at: datetime


class ArtifactOut(BaseModel):
    id: uuid.UUID
    name: str
    size_bytes: int
    content_type: str | None
    download_url: str
    created_at: datetime


class JobExecutionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    job_id: str
    job_type: str
    attempt: int
    status: str
    output: dict[str, Any] | None
    error: dict[str, Any] | None
    started_at: datetime | None
    finished_at: datetime | None
