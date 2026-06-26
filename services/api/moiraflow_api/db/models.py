"""ORM models for the docs-03 schema. Every business table carries `tenant_id`.

Immutable/audit tables (workflow_versions, executions, job_executions,
execution_events, artifacts, audit_log) intentionally have no `updated_at`.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, EmailType, IPType, JSONType, TimestampMixin, uuid_pk


def _created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Tenant(Base, TimestampMixin):
    __tablename__ = "tenants"
    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(100), unique=True)
    status: Mapped[str] = mapped_column(String(20), default="active")


class User(Base, TimestampMixin):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("tenant_id", "email", name="uq_users_tenant_email"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    email: Mapped[str] = mapped_column(EmailType)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(20), default="viewer")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Workflow(Base, TimestampMixin):
    __tablename__ = "workflows"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_workflows_tenant_name"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    active_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workflow_versions.id", use_alter=True, name="fk_workflow_active_version")
    )
    trigger_type: Mapped[str] = mapped_column(String(20), default="manual")
    trigger_config: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    criticality: Mapped[str] = mapped_column(String(10), default="medium")
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WorkflowVersion(Base):
    __tablename__ = "workflow_versions"
    __table_args__ = (
        UniqueConstraint("workflow_id", "version", name="uq_workflow_versions_workflow_version"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    workflow_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workflows.id"))
    version: Mapped[int] = mapped_column(Integer)
    definition: Mapped[dict[str, Any]] = mapped_column(JSONType)
    definition_hash: Mapped[str] = mapped_column(String(64))
    source_format: Mapped[str] = mapped_column(String(8), default="yaml")
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = _created_at()


class Execution(Base):
    __tablename__ = "executions"
    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    workflow_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workflows.id"))
    workflow_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workflow_versions.id"))
    temporal_workflow_id: Mapped[str] = mapped_column(String(255), unique=True)
    temporal_run_id: Mapped[str | None] = mapped_column(String(255))
    trigger_source: Mapped[str] = mapped_column(String(20), default="manual")
    triggered_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    input_context: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    output_context: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    replay_of_execution_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("executions.id"))
    created_at: Mapped[datetime] = _created_at()


class JobExecution(Base):
    __tablename__ = "job_executions"
    __table_args__ = (
        UniqueConstraint(
            "execution_id", "job_id", "attempt", name="uq_job_executions_exec_job_attempt"
        ),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    execution_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("executions.id"))
    job_id: Mapped[str] = mapped_column(String(100))
    job_type: Mapped[str] = mapped_column(String(20))
    agent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("agents.id"))
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    input: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    output: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    logs_ref: Mapped[str | None] = mapped_column(Text)
    error: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created_at()


class ExecutionEvent(Base):
    __tablename__ = "execution_events"
    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    execution_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("executions.id"))
    job_execution_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("job_executions.id"))
    event_type: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = _created_at()


class Artifact(Base):
    __tablename__ = "artifacts"
    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    execution_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("executions.id"))
    job_execution_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("job_executions.id"))
    name: Mapped[str] = mapped_column(String(255))
    bucket: Mapped[str] = mapped_column(String(255))
    object_key: Mapped[str] = mapped_column(Text)
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    content_type: Mapped[str | None] = mapped_column(String(255))
    checksum: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = _created_at()


class Agent(Base, TimestampMixin):
    __tablename__ = "agents"
    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="pending_approval")
    os: Mapped[str] = mapped_column(String(20), default="linux")
    task_queue: Mapped[str] = mapped_column(String(255))
    fingerprint: Mapped[str | None] = mapped_column(String(128))
    public_key: Mapped[str | None] = mapped_column(Text)
    labels: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    enrolled_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class Plugin(Base, TimestampMixin):
    __tablename__ = "plugins"
    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tenants.id"))
    name: Mapped[str] = mapped_column(String(100))
    version: Mapped[str] = mapped_column(String(40))
    kind: Mapped[str] = mapped_column(String(20), default="job")
    actions: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    input_schema: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    output_schema: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    plugin_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class Secret(Base, TimestampMixin):
    __tablename__ = "secrets"
    __table_args__ = (UniqueConstraint("tenant_id", "key", name="uq_secrets_tenant_key"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    key: Mapped[str] = mapped_column(String(200))
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    secret_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, default=dict)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(100))
    target_type: Mapped[str | None] = mapped_column(String(100))
    target_id: Mapped[str | None] = mapped_column(String(255))
    audit_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, default=dict)
    ip_address: Mapped[str | None] = mapped_column(IPType)
    created_at: Mapped[datetime] = _created_at()
