"""Temporal payload encryption codec (ADR-0016).

Must match moiraflow_worker.encryption: same Fernet derivation (SHA-256 of the
master key) so the API, server worker and local agent exchange encrypted payloads.
Keeps secrets/context out of Temporal's history in cleartext.
"""

from __future__ import annotations

import base64
import dataclasses
import hashlib
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


def data_converter(master_key: str) -> DataConverter:
    return dataclasses.replace(default(), payload_codec=EncryptionCodec(master_key))
