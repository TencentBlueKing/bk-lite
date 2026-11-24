from datetime import timedelta
from functools import partial

from django.db import transaction
from django.utils import timezone

from apps.core.logger import itsm_logger as logger
from apps.core.logger import safe_exception_info
from apps.itsm.models.extend import KnowledgeAttachmentCleanup
from apps.itsm.services.attachment import BUCKET, storage_client

RETRY_DELAY = timedelta(minutes=5)


def reserve_upload(object_name):
    return KnowledgeAttachmentCleanup.objects.create(object_name=object_name, next_attempt_at=timezone.now() + RETRY_DELAY)


def queue_attachment_cleanup(object_names):
    now = timezone.now()
    records = KnowledgeAttachmentCleanup.objects.bulk_create(
        [KnowledgeAttachmentCleanup(object_name=name, next_attempt_at=now) for name in object_names]
    )
    names = [item.object_name for item in records[:20]]
    transaction.on_commit(partial(drain_attachment_cleanup, object_names=names), robust=True)


def cleanup_attachment(object_name, *, force=False):
    with transaction.atomic():
        record = KnowledgeAttachmentCleanup.objects.select_for_update().filter(object_name=object_name).first()
        if record is None or (not force and record.next_attempt_at > timezone.now()):
            return False
        try:
            storage_client().remove_object(BUCKET, record.object_name)
        except Exception as error:
            logger.warning(
                "event=itsm_knowledge_attachment_cleanup_failed cleanup_id=%s failed_stage=%s error_type=%s",
                record.pk,
                "remove_object",
                type(error).__name__,
                exc_info=safe_exception_info(error),
            )
            record.next_attempt_at = timezone.now() + RETRY_DELAY
            record.save(update_fields=["next_attempt_at"])
            return False
        record.delete()
        return True


def drain_attachment_cleanup(*, object_names=None, limit=20):
    pending = KnowledgeAttachmentCleanup.objects.filter(next_attempt_at__lte=timezone.now())
    if object_names is not None:
        pending = pending.filter(object_name__in=object_names)
    names = list(pending.order_by("next_attempt_at", "pk").values_list("object_name", flat=True)[:limit])
    return {"removed": sum(cleanup_attachment(name) for name in names)}
