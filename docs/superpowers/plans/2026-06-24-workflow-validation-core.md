# Workflow Definition & Validation Core — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the pure-Python core that parses a FlowOps workflow (YAML/JSON), validates it structurally and semantically (DAG + template references), and produces a canonical content hash — with zero infrastructure dependencies.

**Architecture:** Pydantic v2 models are the single source of truth for structure (and the published JSON Schema is generated from them with `model_json_schema()`). A separate semantic validator covers what JSON Schema cannot express: DAG acyclicity, `needs` integrity, and `{{ jobs.X.outputs.Y }}` reference resolution. A top-level `validate_workflow()` aggregates everything into `{valid, errors[]}`. This is the foundation the API `POST /workflows/validate` endpoint and the Temporal interpreter will both consume.

**Tech Stack:** Python 3.12, Pydantic v2, PyYAML, pytest, ruff, black, mypy.

## Global Constraints

- Python 3.12; Pydantic v2 (`pydantic>=2.6`); product/code in **English**.
- Every model uses `ConfigDict(extra="forbid")` — unknown keys are validation errors (docs 04 §B.6 rule 1).
- Templating is **deterministic**: the reference validator rejects non-deterministic filters (`now()`, `random`) per ADR-0011. (Full interpolation engine is a later slice; this slice only validates references.)
- Context model is **declared-outputs** (ADR-0013): jobs expose `outputs`; there is no shared mutable blob. Reference validation enforces `jobs.<id>.outputs.<key>` resolves to a declared output of a job in `needs`.
- Job `id` and `metadata.name` match `^[a-z0-9_-]+$` (docs 04 §B.2/B.3).
- MVP job types: `command`, `rest`, `sql` only.
- All errors returned as structured `ValidationError` items with `code`, `message`, `loc` (path) — never raise raw exceptions to callers of `validate_workflow()`.

---

### Task 1: API package scaffold + workflow models

**Files:**
- Create: `services/api/pyproject.toml`
- Create: `services/api/flowops_api/__init__.py`
- Create: `services/api/flowops_api/workflow/__init__.py`
- Create: `services/api/flowops_api/workflow/models.py`
- Create: `services/api/tests/__init__.py`
- Test: `services/api/tests/test_models.py`

**Interfaces:**
- Produces: `WorkflowDefinition`, `Spec`, `Job`, `Trigger`, `Metadata`, `RetryPolicy` Pydantic models. `Job` fields: `id: str`, `type: Literal["command","rest","sql"]`, `run_on: Literal["server","agent"]="server"`, `agent_selector: dict[str,str]|None`, `needs: list[str]=[]`, `with_: dict[str,Any]` (alias `with`), `timeout: str|None`, `retry: RetryPolicy|None`, `outputs: dict[str,str]={}`, `condition: str|None`. `WorkflowDefinition` fields: `api_version: Literal["flowops/v1"]` (alias `apiVersion`), `kind: Literal["Workflow"]`, `metadata: Metadata`, `spec: Spec`.

- [ ] **Step 1: Write the failing test**

```python
# services/api/tests/test_models.py
import pytest
from pydantic import ValidationError as PydValidationError

from flowops_api.workflow.models import WorkflowDefinition, Job

VALID = {
    "apiVersion": "flowops/v1",
    "kind": "Workflow",
    "metadata": {"name": "daily_import"},
    "spec": {
        "trigger": {"type": "manual"},
        "jobs": [
            {"id": "fetch", "type": "rest", "with": {"method": "GET", "url": "https://x"}},
        ],
    },
}


def test_parses_minimal_valid_workflow():
    wf = WorkflowDefinition.model_validate(VALID)
    assert wf.metadata.name == "daily_import"
    assert wf.spec.jobs[0].id == "fetch"
    assert wf.spec.jobs[0].run_on == "server"  # default


def test_with_keyword_is_aliased():
    job = Job.model_validate({"id": "j1", "type": "command", "with": {"command": "ls"}})
    assert job.with_ == {"command": "ls"}


def test_unknown_key_is_rejected():
    bad = {**VALID, "spec": {**VALID["spec"], "bogus": 1}}
    with pytest.raises(PydValidationError):
        WorkflowDefinition.model_validate(bad)


def test_invalid_job_id_rejected():
    with pytest.raises(PydValidationError):
        Job.model_validate({"id": "Bad ID!", "type": "command", "with": {"command": "ls"}})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/api && python -m pytest tests/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'flowops_api'`

