"""Move a file between a source and a destination for the `file_transfer` job.

Supported URI schemes:
- ``https://`` / ``http://``      download (source only)
- ``s3://bucket/key``             object storage (S3/MinIO)
- ``artifact://key``              the MoiraFlow artifacts bucket (writes become a
                                  downloadable execution artifact)
- ``sftp://[user@]host[:port]/path``   SFTP (credentials via ``secret://``)

The read/write transports are looked up by scheme from injectable registries, so the
orchestration is unit-testable without boto3/paramiko/network. The default transports
import their heavy dependency lazily.
"""

from __future__ import annotations

import io
import json
import os
from typing import Any, Callable
from urllib.parse import urlparse

# Cap the in-memory transfer so a huge file can't OOM the worker (streaming is a
# later refinement).
MAX_BYTES = 100 * 1024 * 1024  # 100 MB

# reader(parsed, creds) -> bytes
Reader = Callable[[dict[str, Any], dict[str, Any]], bytes]
# writer(parsed, data, creds, tenant_id, job_id) -> artifact ref dict | None
Writer = Callable[..., "dict[str, Any] | None"]


def parse_uri(uri: str) -> dict[str, Any]:
    """Break a transfer URI into its parts (scheme, host, port, bucket, key, path)."""
    u = urlparse(uri)
    scheme = u.scheme.lower()
    parsed: dict[str, Any] = {"scheme": scheme, "raw": uri}
    if scheme in ("http", "https"):
        return parsed
    if scheme == "s3":
        parsed["bucket"] = u.netloc
        parsed["key"] = u.path.lstrip("/")
    elif scheme == "artifact":
        # no bucket — the whole reference after artifact:// is the key
        parsed["key"] = (u.netloc + u.path).strip("/")
    elif scheme == "sftp":
        parsed["host"] = u.hostname
        parsed["port"] = u.port or 22
        parsed["user"] = u.username
        parsed["path"] = u.path
    else:
        raise ValueError(f"unsupported scheme: {scheme!r}")
    return parsed


def _artifacts_bucket() -> str:
    return os.environ.get("S3_BUCKET", "moiraflow-artifacts")


# ── default transports (heavy deps imported lazily) ──────────────────────────
def read_http(parsed: dict[str, Any], creds: dict[str, Any]) -> bytes:
    import httpx

    with httpx.Client(timeout=60) as client:
        response = client.get(parsed["raw"])
        response.raise_for_status()
        return response.content


def read_s3(parsed: dict[str, Any], creds: dict[str, Any]) -> bytes:
    from .storage import _client

    obj = _client().get_object(Bucket=parsed["bucket"], Key=parsed["key"])
    return bytes(obj["Body"].read())


def read_artifact(parsed: dict[str, Any], creds: dict[str, Any]) -> bytes:
    from .storage import _client

    obj = _client().get_object(Bucket=_artifacts_bucket(), Key=parsed["key"])
    return bytes(obj["Body"].read())


def write_s3(
    parsed: dict[str, Any], data: bytes, creds: dict[str, Any], **_: Any
) -> dict[str, Any] | None:
    from .storage import _client

    _client().put_object(Bucket=parsed["bucket"], Key=parsed["key"], Body=data)
    return None


def write_artifact(
    parsed: dict[str, Any],
    data: bytes,
    creds: dict[str, Any],
    *,
    tenant_id: str | None = None,
    job_id: str = "",
    **_: Any,
) -> dict[str, Any]:
    from .storage import _client, _ensure_bucket

    bucket = _artifacts_bucket()
    key = f"{tenant_id or 'default'}/{parsed['key']}"
    client = _client()
    _ensure_bucket(client, bucket)
    client.put_object(Bucket=bucket, Key=key, Body=data)
    return {
        "name": parsed["key"].rsplit("/", 1)[-1],
        "bucket": bucket,
        "object_key": key,
        "size_bytes": len(data),
        "content_type": None,
    }


