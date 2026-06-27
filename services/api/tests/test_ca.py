import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import NameOID

from moiraflow_api.ca import CertificateAuthority, InvalidCsrError, fingerprint


def make_csr(cn: str = "edge-1") -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
        .sign(key, hashes.SHA256())
    )
    return csr.public_bytes(serialization.Encoding.PEM).decode()


def test_sign_csr_issues_cert_chained_to_ca():
    ca = CertificateAuthority.generate()
    cert_pem = ca.sign_csr(make_csr("edge-7"))
    cert = x509.load_pem_x509_certificate(cert_pem.encode())

    # issued by our CA, for the requested subject
    assert cert.issuer.rfc4514_string() == "CN=MoiraFlow Agent CA"
    assert cert.subject.rfc4514_string() == "CN=edge-7"

    # signature actually verifies against the CA public key
    ca_pub = x509.load_pem_x509_certificate(ca.cert_pem.encode()).public_key()
    ca_pub.verify(  # raises if invalid
        cert.signature,
        cert.tbs_certificate_bytes,
        padding.PKCS1v15(),
        cert.signature_hash_algorithm,
    )


def test_fingerprint_is_stable_64_hex():
    ca = CertificateAuthority.generate()
    cert_pem = ca.sign_csr(make_csr())
    fp = fingerprint(cert_pem)
    assert len(fp) == 64 and all(c in "0123456789abcdef" for c in fp)
    assert fingerprint(cert_pem) == fp  # stable


def test_malformed_csr_raises_invalid():
    ca = CertificateAuthority.generate()
    with pytest.raises(InvalidCsrError):
        ca.sign_csr(
            "-----BEGIN CERTIFICATE REQUEST-----\nnonsense\n-----END CERTIFICATE REQUEST-----"
        )


def test_load_from_env_roundtrips(monkeypatch):
    ca = CertificateAuthority.generate()
    key_pem = ca._key.private_bytes(  # noqa: SLF001 - test introspection
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    monkeypatch.setenv("MOIRAFLOW_CA_CERT_PEM", ca.cert_pem)
    monkeypatch.setenv("MOIRAFLOW_CA_KEY_PEM", key_pem)
    loaded = CertificateAuthority.load()
    assert loaded.cert_pem == ca.cert_pem
