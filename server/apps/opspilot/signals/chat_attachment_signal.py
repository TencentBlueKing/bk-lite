"""删除对话附件记录时同步删除 MinIO 对象。会话级联删除同样会触发。"""

from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.models import ChatAttachment


@receiver(post_delete, sender=ChatAttachment, dispatch_uid="chat_attachment_delete_minio_file")
def delete_chat_attachment_file_on_delete(sender, instance, **kwargs):
    file_field = instance.file
    file_name = getattr(file_field, "name", "")
    attachment_id = instance.pk
    storage = file_field.storage if file_name else None

    def cleanup():
        if not file_name or storage is None:
            return
        try:
            storage.delete(file_name)
        except Exception as exc:
            logger.exception(
                "chat_attachment file delete failed: attachment_id=%s failed_stage=%s error_type=%s",
                attachment_id,
                "delete_object",
                type(exc).__name__,
            )

    transaction.on_commit(cleanup, using=kwargs.get("using"))
