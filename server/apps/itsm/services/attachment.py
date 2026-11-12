import re
from datetime import timedelta
from uuid import uuid4

from django.conf import settings
from minio import Minio

BUCKET = "itsm-private"


class AttachmentError(Exception):
    pass


def presign_upload(filename: str) -> dict:
    """给 ITSM 私有桶签发 15 分钟的 PUT 地址。凭据只从环境读取。"""
    if not settings.MINIO_ACCESS_KEY or not settings.MINIO_SECRET_KEY:
        raise AttachmentError("对象存储未配置")
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", filename or "file") or "file"
    object_name = f"attachments/{uuid4().hex}/{safe_name}"
    client = Minio(
        settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=settings.MINIO_USE_HTTPS,
    )
    url = client.presigned_put_object(BUCKET, object_name, expires=timedelta(minutes=15))
    return {"url": url, "object_name": object_name, "method": "PUT"}
