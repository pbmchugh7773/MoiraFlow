"""Agent registry & lifecycle endpoints (Hito 5, slice 1).

enroll/approve/revoke/list are admin-only; `register` is authenticated by the
single-use enrollment token (the agent has no JWT yet).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import models
from ..deps import (
    get_agent_token_store,
    get_current_tenant,
    get_current_user,
    get_session,
    require_roles,
)
from ..schemas.agents import AgentOut, EnrollResponse, RegisterAgentRequest, RegisterResponse
from ..services import agents as svc
from ..services import audit as audit_svc
from ..services.agents import AgentTokenStore, InvalidEnrollmentTokenError

router = APIRouter(prefix="/agents", tags=["agents"])


@router.post("/enroll", response_model=EnrollResponse)
def enroll_agent(
    session: Session = Depends(get_session),
    tenant: models.Tenant = Depends(get_current_tenant),
    store: AgentTokenStore = Depends(get_agent_token_store),
    actor: models.User = Depends(require_roles()),
) -> EnrollResponse:
    token = store.issue(tenant.id)
    audit_svc.record(
        session,
        tenant_id=tenant.id,
        action="agent.enroll",
        actor_user_id=actor.id,
        target_type="agent",
        target_id=None,
    )
    return EnrollResponse(
        enrollment_token=token, temporal_host=get_settings().temporal_host, expires_in=900
    )


@router.post("/register", response_model=RegisterResponse)
def register_agent(
    request: RegisterAgentRequest,
    session: Session = Depends(get_session),
    store: AgentTokenStore = Depends(get_agent_token_store),
) -> RegisterResponse:
    tenant_id = store.consume(request.token)
    if tenant_id is None:
        raise InvalidEnrollmentTokenError("invalid or expired enrollment token")
    agent = svc.register_agent(session, tenant_id, request.name, request.public_key)
    audit_svc.record(
        session,
        tenant_id=tenant_id,
        action="agent.register",
        target_type="agent",
        target_id=str(agent.id),
        metadata={"name": agent.name},
    )
    return RegisterResponse(agent_id=agent.id, task_queue=agent.task_queue, status=agent.status)


@router.get("", response_model=list[AgentOut])
def list_agents(
    session: Session = Depends(get_session),
    tenant: models.Tenant = Depends(get_current_tenant),
    _: models.User = Depends(get_current_user),
) -> list[AgentOut]:
    return [AgentOut.model_validate(a) for a in svc.list_agents(session, tenant.id)]


@router.post("/{agent_id}/approve", response_model=AgentOut)
def approve_agent(
    agent_id: uuid.UUID,
    session: Session = Depends(get_session),
    tenant: models.Tenant = Depends(get_current_tenant),
    actor: models.User = Depends(require_roles()),
) -> AgentOut:
    agent = svc.approve_agent(session, agent_id)
    audit_svc.record(
        session,
        tenant_id=tenant.id,
        action="agent.approve",
        actor_user_id=actor.id,
        target_type="agent",
        target_id=str(agent_id),
    )
    return AgentOut.model_validate(agent)


@router.post("/{agent_id}/revoke", response_model=AgentOut)
def revoke_agent(
    agent_id: uuid.UUID,
    session: Session = Depends(get_session),
    tenant: models.Tenant = Depends(get_current_tenant),
    actor: models.User = Depends(require_roles()),
) -> AgentOut:
    agent = svc.revoke_agent(session, agent_id)
    audit_svc.record(
        session,
        tenant_id=tenant.id,
        action="agent.revoke",
        actor_user_id=actor.id,
        target_type="agent",
        target_id=str(agent_id),
    )
    return AgentOut.model_validate(agent)
