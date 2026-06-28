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


# ── conditions (job `condition`) ─────────────────────────────────────────────
# Pure/deterministic, same reference surface as render_template. No eval(): only
# template lookups plus a single optional comparison, so it stays replay-safe.

_FALSY = {"", "false", "0", "no", "off", "none", "null"}
# Longest operators first so ">=" is matched before ">" (and "!=" before "=").
_COMPARATORS = ("==", "!=", ">=", "<=", ">", "<")


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if value is None:
        return False
    return str(value).strip().lower() not in _FALSY


def _operand(text: str, scope: RenderScope) -> Any:
    """Resolve one side of a comparison: a template expression keeps its type, a
    bare token is a literal string."""
    text = text.strip()
    return render_template(text, scope) if "{{" in text else text


def _equal(lhs: Any, rhs: Any) -> bool:
    if isinstance(lhs, bool) or isinstance(rhs, bool):
        return _truthy(lhs) == _truthy(rhs)
    return str(lhs).strip() == str(rhs).strip()


def _apply(op: str, lhs: Any, rhs: Any) -> bool:
    if op == "==":
        return _equal(lhs, rhs)
    if op == "!=":
        return not _equal(lhs, rhs)
    try:
        left: Any = float(str(lhs).strip())
        right: Any = float(str(rhs).strip())
    except ValueError:  # non-numeric ordering falls back to lexical comparison
        left, right = str(lhs).strip(), str(rhs).strip()
    return bool(
        {">": left > right, "<": left < right, ">=": left >= right, "<=": left <= right}[op]
    )


def evaluate_condition(condition: str, scope: RenderScope) -> bool:
    """Evaluate a job `condition` to a bool.

    Forms: a single template expression (truthy if it resolves to a non-empty,
    non-"false"/"0" value) or a binary comparison ``<lhs> <op> <rhs>`` with op in
    ``== != >= <= > <``. Operands may be template expressions or bare literals.
    Template expressions contain no operators (only dotted paths), so a plain scan
    for the comparator is unambiguous.
    """
    for op in _COMPARATORS:
        idx = condition.find(op)
        if idx != -1:
            lhs = _operand(condition[:idx], scope)
            rhs = _operand(condition[idx + len(op) :], scope)
            return _apply(op, lhs, rhs)
    return _truthy(_operand(condition, scope))
