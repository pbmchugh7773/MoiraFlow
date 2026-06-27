"""Agent enrollment/registration request/response models."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class EnrollResponse(BaseModel):
    enrollment_token: str
    temporal_host: str
    expires_in: int


class RegisterAgentRequest(BaseModel):
    token: str
    name: str
    public_key: str


class RegisterResponse(BaseModel):
    agent_id: uuid.UUID
    task_queue: str
    status: str


class AgentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    status: str
    os: str
    task_queue: str
    fingerprint: str | None
    labels: dict[str, Any]
    last_heartbeat_at: datetime | None
    created_at: datetime
