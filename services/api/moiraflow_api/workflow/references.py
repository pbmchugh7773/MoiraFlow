"""Validate {{ ... }} template references against the declared-outputs model.

Per ADR-0013 there is no shared mutable context: a job may only read
jobs.<dep>.outputs.<key> for a dep it declares in `needs`, and context.<key>
must exist in spec.context. Per ADR-0011 non-deterministic filters are banned.
"""

from __future__ import annotations

import re
from typing import Any

from .errors import WorkflowError
from .models import Job, WorkflowDefinition

_EXPR = re.compile(r"\{\{(.*?)\}\}", re.DOTALL)
_CONTEXT_REF = re.compile(r"\bcontext\.([a-zA-Z_]\w*)")
_OUTPUT_REF = re.compile(r"\bjobs\.([a-z0-9_-]+)\.outputs\.([a-zA-Z_]\w*)")
_NONDETERMINISTIC = re.compile(r"\bnow\s*\(|\brandom\b")


def _iter_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _iter_strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in _iter_strings(v)]
    return []


# Outputs some job types always produce, so they can be referenced downstream
# without being declared explicitly (the activity fills them at runtime).
_AUTO_OUTPUTS: dict[str, set[str]] = {
    "rest": {"status", "body"},
    "file_transfer": {"size", "artifact_key"},
}


def validate_references(wf: WorkflowDefinition) -> list[WorkflowError]:
    errors: list[WorkflowError] = []
    context_keys = set(wf.spec.context.keys())
    outputs_by_job = {
        job.id: set(job.outputs.keys()) | _AUTO_OUTPUTS.get(job.type, set()) for job in wf.spec.jobs
    }

    for i, job in enumerate(wf.spec.jobs):
        loc = f"spec.jobs[{i}].with"
        for text in _iter_strings(job.with_):
            for raw_expr in _EXPR.findall(text):
                _check_expression(raw_expr, job, context_keys, outputs_by_job, loc, errors)
    return errors


def _check_expression(
    expr: str,
    job: Job,
    context_keys: set[str],
    outputs_by_job: dict[str, set[str]],
    loc: str,
    errors: list[WorkflowError],
) -> None:
    if _NONDETERMINISTIC.search(expr):
        errors.append(
            WorkflowError(
                "nondeterministic_template",
                f"job '{job.id}' uses a non-deterministic template: {expr.strip()!r}",
                loc,
            )
        )

    for key in _CONTEXT_REF.findall(expr):
        if key not in context_keys:
            errors.append(
                WorkflowError(
                    "unknown_context_ref", f"job '{job.id}' references unknown context.{key}", loc
                )
            )

    for dep_id, out_key in _OUTPUT_REF.findall(expr):
        if dep_id not in outputs_by_job:
            errors.append(
                WorkflowError(
                    "unknown_output_ref",
                    f"job '{job.id}' references outputs of unknown job '{dep_id}'",
                    loc,
                )
            )
        elif dep_id not in job.needs:
            errors.append(
                WorkflowError(
                    "unknown_output_ref",
                    f"job '{job.id}' reads jobs.{dep_id}.outputs but does not declare "
                    f"it in needs",
                    loc,
                )
            )
        elif out_key not in outputs_by_job[dep_id]:
            errors.append(
                WorkflowError(
                    "unknown_output_ref",
                    f"job '{job.id}' references undeclared output "
                    f"jobs.{dep_id}.outputs.{out_key}",
                    loc,
                )
            )
