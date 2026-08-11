"""DO Spaces (S3-compatible) for uploaded files.

App Platform instances are ephemeral — anything written to local disk is gone
on the next restart or deploy. Uploaded contracts have to live somewhere
durable that isn't the instance itself, so the API writes to Spaces and the
Postgres job row only carries a reference key.
"""

import os
import uuid

import boto3

_client = None


def get_client():
    global _client
    if _client is None:
        _client = boto3.client(
            "s3",
            endpoint_url=os.environ["SPACES_ENDPOINT"],
            region_name=os.environ.get("SPACES_REGION", "nyc3"),
            aws_access_key_id=os.environ["SPACES_ACCESS_KEY"],
            aws_secret_access_key=os.environ["SPACES_SECRET_KEY"],
        )
    return _client


def bucket_name() -> str:
    return os.environ["SPACES_BUCKET"]


def upload(fileobj, original_filename: str) -> str:
    key = f"uploads/{uuid.uuid4()}-{original_filename}"
    get_client().upload_fileobj(fileobj, bucket_name(), key)
    return key


def exists(key: str) -> bool:
    try:
        get_client().head_object(Bucket=bucket_name(), Key=key)
        return True
    except Exception:
        return False
