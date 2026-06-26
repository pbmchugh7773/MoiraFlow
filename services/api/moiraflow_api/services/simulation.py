"""Dry-run a workflow (docs 04 §A.4): resolve the DAG, check secret:// refs and
agent routing — WITHOUT executing any effects. Returns an ordered plan + warnings.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from ..workflow import WorkflowError, parse_definition, validate_workflow
from ..workflow.dag import topological_order
from ..workflow.models import Job
from ..workflow.parser import SourceFormat
from . import secrets as secrets_svc

_SECRET_REF = re.compile(r"secret://([a-zA-Z0-9_-]+)")


@dataclass
class PlanStep:
    job_id: str
    type: str
    run_on: str
    task_queue: str
    needs: list[str]


@dataclass
class SimulationResult:
    valid: bool
    plan: list[PlanStep] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[WorkflowError] = field(default_factory=list)


def _iter_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _iter_strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in _iter_strings(v)]
    return []


def _secret_keys(job: Job) -> set[str]:
    keys: set[str] = set()
    for text in _iter_strings(job.with_):
        keys.update(_SECRET_REF.findall(text))
    return keys


def _task_queue(job: Job) -> str:
    if job.run_on != "agent":
        return "server"
    agent_id = (job.agent_selector or {}).get("agent_id", "local")
    return f"agent-{agent_id}"


def simulate(
    session: Session,
    tenant_id: uuid.UUID,
    content: str,
    source_format: SourceFormat = "yaml",
) -> SimulationResult:
    result = validate_workflow(content, source_format)
    if not result.valid:
        return SimulationResult(valid=False, errors=result.errors)

    workflow = parse_definition(content, source_format)
    jobs_by_id = {job.id: job for job in workflow.spec.jobs}
    warnings: list[str] = []
    plan: list[PlanStep] = []

    for job_id in topological_order(workflow):
        job = jobs_by_id[job_id]
        plan.append(
            PlanStep(
                job_id=job.id,
                type=job.type,
                run_on=job.run_on,
                task_queue=_task_queue(job),
                needs=list(job.needs),
            )
        )
        for key in _secret_keys(job):
            if not secrets_svc.secret_exists(session, tenant_id, key):
                warnings.append(f"job '{job.id}': secret '{key}' is not defined")

    return SimulationResult(valid=True, plan=plan, warnings=warnings)
