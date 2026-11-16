"""待办投递队列：事务后快照、域隔离和接收端幂等。"""

import hashlib
import json

from django.db import transaction
from django.db.models import F

from apps.core.mixinx import EncryptMixin
from apps.core.utils.safe_requests import safe_request
from apps.itsm.models import Ticket, TicketTask
from apps.itsm.models.integration import Integration, TodoDelivery


def send_payload(item, payload):
    headers = {"Idempotency-Key": str(payload.get("event_id") or "")}
    if item.config.get("token"):
        token = EncryptMixin.get_cipher_suite().decrypt(item.config["token"].encode()).decode()
        headers["Authorization"] = f"Bearer {token}"
    response = safe_request("POST", item.config["url"], json=payload, headers=headers, timeout=5, allow_redirects=False, stream=True)
    try:
        if not 200 <= response.status_code < 300:
            raise ValueError(f"接收方返回 HTTP {response.status_code}")
        return {"status_code": response.status_code}
    finally:
        response.close()


def push_todo(ticket, task):
    sync_todos(ticket.id)


def schedule_sync(ticket):
    transaction.on_commit(lambda: sync_todos(ticket.id), robust=True)


@transaction.atomic
def sync_todos(ticket_id):
    ticket = Ticket.objects.select_for_update().get(id=ticket_id)
    if ticket.is_test:
        return
    integrations = list(Integration.objects.filter(domain=ticket.domain, kind="todo", is_enabled=True))
    if not integrations:
        return
    for task in ticket.tasks.all():
        active = task.status in [TicketTask.TaskStatus.PENDING, TicketTask.TaskStatus.CLAIMED]
        snapshot = {
            "ticket_id": ticket.id,
            "task_id": task.id,
            "sn": ticket.sn,
            "title": ticket.title,
            "node": task.node_name or task.node_id,
            "assignees": [task.assignee] if task.assignee else [],
            "status": "pending" if active else "finished",
            "url": f"/itsm/tickets/{ticket.id}",
        }
        for item in integrations:
            last = item.deliveries.filter(task=task).order_by("-id").first()
            if not last and not active:
                continue
            previous = {key: value for key, value in (last.payload if last else {}).items() if key not in {"event", "event_id"}}
            if previous == snapshot:
                continue
            event = "close" if not active else "update" if last else "create"
            key = hashlib.sha256(json.dumps([item.id, task.id, last.id if last else 0, snapshot], sort_keys=True).encode()).hexdigest()
            TodoDelivery.objects.get_or_create(
                event_key=key,
                defaults={
                    "integration": item,
                    "task": task,
                    "domain": ticket.domain,
                    "payload": {**snapshot, "event": event, "event_id": key},
                },
            )


def deliver(delivery_id):
    row = TodoDelivery.objects.select_related("integration").get(id=delivery_id)
    if not row.integration.is_enabled or row.status not in {"pending", "failed"}:
        return
    if TodoDelivery.objects.filter(integration=row.integration, task_id=row.task_id, id__gt=row.id).exists():
        TodoDelivery.objects.filter(id=row.id).update(status="superseded")
        return
    if not TodoDelivery.objects.filter(id=row.id, status__in=["pending", "failed"]).update(status="running", attempts=F("attempts") + 1):
        return
    try:
        send_payload(row.integration, row.payload)
        status, code = "done", ""
    except Exception as exc:
        status, code = "failed", type(exc).__name__
    TodoDelivery.objects.filter(id=row.id).update(status=status, code=code)


def drain_deliveries(limit=50):
    ids = list(TodoDelivery.objects.filter(status="pending", integration__is_enabled=True).order_by("id").values_list("id", flat=True)[:limit])
    for delivery_id in ids:
        deliver(delivery_id)
    return len(ids)
