"""mTLS config wiring for the Temporal client (docs 05 §5).

Ties together: the internal CA issues a client cert -> the cert becomes the TLS
client material -> its fingerprint is the identity the revocation gate checks.
"""

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from moiraflow_api import temporal
from moiraflow_api.ca import CertificateAuthority, fingerprint
from moiraflow_api.config import Settings


def _csr(cn: str) -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
        .sign(key, hashes.SHA256())
    )
    return csr.public_bytes(serialization.Encoding.PEM).decode()


def _client_key_pem() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()


def test_build_tls_config_false_when_unconfigured(monkeypatch):
    monkeypatch.setattr(temporal, "get_settings", lambda: Settings())
    assert temporal.build_tls_config() is False


def test_build_tls_config_from_ca_issued_cert(monkeypatch):
    ca = CertificateAuthority.generate()
    cert_pem = ca.sign_csr(_csr("agent-7"))
    key_pem = _client_key_pem()
    monkeypatch.setattr(
        temporal,
        "get_settings",
        lambda: Settings(
            tls_server_ca=ca.cert_pem,
            tls_client_cert=cert_pem,
            tls_client_key=key_pem,
            tls_server_name="temporal.internal",
        ),
    )

    cfg = temporal.build_tls_config()

    assert cfg is not False
    assert cfg.server_root_ca_cert == ca.cert_pem.encode()
    assert cfg.client_cert == cert_pem.encode()
    assert cfg.client_private_key == key_pem.encode()
    assert cfg.domain == "temporal.internal"
    # the cert's fingerprint is the persisted identity the revocation gate enforces
    assert len(fingerprint(cert_pem)) == 64
