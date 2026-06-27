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
    csr: str | None = None  # PEM CSR; when present the CA issues a signed cert


class RegisterResponse(BaseModel):
    agent_id: uuid.UUID
    task_queue: str
    status: str
    certificate: str | None = None  # signed agent cert (PEM)
    ca_certificate: str | None = None  # CA cert to trust (PEM)
    fingerprint: str | None = None


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