- [ ] **Step 3: Write the pyproject and models**

```toml
# services/api/pyproject.toml
[project]
name = "flowops-api"
version = "0.1.0"
description = "FlowOps API service"
requires-python = ">=3.12"
dependencies = [
    "pydantic>=2.6",
    "pyyaml>=6.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "ruff>=0.4", "black>=24.0", "mypy>=1.10"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["flowops_api"]

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.black]
line-length = 100
```

```python
# services/api/flowops_api/__init__.py
```

```python
# services/api/flowops_api/workflow/__init__.py
```

```python
# services/api/flowops_api/workflow/models.py
"""Pydantic v2 models — the single source of truth for the workflow-as-code schema.

The published JSON Schema (catalog/workflow-schema) is generated from these models.
Structural rules live here (extra="forbid", patterns, enums); semantic rules
(DAG acyclicity, reference resolution) live in validator.py.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

JobType = Literal["command", "rest", "sql"]
RunOn = Literal["server", "agent"]
TriggerType = Literal["cron", "manual", "webhook", "event"]
OnError = Literal["fail", "continue", "compensate"]
RetryStrategy = Literal["fixed", "exponential", "custom"]

_NAME_PATTERN = r"^[a-z0-9_-]+$"

_STRICT = ConfigDict(extra="forbid", populate_by_name=True)


class RetryPolicy(BaseModel):
    model_config = _STRICT
    strategy: RetryStrategy = "fixed"
    max_attempts: int = Field(default=1, ge=1, le=100)
    initial_interval: str | None = None
    interval: str | None = None


class Job(BaseModel):
    model_config = _STRICT
    id: str = Field(pattern=_NAME_PATTERN)
    type: JobType
    run_on: RunOn = "server"
    agent_selector: dict[str, str] | None = None
    needs: list[str] = Field(default_factory=list)
    with_: dict[str, Any] = Field(alias="with")
    timeout: str | None = None
    retry: RetryPolicy | None = None
    outputs: dict[str, str] = Field(default_factory=dict)
    condition: str | None = None


class Trigger(BaseModel):
    model_config = _STRICT
    type: TriggerType
    cron: str | None = None
    timezone: str | None = None


class Sla(BaseModel):
    model_config = _STRICT
    expected_duration: str | None = None
    deadline: str | None = None
    criticality: Literal["low", "medium", "high"] | None = None


class Spec(BaseModel):
    model_config = _STRICT
    trigger: Trigger
    context: dict[str, Any] = Field(default_factory=dict)
    on_error: OnError = "fail"
    sla: Sla | None = None
    jobs: list[Job] = Field(min_length=1)


class Metadata(BaseModel):
    model_config = _STRICT
    name: str = Field(pattern=_NAME_PATTERN)
    description: str | None = None
    labels: dict[str, str] = Field(default_factory=dict)


class WorkflowDefinition(BaseModel):
    model_config = _STRICT
    api_version: Literal["flowops/v1"] = Field(alias="apiVersion")
    kind: Literal["Workflow"]
    metadata: Metadata
    spec: Spec
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd services/api && python -m pip install -e ".[dev]" && python -m pytest tests/test_models.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add services/api/pyproject.toml services/api/flowops_api services/api/tests
git commit -m "feat(api): workflow-as-code Pydantic models + package scaffold"
```

---

### Task 2: Parse YAML/JSON into the model

**Files:**
- Create: `services/api/flowops_api/workflow/parser.py`
- Test: `services/api/tests/test_parser.py`

**Interfaces:**
- Consumes: `WorkflowDefinition` from Task 1.
- Produces: `parse_definition(raw: str | dict, source_format: Literal["yaml","json","dict"]="yaml") -> WorkflowDefinition`. Raises `ParseError(message, loc)` on malformed YAML/JSON or schema violation; never returns a partial object.

- [ ] **Step 1: Write the failing test**

