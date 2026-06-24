"""Machine-readable catalog endpoints (AI First — consumed by FlowOps Architect)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from ..workflow import workflow_json_schema

router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.get("/workflow-schema")
def workflow_schema() -> dict[str, Any]:
    """Return the JSON Schema of the workflow-as-code format (generated from the models)."""
    return workflow_json_schema()