def _parse_host_key(line: str) -> tuple[str, Any]:
    """Parse an OpenSSH public-key line (`ssh-rsa AAAA...`, from `ssh-keyscan`)."""
    import base64

    import paramiko

    parts = line.split()
    keytype, blob = parts[0], parts[1]
    classes = {
        "ssh-rsa": paramiko.RSAKey,
        "ssh-ed25519": paramiko.Ed25519Key,
        "ecdsa-sha2-nistp256": paramiko.ECDSAKey,
        "ecdsa-sha2-nistp384": paramiko.ECDSAKey,
        "ecdsa-sha2-nistp521": paramiko.ECDSAKey,
    }
    cls = classes.get(keytype)
    if cls is None:
        raise ValueError(f"unsupported host key type: {keytype!r}")
    return keytype, cls(data=base64.b64decode(blob))


def _configure_host_key(client: Any, host: str, creds: dict[str, Any]) -> None:
    """Pin the server's host key when `host_key` is supplied (reject any mismatch);
    otherwise trust on first use. Pin in production — `ssh-keyscan <host>` gives the key."""
    import paramiko

    if creds.get("host_key"):
        keytype, key = _parse_host_key(creds["host_key"])
        client.get_host_keys().add(host, keytype, key)
        client.set_missing_host_key_policy(paramiko.RejectPolicy())
    else:
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())


def _load_private_key(pem: str) -> Any:
    import paramiko

    for cls in (paramiko.RSAKey, paramiko.Ed25519Key, paramiko.ECDSAKey):
        try:
            return cls.from_private_key(io.StringIO(pem))
        except Exception:  # noqa: PERF203 - try each key type
            continue
    raise ValueError("unsupported private key")


def _sftp_client(parsed: dict[str, Any], creds: dict[str, Any]) -> Any:
    import paramiko

    client = paramiko.SSHClient()
    _configure_host_key(client, parsed["host"], creds)
    pkey = _load_private_key(creds["private_key"]) if creds.get("private_key") else None
    client.connect(
        parsed["host"],
        port=parsed["port"],
        username=creds.get("username") or parsed.get("user"),
        password=creds.get("password"),
        pkey=pkey,
        timeout=30,
    )
    return client


def read_sftp(parsed: dict[str, Any], creds: dict[str, Any]) -> bytes:
    client = _sftp_client(parsed, creds)
    try:
        buf = io.BytesIO()
        client.open_sftp().getfo(parsed["path"], buf)
        return buf.getvalue()
    finally:
        client.close()


def write_sftp(
    parsed: dict[str, Any], data: bytes, creds: dict[str, Any], **_: Any
) -> dict[str, Any] | None:
    client = _sftp_client(parsed, creds)
    try:
        client.open_sftp().putfo(io.BytesIO(data), parsed["path"])
        return None
    finally:
        client.close()


DEFAULT_READERS: dict[str, Reader] = {
    "http": read_http,
    "https": read_http,
    "s3": read_s3,
    "artifact": read_artifact,
    "sftp": read_sftp,
}
DEFAULT_WRITERS: dict[str, Writer] = {
    "s3": write_s3,
    "artifact": write_artifact,
    "sftp": write_sftp,
}


def parse_credentials(raw: Any) -> dict[str, Any]:
    """A resolved `secret://` value for SFTP — a JSON object, or empty if absent."""
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    return dict(json.loads(raw))


def transfer(
    source: str,
    destination: str,
    *,
    src_creds: dict[str, Any] | None = None,
    dst_creds: dict[str, Any] | None = None,
    tenant_id: str | None = None,
    job_id: str = "",
    readers: dict[str, Reader] | None = None,
    writers: dict[str, Writer] | None = None,
) -> dict[str, Any]:
    """Read `source` and write it to `destination`. Returns
    ``{"size": int, "ref": <artifact ref or None>}``."""
    readers = readers or DEFAULT_READERS
    writers = writers or DEFAULT_WRITERS
    src = parse_uri(source)
    dst = parse_uri(destination)
    if src["scheme"] not in readers:
        raise ValueError(f"cannot read from scheme {src['scheme']!r}")
    if dst["scheme"] not in writers:
        raise ValueError(f"cannot write to scheme {dst['scheme']!r}")

    data = readers[src["scheme"]](src, src_creds or {})
    if len(data) > MAX_BYTES:
        raise ValueError(f"file too large: {len(data)} bytes (max {MAX_BYTES})")
    ref = writers[dst["scheme"]](dst, data, dst_creds or {}, tenant_id=tenant_id, job_id=job_id)
    return {"size": len(data), "ref": ref}
