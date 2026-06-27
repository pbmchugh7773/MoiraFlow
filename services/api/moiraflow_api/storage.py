"""Presigned download URLs for artifacts stored in MinIO/S3.

Uses the browser-reachable public endpoint so the URL works from the user's browser
(the worker uploads via the internal cluster endpoint). Postgres holds only refs.
"""

from __future__ import annotations

from .config import get_settings


def presigned_url(object_key: str, bucket: str, expires: int = 3600) -> str:
    import boto3  # type: ignore[import-untyped]
    from botocore.config import Config  # type: ignore[import-untyped]

    settings = get_settings()
    client = boto3.client(
        "s3",
        endpoint_url=settings.s3_public_endpoint,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name="us-east-1",
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )
    url: str = client.generate_presigned_url(
        "get_object", Params={"Bucket": bucket, "Key": object_key}, ExpiresIn=expires
    )
    return url
