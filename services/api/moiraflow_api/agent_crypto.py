"""Per-agent envelope encryption (Hito 5, slice 3 — ADR-0013 / docs 05 §5).

A secret bound for an agent job is sealed to that agent's RSA public key: a random
Fernet data key encrypts the value, and the data key is wrapped with RSA-OAEP. The
agent unwraps the data key with its private key and decrypts in memory only — so a
stolen task can't leak secrets, and the agent never holds the secrets master key.

The format is shared verbatim with the worker/agent side (services/worker/
moiraflow_worker/agent_crypto.py); a committed fixture cross-checks compatibility.
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


def encrypt_for_agent(public_key_pem: str, plaintext: str) -> str:
    public_key = serialization.load_pem_public_key(public_key_pem.encode())
    data_key = Fernet.generate_key()
    token = Fernet(data_key).encrypt(plaintext.encode())
    wrapped = public_key.encrypt(data_key, _OAEP)  # type: ignore[union-attr]
    envelope = {"k": base64.b64encode(wrapped).decode(), "v": token.decode()}
    return base64.b64encode(json.dumps(envelope).encode()).decode()


def decrypt_for_agent(private_key_pem: str, envelope: str) -> str:
    obj = json.loads(base64.b64decode(envelope))
    private_key = serialization.load_pem_private_key(private_key_pem.encode(), password=None)
    data_key = private_key.decrypt(base64.b64decode(obj["k"]), _OAEP)  # type: ignore[union-attr]
    return Fernet(data_key).decrypt(obj["v"].encode()).decode()
