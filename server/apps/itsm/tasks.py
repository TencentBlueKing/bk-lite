import email
import os
from email.policy import default as email_policy
from pathlib import Path

from celery import shared_task

from apps.itsm.models import EmailRule
from apps.itsm.services.notify.service import deliver_with_retry


@shared_task(bind=True, max_retries=3)
def send_notify(self, event: str, variables: dict, receivers: list[str], event_key: str = "", domain: str = ""):
    """异步发送通知。调用方未启动 Celery 时也可直接执行本函数完成三次重试。"""
    try:
        return deliver_with_retry(event, variables, receivers, event_key, domain=domain)
    except Exception as exc:
        raise self.retry(exc=exc, countdown=2)


@shared_task
def sla_tick():
    from apps.itsm.services.sla_notices import scan

    return scan()


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
def schedule_tick():
    from types import SimpleNamespace

    from django.conf import settings

    from apps.itsm.flowable.client import FlowableClient
    from apps.itsm.services.integrations import live_identity
    from apps.itsm.services.schedules import run_due, target_workflow
    from apps.itsm.services.service_access import check_service_request
    from apps.itsm.services.ticket.service import TicketService

    def service_for(item, run, config):
        identity = live_identity(item, actor=run.created_by, permission="ticket-Add")
        user = SimpleNamespace(username=identity.user, domain=identity.domain, is_superuser=identity.is_superuser)
        check_service_request(SimpleNamespace(user=user), target_workflow(item, config).current_version)
        client = FlowableClient(settings.FLOWABLE_URL, settings.FLOWABLE_USER, settings.FLOWABLE_PASSWORD) if settings.FLOWABLE_PASSWORD else None
        return TicketService(client, identity=identity)

    return {"runs": run_due(service_for)}


@shared_task
def auto_tick():
    """领取 Flowable itsm.auto 外部作业并记一条执行。"""
    from django.conf import settings

    from apps.itsm.flowable.client import FlowableClient, FlowableError
    from apps.itsm.services.todo_sync import drain_deliveries

    drain_deliveries()
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


@shared_task(ignore_result=True)
def trigger_notice_tick():
    from apps.itsm.services.trigger_delivery import drain_trigger_notices

    drain_trigger_notices()


@shared_task(ignore_result=True, soft_time_limit=180, time_limit=210)
def generate_ticket_export(task_id):
    from apps.itsm.services.ticket.export_jobs import generate

    generate(task_id)


@shared_task(ignore_result=True)
def knowledge_attachment_cleanup():
    from apps.itsm.services.knowledge_attachments import drain_attachment_cleanup

    drain_attachment_cleanup()