```python
# services/api/tests/test_parser.py
import pytest

from flowops_api.workflow.parser import parse_definition, ParseError

YAML = """
apiVersion: flowops/v1
kind: Workflow
metadata:
  name: daily_import
spec:
  trigger:
    type: manual
  jobs:
    - id: fetch
      type: rest
      with: { method: GET, url: "https://x" }
"""


def test_parses_yaml():
    wf = parse_definition(YAML, "yaml")
    assert wf.spec.jobs[0].id == "fetch"


def test_parses_json_string():
    import json
    wf = parse_definition(json.dumps({
        "apiVersion": "flowops/v1", "kind": "Workflow",
        "metadata": {"name": "n"},
        "spec": {"trigger": {"type": "manual"},
                 "jobs": [{"id": "j", "type": "command", "with": {"command": "ls"}}]},
    }), "json")
    assert wf.spec.jobs[0].type == "command"


def test_malformed_yaml_raises_parse_error():
    with pytest.raises(ParseError):
        parse_definition("metadata: [unclosed", "yaml")


def test_schema_violation_raises_parse_error():
    with pytest.raises(ParseError):
        parse_definition("apiVersion: flowops/v1\nkind: Workflow\n", "yaml")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/api && python -m pytest tests/test_parser.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'flowops_api.workflow.parser'`

- [ ] **Step 3: Write the parser**

```python
# services/api/flowops_api/workflow/parser.py
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd services/api && python -m pytest tests/test_parser.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add services/api/flowops_api/workflow/parser.py services/api/tests/test_parser.py
git commit -m "feat(api): YAML/JSON workflow parser with ParseError"
```

---

### Task 3: DAG validation (unique ids, needs integrity, acyclicity)

**Files:**
- Create: `services/api/flowops_api/workflow/errors.py`
- Create: `services/api/flowops_api/workflow/dag.py`
- Test: `services/api/tests/test_dag.py`

**Interfaces:**
- Consumes: `WorkflowDefinition`, `Job` from Task 1.
- Produces: `errors.WorkflowError` dataclass with fields `code: str`, `message: str`, `loc: str`. `dag.validate_dag(wf: WorkflowDefinition) -> list[WorkflowError]` — returns `[]` when the DAG is valid. Codes used: `duplicate_job_id`, `unknown_dependency`, `cycle`. `dag.topological_order(wf) -> list[str]` returns job ids in dependency order (raises `ValueError` if cyclic — callers must validate first).

- [ ] **Step 1: Write the failing test**

```python
# services/api/tests/test_dag.py
from flowops_api.workflow.dag import validate_dag, topological_order
from flowops_api.workflow.parser import parse_definition


def _wf(jobs):
    return parse_definition(
        {"apiVersion": "flowops/v1", "kind": "Workflow",
         "metadata": {"name": "n"},
         "spec": {"trigger": {"type": "manual"}, "jobs": jobs}}, "dict")


def test_valid_dag_has_no_errors():
    wf = _wf([
        {"id": "a", "type": "command", "with": {"command": "ls"}},
        {"id": "b", "type": "command", "with": {"command": "ls"}, "needs": ["a"]},
    ])
    assert validate_dag(wf) == []
    assert topological_order(wf) == ["a", "b"]


def test_duplicate_id_detected():
    wf = _wf([
        {"id": "a", "type": "command", "with": {"command": "ls"}},
        {"id": "a", "type": "command", "with": {"command": "ls"}},
    ])
    codes = [e.code for e in validate_dag(wf)]
    assert "duplicate_job_id" in codes


def test_unknown_dependency_detected():
    wf = _wf([
        {"id": "a", "type": "command", "with": {"command": "ls"}, "needs": ["ghost"]},
    ])
    codes = [e.code for e in validate_dag(wf)]
    assert "unknown_dependency" in codes


def test_cycle_detected():
    wf = _wf([
        {"id": "a", "type": "command", "with": {"command": "ls"}, "needs": ["b"]},
        {"id": "b", "type": "command", "with": {"command": "ls"}, "needs": ["a"]},
    ])
    codes = [e.code for e in validate_dag(wf)]
    assert "cycle" in codes
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/api && python -m pytest tests/test_dag.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'flowops_api.workflow.dag'`

