"""对话附件解析与清理。解析走独立队列，不与 wiki 导入混排。"""

from celery import shared_task

from apps.opspilot.services.chat_attachment_service import cleanup_chat_attachments, parse_chat_attachment


@shared_task(
    name="apps.opspilot.tasks.parse_chat_attachment",
    queue="opspilot_chat_parse",
    soft_time_limit=120,
    time_limit=130,
)
def parse_chat_attachment_task(attachment_id: int):
    parse_chat_attachment(attachment_id)


@shared_task(
    name="apps.opspilot.tasks.cleanup_chat_attachments_task",
    queue="opspilot_maintenance",
)
def cleanup_chat_attachments_task():
    return cleanup_chat_attachments()
