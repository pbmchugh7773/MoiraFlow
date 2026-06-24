"""DAG validation and ordering for a workflow's jobs.

Kahn's algorithm gives O(V + E) cycle detection and a deterministic topological
order (ties broken by definition order), which the interpreter needs to schedule
jobs without surprises.
"""

from __future__ import annotations

from .errors import WorkflowError
from .models import WorkflowDefinition

# edges: dependency -> [jobs that depend on it]; plus in-degree per job.
_Graph = tuple[dict[str, list[str]], dict[str, int]]


def _build_graph(wf: WorkflowDefinition) -> _Graph:
    successors: dict[str, list[str]] = {job.id: [] for job in wf.spec.jobs}
    indegree: dict[str, int] = {job.id: 0 for job in wf.spec.jobs}
    for job in wf.spec.jobs:
        for dep in job.needs:
            if dep in successors:  # unknown deps are reported separately
                successors[dep].append(job.id)
                indegree[job.id] += 1
    return successors, indegree


def validate_dag(wf: WorkflowDefinition) -> list[WorkflowError]:
    errors: list[WorkflowError] = []
    seen: set[str] = set()
    for i, job in enumerate(wf.spec.jobs):
        if job.id in seen:
            errors.append(
                WorkflowError(
                    "duplicate_job_id", f"job id '{job.id}' is not unique", f"spec.jobs[{i}].id"
                )
            )
        seen.add(job.id)

    for i, job in enumerate(wf.spec.jobs):
        for dep in job.needs:
            if dep not in seen:
                errors.append(
                    WorkflowError(
                        "unknown_dependency",
                        f"job '{job.id}' needs unknown job '{dep}'",
                        f"spec.jobs[{i}].needs",
                    )
                )

    # Only test for cycles when every edge points to a real job.
    if not any(e.code == "unknown_dependency" for e in errors) and _has_cycle(wf):
        errors.append(WorkflowError("cycle", "workflow jobs form a dependency cycle", "spec.jobs"))
    return errors


def _has_cycle(wf: WorkflowDefinition) -> bool:
    successors, indegree = _build_graph(wf)
    ready = [job_id for job_id, deg in indegree.items() if deg == 0]
    visited = 0
    while ready:
        node = ready.pop()
        visited += 1
        for nxt in successors[node]:
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                ready.append(nxt)
    return visited != len(wf.spec.jobs)


def topological_order(wf: WorkflowDefinition) -> list[str]:
    """Return job ids in dependency order. Raises ValueError if the graph is cyclic."""
    successors, indegree = _build_graph(wf)
    position = {job.id: i for i, job in enumerate(wf.spec.jobs)}
    ready = sorted((j for j, deg in indegree.items() if deg == 0), key=lambda j: position[j])
    order: list[str] = []
    while ready:
        node = ready.pop(0)
        order.append(node)
        for nxt in successors[node]:
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                ready.append(nxt)
        ready.sort(key=lambda j: position[j])
    if len(order) != len(wf.spec.jobs):
        raise ValueError("workflow has a cycle; call validate_dag first")
    return order
