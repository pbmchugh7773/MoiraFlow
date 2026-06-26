"""Temporal payload encryption (ADR-0016).

A PayloadCodec that encrypts every payload before it reaches Temporal, so secrets
and context are not stored in cleartext in Temporal's history. Uses the SAME Fernet
derivation as secret storage (keyed by SECRETS_MASTER_KEY) — the API, server worker
and (local) agent must share the key to exchange payloads. Decode passes
non-encrypted payloads through, so old/plaintext histories still replay.

NOTE: the *remote* agent (Hito 5) will use per-agent envelope encryption (ADR-0013)
instead of this shared key; this global codec covers server-side + the local agent.
"""

from __future__ import annotations

import base64
import dataclasses
import hashlib
import os
from collections.abc import Sequence

from cryptography.fernet import Fernet
from temporalio.api.common.v1 import Payload
from temporalio.converter import DataConverter, PayloadCodec, default

_ENCODING = b"binary/encrypted"


def _fernet(master_key: str) -> Fernet:
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(master_key.encode()).digest()))


class EncryptionCodec(PayloadCodec):
    def __init__(self, master_key: str) -> None:
        self._fernet = _fernet(master_key)

    async def encode(self, payloads: Sequence[Payload]) -> list[Payload]:
        return [
            Payload(
                metadata={"encoding": _ENCODING},
                data=self._fernet.encrypt(p.SerializeToString()),
            )
            for p in payloads
        ]

    async def decode(self, payloads: Sequence[Payload]) -> list[Payload]:
        result: list[Payload] = []
        for payload in payloads:
            if payload.metadata.get("encoding") != _ENCODING:
                result.append(payload)
                continue
            inner = Payload()
            inner.ParseFromString(self._fernet.decrypt(payload.data))
            result.append(inner)
        return result


def data_converter(master_key: str | None = None) -> DataConverter:
    key = (
        master_key
        if master_key is not None
        else os.getenv("SECRETS_MASTER_KEY", "dev-insecure-master-key")
    )
    return dataclasses.replace(default(), payload_codec=EncryptionCodec(key))
