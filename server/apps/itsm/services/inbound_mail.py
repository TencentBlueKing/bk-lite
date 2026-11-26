"""按收件邮箱路由，保留稳定的建单标识以便轮询恢复。"""

import hashlib
from datetime import timedelta
from email import message_from_bytes
from email.policy import default
from email.utils import getaddresses

from django.db.models import F, Q
from django.db.models.functions import Lower
from django.utils import timezone

from apps.itsm.models import EmailRule, Service
from apps.itsm.models.integration import EmailReceipt


def ingest_email(path, service_factory):
    raw = path.read_bytes()
    message = message_from_bytes(raw, policy=default)
    # 可信投递器提供的实际收件地址优先于可见的 To/Cc。
    destinations = message.get_all("Delivered-To") or message.get_all("X-Original-To")
    addresses = getaddresses(destinations or (message.get_all("To", []) + message.get_all("Cc", [])))
    mailboxes = {address.strip().lower() for _, address in addresses if address}
    rules = list(EmailRule.objects.filter(is_enabled=True).annotate(address=Lower("mailbox")).filter(address__in=mailboxes).order_by("pk")[:2])
    if len(rules) != 1:
        return "unrouted"
    rule = rules[0]
    service = (
        Service.objects.select_related("workflow__current_version")
        .filter(
            pk=rule.service_id,
            domain=rule.domain,
            is_enabled=True,
            visibility="all",
            workflow__domain=rule.domain,
            workflow__is_enabled=True,
            workflow__current_version__is_published=True,
            workflow__current_version__domain=rule.domain,
            workflow__current_version__workflow_id=F("workflow_id"),
        )
        .first()
    )
    if service is None:
        return "unrouted"
    message_id = str(message.get("Message-ID") or "").strip()
    key = hashlib.sha256(message_id.encode() if message_id else raw).hexdigest()
    receipt, _ = EmailReceipt.objects.get_or_create(
        domain=rule.domain,
        mailbox=rule.address,
        message_key=key,
        defaults={"service": service, "version": service.workflow.current_version, "title": str(message.get("subject") or "邮件工单")[:200]},
    )
    if receipt.status == "done":
        return "duplicate"
    if receipt.service_id != service.pk:
        return "unrouted"
    now = timezone.now()
    # 两个轮询重叠时只允许一个发送。同一邮件故障恢复沿用创建请求键。
    claimed = EmailReceipt.objects.filter(pk=receipt.pk).filter(Q(status="pending") | Q(status="running", claimed_at__lt=now - timedelta(minutes=5)))
    if not claimed.update(status="running", claimed_at=now):
        return "processing"
    ticket = service_factory().create(receipt.version, {"title": receipt.title}, "mail", service=service, creation_key=f"email-{receipt.pk}")
    recorded = EmailReceipt.objects.filter(pk=receipt.pk, status="running", claimed_at=now).update(ticket=ticket, status="done", claimed_at=None)
    return "created" if recorded else "processing"
