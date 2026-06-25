"""Workflow endpoints. MVP slice: structural + semantic validation (no persistence yet)."""

from __future__ import annotations

from fastapi import APIRouter

from ..schemas.validation import ValidateRequest, ValidateResponse
from ..workflow import validate_workflow

router = APIRouter(prefix="/workflows", tags=["workflows"])


@router.post("/validate", response_model=ValidateResponse)
def validate(request: ValidateRequest) -> ValidateResponse:
    """Validate a workflow definition. Always returns 200; problems are in `errors`.

    A 200-with-errors contract (rather than 4xx) keeps the endpoint machine-friendly
    for the UI editor and the future MoiraFlow Architect, which expect a structured
    report, not an HTTP error.
    """
    result = validate_workflow(request.content, request.format)
    return ValidateResponse.from_result(result)
