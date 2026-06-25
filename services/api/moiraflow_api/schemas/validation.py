"""Request/response models for the workflow validation endpoint (API contract)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from ..workflow import ValidationResult, WorkflowError


class ValidateRequest(BaseModel):
    content: str = Field(description="Raw workflow definition (YAML or JSON text).")
    format: Literal["yaml", "json"] = "yaml"


class ValidationErrorOut(BaseModel):
    code: str
    message: str
    loc: str = ""

    @classmethod
    def from_error(cls, error: WorkflowError) -> "ValidationErrorOut":
        return cls(code=error.code, message=error.message, loc=error.loc)


class ValidateResponse(BaseModel):
    valid: bool
    errors: list[ValidationErrorOut]

    @classmethod
    def from_result(cls, result: ValidationResult) -> "ValidateResponse":
        return cls(
            valid=result.valid,
            errors=[ValidationErrorOut.from_error(e) for e in result.errors],
        )
