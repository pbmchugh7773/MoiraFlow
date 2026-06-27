"""Agent-side decryption for per-agent envelope encryption (Hito 5, slice 3).

The agent unwraps the RSA-OAEP-wrapped Fernet data key with its private key and
decrypts the secret in memory only — never on disk, never logged. Format matches
services/api/moiraflow_api/agent_crypto.py verbatim (cross-checked by a fixture).
"""

from __future__ import annotations

import base64
import json

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

_OAEP = padding.OAEP(
    mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None
)


def decrypt_for_agent(private_key_pem: str, envelope: str) -> str:
    obj = json.loads(base64.b64decode(envelope))
    private_key = serialization.load_pem_private_key(private_key_pem.encode(), password=None)
    data_key = private_key.decrypt(base64.b64decode(obj["k"]), _OAEP)  # type: ignore[union-attr]
    return Fernet(data_key).decrypt(obj["v"].encode()).decode()
