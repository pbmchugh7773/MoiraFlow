"""Agent registry & lifecycle (Hito 5, slice 1 — docs 05 §3).

Enroll (admin issues a single-use, short-lived token) -> register (agent presents
the token + its public key -> a pending_approval row) -> approve (admin) -> revoke.
The enrollment token store is injectable so the flow is testable without Redis.
"""

from __future__ import annotations

import secrets as pysecrets
import uuid
from datetime import datetime, timezone
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..agent_crypto import encrypt_for_agent
from ..db import models
from . import secrets as secrets_svc

_PENDING = "pending_approval"
_ACTIVE = {"approved", "online"}


class AgentServiceError(Exception):
    pass


class AgentNotFoundError(AgentServiceError):
    pass


class InvalidEnrollmentTokenError(AgentServiceError):
    pass


class AgentNotAuthorizedError(AgentServiceError):
    pass


class AgentTokenStore(Protocol):
    def issue(self, tenant_id: uuid.UUID, ttl_seconds: int = 900) -> str: ...

    def consume(self, token: str) -> uuid.UUID | None:
        """Atomically validate + invalidate a token (single-use). None if invalid."""
        ...


class RedisAgentTokenStore:
    def __init__(self, redis_url: str) -> None:
        self._redis_url = redis_url

    def _client(self) -> Any:
        import redis

        return redis.Redis.from_url(self._redis_url)

    def issue(self, tenant_id: uuid.UUID, ttl_seconds: int = 900) -> str:
        token = pysecrets.token_urlsafe(32)
        self._client().set(f"agent-enroll:{token}", str(tenant_id), ex=ttl_seconds, nx=True)
        return token

    def consume(self, token: str) -> uuid.UUID | None:
        raw = self._client().getdel(f"agent-enroll:{token}")
        if raw is None:
            return None
        return uuid.UUID(raw.decode() if isinstance(raw, bytes) else raw)


def register_agent(
    session: Session, tenant_id: uuid.UUID, name: str, public_key: str
) -> models.Agent:
    agent = models.Agent(
        tenant_id=tenant_id,
        name=name,
        status=_PENDING,
        os="linux",
        task_queue="",
        public_key=public_key,
    )
    session.add(agent)
    session.flush()  # assigns the id
    agent.task_queue = f"agent-{agent.id}"
    session.flush()
    return agent


def get_agent(session: Session, agent_id: uuid.UUID) -> models.Agent:
    agent = session.get(models.Agent, agent_id)
    if agent is None:
        raise AgentNotFoundError(f"agent {agent_id} not found")
    return agent


def approve_agent(session: Session, agent_id: uuid.UUID) -> models.Agent:
    agent = get_agent(session, agent_id)
    agent.status = "approved"
    session.flush()
    return agent


def revoke_agent(session: Session, agent_id: uuid.UUID) -> models.Agent:
    agent = get_agent(session, agent_id)
    agent.status = "revoked"
    session.flush()
    return agent


def verify_agent(session: Session, fingerprint: str) -> models.Agent:
    """Authorize an agent by its certificate fingerprint (the revocation gate). The
    control plane denies revoked/unapproved agents even though a task-queue name is
    not itself a security boundary (ADR-0012)."""
    agent = session.scalar(select(models.Agent).where(models.Agent.fingerprint == fingerprint))
    if agent is None:
        raise AgentNotAuthorizedError("unknown agent fingerprint")
    if agent.status == "revoked":
        raise AgentNotAuthorizedError("agent is revoked")
    if agent.status not in _ACTIVE:
        raise AgentNotAuthorizedError(f"agent not approved (status={agent.status})")
    return agent


def heartbeat(session: Session, agent: models.Agent) -> models.Agent:
    agent.status = "online"
    agent.last_heartbeat_at = datetime.now(timezone.utc)
    session.flush()
    return agent


def seal_secrets_for_agent(
    session: Session, agent: models.Agent, keys: list[str], master_key: str
) -> dict[str, str]:
    """Resolve each secret server-side and seal it to the agent's public key, so the
    plaintext never travels and the agent decrypts in memory (ADR-0013, slice 3)."""
    if not agent.public_key:
        raise AgentNotAuthorizedError("agent has no public key to seal secrets to")
    sealed: dict[str, str] = {}
    for key in keys:
        value = secrets_svc.get_value(session, master_key, agent.tenant_id, key)
        sealed[key] = encrypt_for_agent(agent.public_key, value)
    return sealed


def list_agents(session: Session, tenant_id: uuid.UUID) -> list[models.Agent]:
    return list(
        session.scalars(
            select(models.Agent)
            .where(models.Agent.tenant_id == tenant_id)
            .order_by(models.Agent.created_at)
        )
    )
