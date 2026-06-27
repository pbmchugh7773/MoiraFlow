"""Upload job artifacts to MinIO/S3 (docs 03 §3.8 / 05 §5).

The worker uploads declared files to object storage and reports references; Postgres
only ever stores the reference (never the binary). The S3 client is injectable so
the upload logic is testable without a real MinIO.
"""

from __future__ import annotations

import mimetypes
import os
from pathlib import Path
from typing import Any


def _client() -> Any:
    import boto3  # type: ignore[import-untyped]
    from botocore.config import Config  # type: ignore[import-untyped]

    return boto3.client(
        "s3",
        endpoint_url=os.environ.get("S3_ENDPOINT", "http://minio:9000"),
        aws_access_key_id=os.environ.get("S3_ACCESS_KEY", "minioadmin"),
        aws_secret_access_key=os.environ.get("S3_SECRET_KEY", "minioadmin"),
        region_name="us-east-1",
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def _ensure_bucket(client: Any, bucket: str) -> None:
    try:
        client.head_bucket(Bucket=bucket)
    except Exception:
        client.create_bucket(Bucket=bucket)


def upload_artifacts(
    paths: list[str],
    key_prefix: str,
    *,
    client: Any | None = None,
    bucket: str | None = None,
) -> list[dict[str, Any]]:
    """Upload each existing file; return [{name, bucket, object_key, size_bytes,
    content_type}]. Missing files are skipped (not every run produces every file)."""
    if not paths:
        return []
    bucket = bucket or os.environ.get("S3_BUCKET", "moiraflow-artifacts")
    client = client or _client()
    _ensure_bucket(client, bucket)
    refs: list[dict[str, Any]] = []
    for raw in paths:
        path = Path(raw)
        if not path.is_file():
            continue
        object_key = f"{key_prefix}/{path.name}"
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        client.upload_file(str(path), bucket, object_key, ExtraArgs={"ContentType": content_type})
        refs.append(
            {
                "name": path.name,
                "bucket": bucket,
                "object_key": object_key,
                "size_bytes": path.stat().st_size,
                "content_type": content_type,
            }
        )
    return refs
