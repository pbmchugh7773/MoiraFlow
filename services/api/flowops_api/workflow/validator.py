"""Top-level validation entrypoint: never raises, aggregates all rules."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .dag import validate_dag
from .errors import WorkflowError
from .models import WorkflowDefinition
from .parser import ParseError, SourceFormat, parse_definition
from .references import validate_references


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    errors: list[WorkflowError] = field(default_factory=list)


def validate_workflow(
    raw: str | dict[str, Any], source_format: SourceFormat = "yaml"
) -> ValidationResult:
    try:
        wf = parse_definition(raw, source_format)
    except ParseError as exc:
        return ValidationResult(False, [WorkflowError("parse_error", exc.message, exc.loc)])

    errors = [*validate_dag(wf), *validate_references(wf)]
    return ValidationResult(not errors, errors)


def workflow_json_schema() -> dict[str, Any]:
    return WorkflowDefinition.model_json_schema(by_alias=True)
