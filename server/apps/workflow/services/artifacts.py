from __future__ import annotations

from django.db import connection, transaction
from django.utils import timezone

from apps.core.logger import workflow_logger as logger
from apps.workflow.models import ExecutionArtifact
from apps.workflow.services.object_store import WorkflowObjectStore


def cleanup_expired_artifacts(*, store=None, batch_size: int = 100) -> dict[str, int]:
    object_store = store or WorkflowObjectStore()
    now = timezone.now()
    limit = max(1, min(batch_size, 500))
    with transaction.atomic():
        queryset = ExecutionArtifact.objects.filter(deleted_at__isnull=True, expires_at__lte=now).order_by("expires_at")
        if connection.features.has_select_for_update:
            if getattr(connection.features, "has_select_for_update_skip_locked", False):
                queryset = queryset.select_for_update(skip_locked=True)
            else:
                queryset = queryset.select_for_update()
        records = list(queryset[:limit])
        deleted = failed = 0
        for artifact in records:
            try:
                object_store.delete(artifact.object_key)
            except Exception as error:
                failed += 1
                logger.warning(
                    "event=workflow_artifact_cleanup_failed artifact_id=%s error_type=%s",
                    artifact.id,
                    type(error).__name__,
                )
                continue
            artifact.deleted_at = timezone.now()
            artifact.save(update_fields=("deleted_at", "updated_at"))
            deleted += 1
    return {"selected": len(records), "deleted": deleted, "failed": failed}


class NotificationFileSizeError(ValueError):
    """已登记的附件超出本次原生文件传输的大小范围。"""


def read_notification_artifact(*, artifact_id, execution_id, team, min_bytes, max_bytes):
    artifact = ExecutionArtifact.objects.get(
        pk=artifact_id, execution_id=execution_id, team=[team], deleted_at__isnull=True, expires_at__gt=timezone.now()
    )
    if not min_bytes <= artifact.size <= max_bytes:
        raise NotificationFileSizeError("文件大小超过渠道限制")
    content, _, _ = WorkflowObjectStore().get(artifact.object_key, max_bytes=max_bytes)
    if len(content) != artifact.size:
        raise ValueError("附件内容与登记大小不一致")
    return artifact.filename, content
