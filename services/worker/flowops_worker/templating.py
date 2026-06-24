"""Deterministic template interpolation for the interpreter (ADR-0011).

Pure: no I/O, no time, no randomness, no filters — just dotted-path lookups. This
is the SAME reference surface that the API's validate_references() checks, so a
validated workflow renders without surprises, and running it inside a Temporal
workflow stays replay-safe.

`secret://...` values carry no `{{ }}` and pass through untouched; secrets are
resolved later by activities (late resolution, never in workflow code).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_EXPR = re.compile(r"\{\{\s*(.*?)\s*\}\}")
_WHOLE = re.compile(r"^\{\{\s*(.*?)\s*\}\}$")
_CONTEXT = re.compile(r"^context\.([a-zA-Z_]\w*)$")
_OUTPUT = re.compile(r"^jobs\.([a-z0-9_-]+)\.outputs\.([a-zA-Z_]\w*)$")


class TemplateError(Exception):
    """Raised when a template references a value that is not in scope."""


@dataclass(frozen=True)
class RenderScope:
    context: dict[str, Any]
    outputs: dict[str, dict[str, Any]]


def _resolve(expr: str, scope: RenderScope) -> Any:
    ctx = _CONTEXT.match(expr)
    if ctx:
        key = ctx.group(1)
        if key not in scope.context:
            raise TemplateError(f"unknown reference: context.{key}")
        return scope.context[key]

    out = _OUTPUT.match(expr)
    if out:
        job_id, out_key = out.group(1), out.group(2)
        job_outputs = scope.outputs.get(job_id)
        if job_outputs is None or out_key not in job_outputs:
            raise TemplateError(f"unknown reference: jobs.{job_id}.outputs.{out_key}")
        return job_outputs[out_key]

    raise TemplateError(f"unsupported template expression: {expr!r}")


def render_template(text: str, scope: RenderScope) -> Any:
    """Render a single template string.

    If the whole string is exactly one expression, the resolved value keeps its
    original type (e.g. an int stays an int). Otherwise every expression is
    substituted as text.
    """
    whole = _WHOLE.match(text)
    if whole:
        return _resolve(whole.group(1), scope)

    return _EXPR.sub(lambda m: str(_resolve(m.group(1), scope)), text)


def render_job_inputs(value: Any, scope: RenderScope) -> Any:
    """Recursively render every string in a job's `with` mapping."""
    if isinstance(value, str):
        return render_template(value, scope)
    if isinstance(value, dict):
        return {k: render_job_inputs(v, scope) for k, v in value.items()}
    if isinstance(value, list):
        return [render_job_inputs(v, scope) for v in value]
    return value
