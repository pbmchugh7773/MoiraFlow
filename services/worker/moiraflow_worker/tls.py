"""Build a Temporal mTLS config from the environment (docs 05 §5).

The agent/worker authenticates to Temporal with a client certificate issued by the
internal CA, and verifies the server against that CA — so the transport is mutually
authenticated and a revoked/forged cert can't connect. `build_tls_config` returns
None when no TLS material is configured (plaintext dev against the local dev server,
which has no TLS), so this stays inert until certs are wired in.

Each material may be given inline as PEM (value starts with ``-----BEGIN``) or as a
path to a PEM file.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from temporalio.service import TLSConfig

SERVER_CA_ENV = "MOIRAFLOW_TLS_SERVER_CA"
CLIENT_CERT_ENV = "MOIRAFLOW_TLS_CLIENT_CERT"
CLIENT_KEY_ENV = "MOIRAFLOW_TLS_CLIENT_KEY"
SERVER_NAME_ENV = "MOIRAFLOW_TLS_SERVER_NAME"


def _material(value: str | None) -> bytes | None:
    """Resolve a PEM value: inline PEM text, or a path to a PEM file."""
    if not value:
        return None
    if value.lstrip().startswith("-----BEGIN"):
        return value.encode()
    return Path(value).read_bytes()


def build_tls_config(env: Mapping[str, str]) -> TLSConfig | None:
    """A TLSConfig for the agent↔Temporal connection, or None if not configured."""
    ca = _material(env.get(SERVER_CA_ENV))
    client_cert = _material(env.get(CLIENT_CERT_ENV))
    client_key = _material(env.get(CLIENT_KEY_ENV))
    if ca is None and client_cert is None and client_key is None:
        return None
    return TLSConfig(
        server_root_ca_cert=ca,
        client_cert=client_cert,
        client_private_key=client_key,
        domain=env.get(SERVER_NAME_ENV) or None,
    )