- [ ] **Step 3: Write errors + dag (Kahn's algorithm)**

```python
# services/api/flowops_api/workflow/errors.py
"""Structured validation error shared across validators."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WorkflowError:
    code: str
    message: str
    loc: str = ""
```

```python
# services/api/flowops_api/workflow/dag.py
"""DAG validation and ordering for a workflow's jobs.

Kahn's algorithm gives O(V + E) cycle detection and a deterministic
topological order (ties broken by definition order), which the interpreter
needs to schedule jobs without surprises.
"""
from __future__ import annotations

from .errors import WorkflowError
from .models import WorkflowDefinition


def validate_dag(wf: WorkflowDefinition) -> list[WorkflowError]:
    errors: list[WorkflowError] = []
    ids: list[str] = []
    seen: set[str] = set()
    for i, job in enumerate(wf.spec.jobs):
        if job.id in seen:
            errors.append(WorkflowError("duplicate_job_id",
                          f"job id '{job.id}' is not unique", f"spec.jobs[{i}].id"))
        seen.add(job.id)
        ids.append(job.id)

    for i, job in enumerate(wf.spec.jobs):
        for dep in job.needs:
            if dep not in seen:
                errors.append(WorkflowError("unknown_dependency",
                              f"job '{job.id}' needs unknown job '{dep}'",
                              f"spec.jobs[{i}].needs"))

    # Cycle detection only over edges between known jobs.
    if not any(e.code == "unknown_dependency" for e in errors):
        if _has_cycle(wf):
            errors.append(WorkflowError("cycle",
                          "workflow jobs form a dependency cycle", "spec.jobs"))
    return errors


def _adjacency(wf: WorkflowDefinition) -> dict[str, list[str]]:
    # edge dep -> job (dep must run before job)
    out: dict[str, list[str]] = {job.id: [] for job in wf.spec.jobs}
    indeg: dict[str, int] = {job.id: 0 for job in wf.spec.jobs}
    for job in wf.spec.jobs:
        for dep in job.needs:
            out[dep].append(job.id)
            indeg[job.id] += 1
    return out, indeg  # type: ignore[return-value]


def _has_cycle(wf: WorkflowDefinition) -> bool:
    out, indeg = _adjacency(wf)  # type: ignore[misc]
    queue = [j for j, d in indeg.items() if d == 0]
    visited = 0
    while queue:
        n = queue.pop()
        visited += 1
        for m in out[n]:
            indeg[m] -= 1
            if indeg[m] == 0:
                queue.append(m)
    return visited != len(wf.spec.jobs)


def topological_order(wf: WorkflowDefinition) -> list[str]:
    out, indeg = _adjacency(wf)  # type: ignore[misc]
    order_index = {job.id: i for i, job in enumerate(wf.spec.jobs)}
    ready = sorted((j for j, d in indeg.items() if d == 0), key=order_index.get)
    result: list[str] = []
    while ready:
        n = ready.pop(0)
        result.append(n)
        newly: list[str] = []
        for m in out[n]:
            indeg[m] -= 1
            if indeg[m] == 0:
                newly.append(m)
        ready = sorted(ready + newly, key=order_index.get)
    if len(result) != len(wf.spec.jobs):
        raise ValueError("workflow has a cycle; call validate_dag first")
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd services/api && python -m pytest tests/test_dag.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add services/api/flowops_api/workflow/errors.py services/api/flowops_api/workflow/dag.py services/api/tests/test_dag.py
git commit -m "feat(api): DAG validation (dup ids, needs integrity, cycle detection) + topo order"
```

---

### Task 4: Template reference validation (declared-outputs model)

**Files:**
- Create: `services/api/flowops_api/workflow/references.py`
- Test: `services/api/tests/test_references.py`

**Interfaces:**
- Consumes: `WorkflowDefinition`, `WorkflowError`.
- Produces: `references.validate_references(wf) -> list[WorkflowError]`. Scans every string in each job's `with_` (recursively) for `{{ ... }}` expressions. Codes: `unknown_context_ref` (`context.X` where X not in `spec.context`), `unknown_output_ref` (`jobs.X.outputs.Y` where job X absent, not in this job's `needs`, or Y not declared in X.outputs), `nondeterministic_template` (expression contains `now(` or `random`). `secret://` / `secrets.` references are allowed here (existence is checked later in `simulate`).

- [ ] **Step 1: Write the failing test**

