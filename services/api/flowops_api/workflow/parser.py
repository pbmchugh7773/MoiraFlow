"""Turn raw YAML/JSON into a validated WorkflowDefinition."""

from __future__ import annotations

import json
from typing import Any, Literal

import yaml
from pydantic import ValidationError as PydValidationError

from .models import WorkflowDefinition

SourceFormat = Literal["yaml", "json", "dict"]


class ParseError(Exception):
    """Raised when raw input is not a structurally valid workflow."""

    def __init__(self, message: str, loc: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.loc = loc


def _load(raw: str | dict[str, Any], source_format: SourceFormat) -> dict[str, Any]:
    if source_format == "dict":
        if not isinstance(raw, dict):
            raise ParseError("expected a mapping for source_format='dict'")
        return raw
    if not isinstance(raw, str):
        raise ParseError(f"expected a string for source_format={source_format!r}")
    try:
        data = yaml.safe_load(raw) if source_format == "yaml" else json.loads(raw)
    except (yaml.YAMLError, json.JSONDecodeError) as exc:
        raise ParseError(f"malformed {source_format}: {exc}") from exc
    if not isinstance(data, dict):
        raise ParseError("workflow document must be a mapping at the top level")
    return data


def parse_definition(
    raw: str | dict[str, Any], source_format: SourceFormat = "yaml"
) -> WorkflowDefinition:
    data = _load(raw, source_format)
    try:
        return WorkflowDefinition.model_validate(data)
    except PydValidationError as exc:
        first = exc.errors()[0]
        loc = ".".join(str(p) for p in first["loc"])
        raise ParseError(f"{loc}: {first['msg']}", loc=loc) from exc
