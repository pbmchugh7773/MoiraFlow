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