```python
# services/api/tests/test_references.py
from flowops_api.workflow.references import validate_references
from flowops_api.workflow.parser import parse_definition


def _wf(jobs, context=None):
    spec = {"trigger": {"type": "manual"}, "jobs": jobs}
    if context is not None:
        spec["context"] = context
    return parse_definition(
        {"apiVersion": "flowops/v1", "kind": "Workflow",
         "metadata": {"name": "n"}, "spec": spec}, "dict")


def test_valid_output_reference_ok():
    wf = _wf([
        {"id": "a", "type": "command", "with": {"command": "echo hi"},
         "outputs": {"path": "/tmp/x"}},
        {"id": "b", "type": "command", "needs": ["a"],
         "with": {"command": "cat {{ jobs.a.outputs.path }}"}},
    ])
    assert validate_references(wf) == []


def test_context_reference_ok():
    wf = _wf([{"id": "a", "type": "command",
               "with": {"command": "echo {{ context.url }}"}}],
             context={"url": "https://x"})
    assert validate_references(wf) == []


def test_unknown_context_ref_detected():
    wf = _wf([{"id": "a", "type": "command",
               "with": {"command": "echo {{ context.missing }}"}}])
    codes = [e.code for e in validate_references(wf)]
    assert "unknown_context_ref" in codes


def test_output_ref_to_undeclared_output_detected():
    wf = _wf([
        {"id": "a", "type": "command", "with": {"command": "echo"}},
        {"id": "b", "type": "command", "needs": ["a"],
         "with": {"command": "cat {{ jobs.a.outputs.path }}"}},
    ])
    codes = [e.code for e in validate_references(wf)]
    assert "unknown_output_ref" in codes


def test_output_ref_without_needs_detected():
    wf = _wf([
        {"id": "a", "type": "command", "with": {"command": "echo"},
         "outputs": {"path": "/tmp/x"}},
        {"id": "b", "type": "command",
         "with": {"command": "cat {{ jobs.a.outputs.path }}"}},
    ])
    codes = [e.code for e in validate_references(wf)]
    assert "unknown_output_ref" in codes


def test_nondeterministic_template_rejected():
    wf = _wf([{"id": "a", "type": "command",
               "with": {"command": "echo {{ now() }}"}}])
    codes = [e.code for e in validate_references(wf)]
    assert "nondeterministic_template" in codes
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/api && python -m pytest tests/test_references.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'flowops_api.workflow.references'`

- [ ] **Step 3: Write the reference validator**

```python
# services/api/flowops_api/workflow/references.py
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
_CONTEXT_REF = re.compile(r"\bcontext\.([a-zA-Z_][\w]*)")
_OUTPUT_REF = re.compile(r"\bjobs\.([a-z0-9_-]+)\.outputs\.([a-zA-Z_][\w]*)")
_NONDETERMINISTIC = re.compile(r"\bnow\s*\(|\brandom\b")


def _iter_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _iter_strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in _iter_strings(v)]
    return []


def validate_references(wf: WorkflowDefinition) -> list[WorkflowError]:
    errors: list[WorkflowError] = []
    context_keys = set(wf.spec.context.keys())
    outputs_by_job = {job.id: set(job.outputs.keys()) for job in wf.spec.jobs}

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
        errors.append(WorkflowError("nondeterministic_template",
                      f"job '{job.id}' uses a non-deterministic template: {expr.strip()!r}", loc))

    for key in _CONTEXT_REF.findall(expr):
        if key not in context_keys:
            errors.append(WorkflowError("unknown_context_ref",
                          f"job '{job.id}' references unknown context.{key}", loc))

    for dep_id, out_key in _OUTPUT_REF.findall(expr):
        if dep_id not in outputs_by_job:
            errors.append(WorkflowError("unknown_output_ref",
                          f"job '{job.id}' references outputs of unknown job '{dep_id}'", loc))
        elif dep_id not in job.needs:
            errors.append(WorkflowError("unknown_output_ref",
                          f"job '{job.id}' reads jobs.{dep_id}.outputs but does not declare it in needs", loc))
        elif out_key not in outputs_by_job[dep_id]:
            errors.append(WorkflowError("unknown_output_ref",
                          f"job '{job.id}' references undeclared output jobs.{dep_id}.outputs.{out_key}", loc))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd services/api && python -m pytest tests/test_references.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add services/api/flowops_api/workflow/references.py services/api/tests/test_references.py
git commit -m "feat(api): template reference validation (declared-outputs + determinism)"
```

---

