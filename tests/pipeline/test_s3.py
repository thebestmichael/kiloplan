"""The S3 upload, run against a simulated bucket so no AWS account is needed."""

import boto3
import pytest
from moto import mock_aws

from kiloplan.pipeline.s3 import bucket_name, upload_lake

BUCKET = "test-lake"


@pytest.fixture(autouse=True)
def aws_env(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-2")


@mock_aws
def test_uploads_each_parquet_file_under_the_prefix(tmp_path):
    (tmp_path / "weeks.parquet").write_bytes(b"one")
    (tmp_path / "foods.parquet").write_bytes(b"two")
    (tmp_path / "notes.txt").write_bytes(b"not parquet")
    client = boto3.client("s3")
    client.create_bucket(
        Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": "us-east-2"}
    )

    keys = upload_lake(tmp_path, BUCKET)

    assert keys == ["raw/foods.parquet", "raw/weeks.parquet"]
    stored = [o["Key"] for o in client.list_objects_v2(Bucket=BUCKET)["Contents"]]
    assert sorted(stored) == keys
    assert client.get_object(Bucket=BUCKET, Key="raw/weeks.parquet")["Body"].read() == b"one"


def test_off_without_a_bucket(monkeypatch):
    monkeypatch.delenv("KILOPLAN_S3_BUCKET", raising=False)
    assert bucket_name() is None
    monkeypatch.setenv("KILOPLAN_S3_BUCKET", "")
    assert bucket_name() is None
    monkeypatch.setenv("KILOPLAN_S3_BUCKET", BUCKET)
    assert bucket_name() == BUCKET
