import email
import os
from email.policy import default as email_policy
from pathlib import Path

from celery import shared_task
from django.utils import timezone

from apps.itsm.models import EmailRule, TicketSLARecord
from apps.itsm.models.extend import ScheduledTask
from apps.itsm.services.notify.service import deliver_with_retry


@shared_task(bind=True, max_retries=3)
def send_notify(self, event: str, variables: dict, receivers: list[str], event_key: str = ""):
    """异步发送通知。调用方未启动 Celery 时也可直接执行本函数完成三次重试。"""
    try:
        return deliver_with_retry(event, variables, receivers, event_key)
    except Exception as exc:
        raise self.retry(exc=exc, countdown=2)


@shared_task
def sla_tick():
    """把已过截止且未暂停、未完成的 SLA 标为超时。"""
    now = timezone.now()
    updated = TicketSLARecord.objects.filter(finished_at__isnull=True, paused_at__isnull=True, due_at__lt=now, breached=False).update(breached=True)
    return {"breached": updated}


def _ingest_eml(path: Path) -> bool:
    from apps.itsm.models import Service
    from apps.itsm.views.tickets import _service

    rule = EmailRule.objects.filter(is_enabled=True).exclude(service_id=None).first()
    if rule is None:
        return False
    service = Service.objects.select_related("workflow__current_version").filter(id=rule.service_id).first()
    if service is None or service.workflow.current_version_id is None:
        return False
    message = email.message_from_bytes(path.read_bytes(), policy=email_policy)
    subject = str(message.get("subject") or "邮件工单")
    _service().create(service.workflow.current_version, {"title": subject[:200]}, "mail", is_test=True)
    return True


@shared_task
def email_poll():
    """读取 ITSM_MAIL_DIR 里的 eml。没有目录时不创建工单。"""
    mail_dir = os.environ.get("ITSM_MAIL_DIR", "")
    if not mail_dir:
        return {"checked": EmailRule.objects.filter(is_enabled=True).count(), "created": 0}
    root = Path(mail_dir)
    if not root.is_dir():
        return {"checked": 0, "created": 0}
    created = 0
    for path in root.glob("*.eml"):
        if _ingest_eml(path):
            created += 1
            path.rename(path.with_suffix(".eml.done"))
    return {"checked": created, "created": created}


@shared_task
def scheduled_noop(schedule_id: int = 0):
    import json

    item = ScheduledTask.objects.filter(id=schedule_id, is_enabled=True).first()
    if item is None:
        return {"schedule_id": schedule_id, "ran": False}
    try:
        config = json.loads(item.action)
    except (TypeError, ValueError):
        config = {}
    if isinstance(config, dict) and config.get("notify") and item.created_by:
        try:
            deliver_with_retry("schedule", {"title": item.name, "content": item.name}, [item.created_by], f"schedule-{item.id}")
        except Exception as exc:
            from apps.core.logger import itsm_logger as logger

            logger.warning("定时任务通知失败 schedule_id=%s error_type=%s", schedule_id, type(exc).__name__)
            return {"schedule_id": schedule_id, "ran": True, "notify": "failed"}
    return {"schedule_id": schedule_id, "name": item.name, "ran": True}


@shared_task
def auto_tick():
    """领取 Flowable itsm.auto 外部作业并记一条执行。"""
    from django.conf import settings

    from apps.itsm.flowable.client import FlowableClient, FlowableError

    if not settings.FLOWABLE_PASSWORD:
        return {"acquired": 0}
    client = FlowableClient(settings.FLOWABLE_URL, settings.FLOWABLE_USER, settings.FLOWABLE_PASSWORD)
    done = 0
    for topic, kind in (("itsm.auto", "auto"), ("itsm.notify", "notify")):
        try:
            jobs = client.acquire_jobs(topic)
        except FlowableError:
            continue
        for job in jobs:
            from apps.itsm.services.external_jobs import process_job

            if process_job(client, job):
                done += 1
    from apps.itsm.services.external_jobs import reconcile_tickets

    reconciled = reconcile_tickets(client)
    return {"acquired": done, "reconciled": reconciled}
