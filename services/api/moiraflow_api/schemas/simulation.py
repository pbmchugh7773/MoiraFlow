"""Response models for workflow dry-run (simulate)."""

from __future__ import annotations

from pydantic import BaseModel

from ..services.simulation import SimulationResult
from .validation import ValidationErrorOut


class PlanStepOut(BaseModel):
    job_id: str
    type: str
    run_on: str
    task_queue: str
    needs: list[str]


class SimulateResponse(BaseModel):
    valid: bool
    plan: list[PlanStepOut]
    warnings: list[str]
    errors: list[ValidationErrorOut]

    @classmethod
    def from_result(cls, result: SimulationResult) -> "SimulateResponse":
        return cls(
            valid=result.valid,
            plan=[PlanStepOut(**vars(s)) for s in result.plan],
            warnings=result.warnings,
            errors=[ValidationErrorOut.from_error(e) for e in result.errors],
        )
