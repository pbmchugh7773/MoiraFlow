"""Secret request/response models — values are write-only, never returned."""

from __future__ import annotations

from pydantic import BaseModel


class PutSecretRequest(BaseModel):
    value: str


class SecretKeysOut(BaseModel):
    keys: list[str]
