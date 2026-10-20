"""Uploads the exported Parquet files to S3.

Off unless KILOPLAN_S3_BUCKET is set. Credentials come from the standard AWS
environment variables (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION), which
live in .env and are never committed.
"""

import os
from pathlib import Path

import boto3

DEFAULT_PREFIX = "raw"


def bucket_name() -> str | None:
    return os.environ.get("KILOPLAN_S3_BUCKET") or None


def upload_lake(source: Path, bucket: str, prefix: str = DEFAULT_PREFIX) -> list[str]:
    """Upload every Parquet file in `source` to `s3://bucket/prefix/`. Returns the keys written."""
    client = boto3.client("s3")
    keys = []
    for path in sorted(source.glob("*.parquet")):
        key = f"{prefix}/{path.name}"
        client.upload_file(str(path), bucket, key)
        keys.append(key)
    return keys
