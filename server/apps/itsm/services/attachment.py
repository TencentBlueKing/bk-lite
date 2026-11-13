import re
from datetime import timedelta
from urllib.parse import quote
from uuid import uuid4

from django.conf import settings
from django.core import signing
from django.db import transaction
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
    client = storage_client()
    url = client.presigned_put_object(BUCKET, object_name, expires=timedelta(minutes=15))
    return {"url": url, "object_name": object_name, "method": "PUT"}


def storage_client():
    return Minio(
        settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=settings.MINIO_USE_HTTPS,
    )


def download_url(item):
    return storage_client().presigned_get_object(
        BUCKET,
        item.object_name,
        expires=timedelta(minutes=5),
        response_headers={
            "response-content-disposition": "attachment; filename*=UTF-8''" + quote(item.name),
            "response-content-type": "application/octet-stream",
        },
    )


def upload_receipt(signed, ticket, username, name):
    return signing.dumps({"object_name": signed["object_name"], "ticket_id": ticket.id, "username": username, "name": name}, salt="itsm-upload")


@transaction.atomic
def register_upload(ticket, username, payload):
    from apps.itsm.models import Ticket, TicketAttachment

    try:
        receipt = signing.loads(payload.get("receipt", ""), salt="itsm-upload", max_age=3600)
    except signing.BadSignature as exc:
        raise PermissionError() from exc
    if receipt["ticket_id"] != ticket.id or receipt["username"] != username:
        raise PermissionError()
    stat = storage_client().stat_object(BUCKET, receipt["object_name"])
    if stat.size > 20 * 1024 * 1024:
        raise ValueError("附件不得超过 20 MB")
    Ticket.objects.select_for_update().get(pk=ticket.pk)
    item, _ = TicketAttachment.objects.get_or_create(
        ticket=ticket,
        object_name=receipt["object_name"],
        defaults={"name": receipt["name"], "size": stat.size, "created_by": username, "updated_by": username},
    )
    return item
