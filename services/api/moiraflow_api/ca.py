"""Internal certificate authority for agent identity (Hito 5, slice 2 — docs 05 §4.2).

A self-signed CA signs each agent's CSR at registration; the cert's SHA-256
fingerprint is persisted and later used to verify the agent at connection time
(slice 4). For a single API replica the CA is generated in-process; for multiple
replicas provide a shared CA via MOIRAFLOW_CA_CERT_PEM / MOIRAFLOW_CA_KEY_PEM so
certs issued by one replica verify against another's CA.
"""

from __future__ import annotations

import datetime
import os
from functools import lru_cache

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

_CA_CN = "MoiraFlow Agent CA"


class InvalidCsrError(Exception):
    pass


class CertificateAuthority:
    def __init__(self, cert: x509.Certificate, key: rsa.RSAPrivateKey) -> None:
        self._cert = cert
        self._key = key

    @classmethod
    def generate(cls) -> CertificateAuthority:
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, _CA_CN)])
        now = datetime.datetime.now(datetime.timezone.utc)
        cert = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(minutes=1))
            .not_valid_after(now + datetime.timedelta(days=3650))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .sign(key, hashes.SHA256())
        )
        return cls(cert, key)

    @classmethod
    def load(cls) -> CertificateAuthority:
        cert_pem = os.getenv("MOIRAFLOW_CA_CERT_PEM")
        key_pem = os.getenv("MOIRAFLOW_CA_KEY_PEM")
        if cert_pem and key_pem:
            cert = x509.load_pem_x509_certificate(cert_pem.encode())
            key = serialization.load_pem_private_key(key_pem.encode(), password=None)
            assert isinstance(key, rsa.RSAPrivateKey)
            return cls(cert, key)
        return cls.generate()

    @property
    def cert_pem(self) -> str:
        return self._cert.public_bytes(serialization.Encoding.PEM).decode()

    def sign_csr(self, csr_pem: str, valid_days: int = 90) -> str:
        try:
            csr = x509.load_pem_x509_csr(csr_pem.encode())
        except ValueError as exc:
            raise InvalidCsrError(f"malformed CSR: {exc}") from exc
        if not csr.is_signature_valid:
            raise InvalidCsrError("CSR signature is not valid")
        now = datetime.datetime.now(datetime.timezone.utc)
        cert = (
            x509.CertificateBuilder()
            .subject_name(csr.subject)
            .issuer_name(self._cert.subject)
            .public_key(csr.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(minutes=1))
            .not_valid_after(now + datetime.timedelta(days=valid_days))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .sign(self._key, hashes.SHA256())
        )
        return cert.public_bytes(serialization.Encoding.PEM).decode()


def fingerprint(cert_pem: str) -> str:
    """Stable SHA-256 fingerprint (hex) of a certificate — the agent's identity."""
    cert = x509.load_pem_x509_certificate(cert_pem.encode())
    return cert.fingerprint(hashes.SHA256()).hex()


@lru_cache(maxsize=1)
def get_certificate_authority() -> CertificateAuthority:
    return CertificateAuthority.load()
