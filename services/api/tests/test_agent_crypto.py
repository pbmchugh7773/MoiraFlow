import base64
import json

import pytest
from cryptography.fernet import InvalidToken
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from moiraflow_api.agent_crypto import decrypt_for_agent, encrypt_for_agent


def _keypair():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    pub = (
        key.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )
    return priv, pub


def test_roundtrip():
    priv, pub = _keypair()
    env = encrypt_for_agent(pub, "super-secret-dsn")
    assert env != "super-secret-dsn"  # not plaintext
    assert decrypt_for_agent(priv, env) == "super-secret-dsn"


def test_wrong_private_key_cannot_decrypt():
    _, pub = _keypair()
    other_priv, _ = _keypair()
    env = encrypt_for_agent(pub, "x")
    with pytest.raises(ValueError):  # OAEP unwrap fails
        decrypt_for_agent(other_priv, env)


def test_tampered_ciphertext_is_rejected():
    priv, pub = _keypair()
    env = encrypt_for_agent(pub, "x")
    obj = json.loads(base64.b64decode(env))
    obj["v"] = obj["v"][:-4] + "AAAA"  # corrupt the Fernet token
    tampered = base64.b64encode(json.dumps(obj).encode()).decode()
    with pytest.raises(InvalidToken):
        decrypt_for_agent(priv, tampered)