### Task 5: Canonical normalization + content hash

**Files:**
- Create: `services/api/flowops_api/workflow/hashing.py`
- Test: `services/api/tests/test_hashing.py`

**Interfaces:**
- Consumes: `WorkflowDefinition`.
- Produces: `hashing.canonical_dict(wf) -> dict` (JSON-mode dump, by alias) and `hashing.definition_hash(wf) -> str` (sha256 hex of the canonical JSON with sorted keys). Equal-meaning definitions that differ only in key order or whitespace hash identically; any semantic change changes the hash. Used by `workflow_versions.definition_hash` (docs 03 §3.4).

- [ ] **Step 1: Write the failing test**

```python
# services/api/tests/test_hashing.py
from flowops_api.workflow.hashing import definition_hash, canonical_dict
from flowops_api.workflow.parser import parse_definition

BASE = {"apiVersion": "flowops/v1", "kind": "Workflow",
        "metadata": {"name": "n"},
        "spec": {"trigger": {"type": "manual"},
                 "jobs": [{"id": "a", "type": "command", "with": {"command": "ls"}}]}}


def test_hash_is_stable_and_hex():
    h = definition_hash(parse_definition(BASE, "dict"))
    assert isinstance(h, str) and len(h) == 64
    assert h == definition_hash(parse_definition(BASE, "dict"))


def test_key_order_does_not_change_hash():
    reordered = {"kind": "Workflow", "apiVersion": "flowops/v1",
                 "spec": BASE["spec"], "metadata": {"name": "n"}}
    assert definition_hash(parse_definition(BASE, "dict")) == \
           definition_hash(parse_definition(reordered, "dict"))


def test_semantic_change_changes_hash():
    changed = {**BASE, "metadata": {"name": "different"}}
    assert definition_hash(parse_definition(BASE, "dict")) != \
           definition_hash(parse_definition(changed, "dict"))


def test_canonical_dict_uses_aliases():
    cd = canonical_dict(parse_definition(BASE, "dict"))
    assert cd["apiVersion"] == "flowops/v1"
    assert cd["spec"]["jobs"][0]["with"] == {"command": "ls"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/api && python -m pytest tests/test_hashing.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'flowops_api.workflow.hashing'`

- [ ] **Step 3: Write the hashing module**

```python
# services/api/flowops_api/workflow/hashing.py
"""Canonical normalization + content hash for immutable versioning (docs 03 §3.4)."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from .models import WorkflowDefinition


def canonical_dict(wf: WorkflowDefinition) -> dict[str, Any]:
    # mode="json" makes the structure JSON-serializable; by_alias keeps the
    # external field names (apiVersion, with). Defaults are included so two
    # definitions with the same effective meaning hash identically.
    return wf.model_dump(mode="json", by_alias=True)


def definition_hash(wf: WorkflowDefinition) -> str:
    canonical = json.dumps(canonical_dict(wf), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd services/api && python -m pytest tests/test_hashing.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add services/api/flowops_api/workflow/hashing.py services/api/tests/test_hashing.py
git commit -m "feat(api): canonical normalization + sha256 content hash"
```

---

### Task 6: `validate_workflow()` aggregator + generated JSON Schema

**Files:**
- Create: `services/api/flowops_api/workflow/validator.py`
- Modify: `services/api/flowops_api/workflow/__init__.py` (export public API)
- Test: `services/api/tests/test_validator.py`

**Interfaces:**
- Consumes: everything above.
- Produces: `validator.ValidationResult` dataclass `{valid: bool, errors: list[WorkflowError]}`; `validator.validate_workflow(raw, source_format="yaml") -> ValidationResult` (never raises — parse failures become a single `WorkflowError(code="parse_error")`); `validator.workflow_json_schema() -> dict` (the published JSON Schema generated from the Pydantic model). `__init__` re-exports `parse_definition`, `validate_workflow`, `ValidationResult`, `WorkflowError`, `definition_hash`, `workflow_json_schema`.

- [ ] **Step 1: Write the failing test**

