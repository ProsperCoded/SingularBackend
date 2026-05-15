from __future__ import annotations

import base64
from functools import lru_cache

import boto3
from botocore.exceptions import ClientError

from core.config import settings


def build_qr_object_key(product_id: str) -> str:
    return f"products/{product_id}/qr.png"


def _build_endpoint_url() -> str | None:
    if settings.DO_SPACES_ENDPOINT:
        return settings.DO_SPACES_ENDPOINT
    return f"https://{settings.DO_SPACES_REGION}.digitaloceanspaces.com"


@lru_cache(maxsize=1)
def get_spaces_client():
    return boto3.client(
        "s3",
        region_name=settings.DO_SPACES_REGION,
        endpoint_url=_build_endpoint_url(),
        aws_access_key_id=settings.DO_SPACES_KEY,
        aws_secret_access_key=settings.DO_SPACES_SECRET,
    )


def upload_qr_png(product_id: str, png_bytes: bytes) -> str:
    key = build_qr_object_key(product_id)
    get_spaces_client().put_object(
        Bucket=settings.DO_SPACES_BUCKET,
        Key=key,
        Body=png_bytes,
        ContentType="image/png",
    )
    return key


def download_qr_png(product_id: str) -> bytes | None:
    key = build_qr_object_key(product_id)
    try:
        response = get_spaces_client().get_object(
            Bucket=settings.DO_SPACES_BUCKET,
            Key=key,
        )
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code")
        if error_code in {"NoSuchKey", "404", "NotFound"}:
            return None
        raise

    body = response["Body"].read()
    if isinstance(body, bytes):
        return body
    return bytes(body)


def encode_png_bytes(png_bytes: bytes) -> str:
    return base64.b64encode(png_bytes).decode("ascii")
