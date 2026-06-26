"""Request/response models for workflow CRUD + versioning."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class CreateWorkflowRequest(BaseModel):
    content: str
    format: Literal["yaml", "json"] = "yaml"


class WorkflowVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    version: int
    definition_hash: str
    source_format: str
    created_at: datetime


class WorkflowVersionDetailOut(WorkflowVersionOut):
    definition: dict[str, Any]


class WorkflowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    description: str | None
    trigger_type: str
    trigger_config: dict[str, Any]
    is_enabled: bool
    active_version_id: uuid.UUID | None
    created_at: datetime
