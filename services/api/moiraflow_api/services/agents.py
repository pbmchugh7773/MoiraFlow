"""Agent registry & lifecycle (Hito 5, slice 1 — docs 05 §3).

Enroll (admin issues a single-use, short-lived token) -> register (agent presents
the token + its public key -> a pending_approval row) -> approve (admin) -> revoke.
The enrollment token store is injectable so the flow is testable without Redis.
"""

from __future__ import annotations

import secrets as pysecrets
import uuid
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import models

_PENDING = "pending_approval"


class AgentServiceError(Exception):
    pass


class AgentNotFoundError(AgentServiceError):
    pass


class InvalidEnrollmentTokenError(AgentServiceError):
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


def list_agents(session: Session, tenant_id: uuid.UUID) -> list[models.Agent]:
    return list(
        session.scalars(
            select(models.Agent)
            .where(models.Agent.tenant_id == tenant_id)
            .order_by(models.Agent.created_at)
        )
    )
