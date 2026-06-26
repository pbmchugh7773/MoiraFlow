"""Machine-readable catalog endpoints (AI First — consumed by MoiraFlow Architect)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import models
from ..deps import get_current_tenant, get_session
from ..workflow import workflow_json_schema
from ..workflow.catalog import job_types_catalog

router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.get("/workflow-schema")
def workflow_schema() -> dict[str, Any]:
    """The JSON Schema of the workflow-as-code format (generated from the models)."""
    return workflow_json_schema()


@router.get("/job-types")
def job_types() -> list[dict[str, Any]]:
    """Built-in job types with their `with` input/output schemas."""
    return job_types_catalog()


@router.get("/connectors")
def connectors(
    session: Session = Depends(get_session),
    tenant: models.Tenant = Depends(get_current_tenant),
) -> list[dict[str, Any]]:
    """Registered plugins/connectors (global + this tenant's). Empty in the MVP."""
    rows = session.scalars(
        select(models.Plugin).where(
            (models.Plugin.tenant_id == tenant.id) | (models.Plugin.tenant_id.is_(None))
        )
    )
    return [
        {"name": p.name, "version": p.version, "kind": p.kind, "actions": p.actions} for p in rows
    ]
