import asyncio

from temporalio.api.common.v1 import Payload

from moiraflow_worker.encryption import EncryptionCodec


def _payload(data: bytes) -> Payload:
    return Payload(metadata={"encoding": b"json/plain"}, data=data)


def test_encode_then_decode_roundtrips():
    codec = EncryptionCodec("master-key")
    original = _payload(b'{"secret":"pg://u:pw@h/db"}')

    encoded = asyncio.run(codec.encode([original]))
    assert encoded[0].metadata["encoding"] == b"binary/encrypted"
    assert b"pg://" not in encoded[0].data  # ciphertext, not plaintext

    decoded = asyncio.run(codec.decode(encoded))
    assert decoded[0].data == original.data
    assert decoded[0].metadata["encoding"] == b"json/plain"


def test_decode_passes_through_unencrypted_payloads():
    codec = EncryptionCodec("master-key")
    plain = _payload(b"hello")
    decoded = asyncio.run(codec.decode([plain]))
    assert decoded[0].data == b"hello"


def test_wrong_key_cannot_decrypt():
    encoded = asyncio.run(EncryptionCodec("key-a").encode([_payload(b"x")]))
    with __import__("pytest").raises(Exception):
        asyncio.run(EncryptionCodec("key-b").decode(encoded))