```python
# services/api/tests/test_validator.py
from flowops_api.workflow import (
    validate_workflow, ValidationResult, workflow_json_schema,
)

GOOD = """
apiVersion: flowops/v1
kind: Workflow
metadata: { name: daily_import }
spec:
  trigger: { type: manual }
  context: { url: "https://x" }
  jobs:
    - id: fetch
      type: command
      with: { command: "curl {{ context.url }}" }
      outputs: { path: /tmp/data }
    - id: load
      type: command
      needs: [fetch]
      with: { command: "cat {{ jobs.fetch.outputs.path }}" }
"""


def test_good_workflow_is_valid():
    result = validate_workflow(GOOD, "yaml")
    assert isinstance(result, ValidationResult)
    assert result.valid is True
    assert result.errors == []


def test_parse_error_becomes_structured_error():
    result = validate_workflow("metadata: [unclosed", "yaml")
    assert result.valid is False
    assert result.errors[0].code == "parse_error"


def test_semantic_errors_aggregated():
    bad = """
apiVersion: flowops/v1
kind: Workflow
metadata: { name: n }
spec:
  trigger: { type: manual }
  jobs:
    - id: a
      type: command
      needs: [ghost]
      with: { command: "echo {{ context.missing }}" }
"""
    result = validate_workflow(bad, "yaml")
    assert result.valid is False
    codes = {e.code for e in result.errors}
    assert "unknown_dependency" in codes
    assert "unknown_context_ref" in codes


def test_json_schema_is_generated():
    schema = workflow_json_schema()
    assert schema["title"] == "WorkflowDefinition"
    assert "properties" in schema
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/api && python -m pytest tests/test_validator.py -v`
Expected: FAIL — `ImportError: cannot import name 'validate_workflow'`

- [ ] **Step 3: Write the aggregator and exports**

```python
# services/api/flowops_api/workflow/validator.py
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
```

```python
# services/api/flowops_api/workflow/__init__.py
"""Public surface of the workflow validation core."""
from .errors import WorkflowError
from .hashing import canonical_dict, definition_hash
from .models import WorkflowDefinition
from .parser import ParseError, parse_definition
from .validator import ValidationResult, validate_workflow, workflow_json_schema

__all__ = [
    "WorkflowDefinition", "parse_definition", "ParseError",
    "validate_workflow", "ValidationResult", "WorkflowError",
    "definition_hash", "canonical_dict", "workflow_json_schema",
]
```

- [ ] **Step 4: Run the full suite to verify it passes**

Run: `cd services/api && python -m pytest -v`
Expected: PASS (all tasks' tests green)

- [ ] **Step 5: Lint, type-check, commit**

```bash
cd services/api && python -m ruff check flowops_api && python -m black --check flowops_api && python -m mypy flowops_api
git add services/api/flowops_api/workflow/validator.py services/api/flowops_api/workflow/__init__.py services/api/tests/test_validator.py
git commit -m "feat(api): validate_workflow aggregator + generated JSON Schema"
```

---

## Self-Review

**Spec coverage (docs 04 §B.6 validation rules):**
- Rule 1 (structural JSON Schema): Task 1 (`extra="forbid"`, patterns, enums) + Task 6 (generated schema). ✓
- Rule 2 (unique ids, needs exist, no cycles): Task 3. ✓
- Rule 3 (`type` in catalog, `with` matches type schema): **partially deferred** — `type` enum is enforced (Task 1); per-type `with` schema validation needs the plugin catalog (next slice). Noted, not a gap in this slice's scope.
- Rule 4 (`run_on: agent` requires resolvable `agent_selector`): belongs to `simulate` (needs agent registry) — out of this slice. Noted.
- Rule 5 (`{{ jobs.X.outputs.Y }}` declared): Task 4. ✓
- Rule 6 (`secret://k` exists): belongs to `simulate` (needs secrets store) — out of this slice. Noted.
- Content hash for immutable versioning (docs 03 §3.4): Task 5. ✓
- Deterministic templating (ADR-0011) + declared-outputs (ADR-0013): Task 4. ✓

**Placeholder scan:** none — every step has runnable code/commands.

**Type consistency:** `WorkflowError(code, message, loc)` used identically across dag/references/validator; `parse_definition(raw, source_format)` signature consistent; `validate_workflow` returns `ValidationResult` as exported. ✓

**Deferred to next slices (explicitly, not silently):** per-type `with` schema validation, `simulate` (agent/secret resolution), the FastAPI endpoint wiring `POST /workflows/validate`, persistence. These require the plugin catalog / DB and belong to their own plans.
