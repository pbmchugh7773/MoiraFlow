from moiraflow_worker.tls import (
    CLIENT_CERT_ENV,
    CLIENT_KEY_ENV,
    SERVER_CA_ENV,
    SERVER_NAME_ENV,
    build_tls_config,
)

_PEM = "-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----\n"
_KEY = "-----BEGIN PRIVATE KEY-----\nMIIE\n-----END PRIVATE KEY-----\n"


def test_no_material_returns_none():
    # Inert until certs are wired in -> dev connects plaintext.
    assert build_tls_config({}) is None


def test_inline_pem_material_is_used_verbatim():
    cfg = build_tls_config({SERVER_CA_ENV: _PEM, CLIENT_CERT_ENV: _PEM, CLIENT_KEY_ENV: _KEY})
    assert cfg is not None
    assert cfg.server_root_ca_cert == _PEM.encode()
    assert cfg.client_cert == _PEM.encode()
    assert cfg.client_private_key == _KEY.encode()


def test_file_path_material_is_read(tmp_path):
    ca_file = tmp_path / "ca.pem"
    ca_file.write_text(_PEM)
    cfg = build_tls_config({SERVER_CA_ENV: str(ca_file), CLIENT_CERT_ENV: _PEM})
    assert cfg is not None
    assert cfg.server_root_ca_cert == _PEM.encode()


def test_server_name_sets_domain():
    cfg = build_tls_config({CLIENT_CERT_ENV: _PEM, SERVER_NAME_ENV: "temporal.internal"})
    assert cfg is not None
    assert cfg.domain == "temporal.internal"


def test_partial_material_still_builds_config():
    # Only a CA (e.g. server-auth only) is enough to opt into TLS.
    cfg = build_tls_config({SERVER_CA_ENV: _PEM})
    assert cfg is not None
    assert cfg.client_cert is None
