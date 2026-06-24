"""Structured validation error shared across validators."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WorkflowError:
    code: str
    message: str
    loc: str = ""
