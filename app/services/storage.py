import re
import uuid
from pathlib import Path

import boto3  # type: ignore[import-untyped]
from fastapi import HTTPException

from app.core.config import settings
from app.schemas.api import UploadPresignRequest, UploadPresignResponse


def public_media_url(storage_key: str | None, remote_url: str | None) -> str | None:
    if remote_url:
        return remote_url
    if storage_key and settings.media_public_base_url:
        return f"{settings.media_public_base_url.rstrip('/')}/{storage_key.lstrip('/')}"
    return None


def create_upload_presign(payload: UploadPresignRequest) -> UploadPresignResponse:
    if not settings.storage_configured:
        raise HTTPException(status_code=503, detail="Object storage is not configured")

    suffix = Path(payload.filename).suffix.lower()
    allowed_suffixes = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
    if suffix not in allowed_suffixes:
        raise HTTPException(status_code=422, detail="Unsupported image filename extension")

    safe_stem = re.sub(r"[^a-zA-Z0-9_-]+", "-", Path(payload.filename).stem).strip("-")
    safe_stem = safe_stem[:80] or "image"
    storage_key = f"media/{payload.kind}/{uuid.uuid4().hex}-{safe_stem}{suffix}"

    client = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key,
        region_name=settings.s3_region,
    )
    upload_url = client.generate_presigned_url(
        "put_object",
        Params={
            "Bucket": settings.s3_bucket,
            "Key": storage_key,
            "ContentType": payload.content_type,
        },
        ExpiresIn=900,
    )
    return UploadPresignResponse(
        upload_url=upload_url,
        storage_key=storage_key,
        public_url=public_media_url(storage_key, None),
        required_headers={"Content-Type": payload.content_type},
    )
