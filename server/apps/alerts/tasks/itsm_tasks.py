from celery import shared_task
from django.utils import timezone

from apps.alerts.itsm.service import LEASE, execute_creation
from apps.alerts.models.action import ActionExecution
from apps.alerts.models.itsm import AlertItsmTicket
from apps.alerts.service.outbox import enqueue_outbox


@shared_task
def scan_itsm_tickets():
    now = timezone.now()
    expired = ActionExecution.objects.filter(action_type="itsm", status="running", updated_at__lte=now - LEASE).order_by("pk")
    for execution_id in list(expired.values_list("pk", flat=True)[:100]):
        execute_creation(execution_id)
    due = AlertItsmTicket.objects.filter(ticket_id__isnull=False, next_sync_at__lte=now).order_by("next_sync_at", "pk")
    count = 0
    for link in list(due[:100]):
        enqueue_outbox("itsm_sync", {"link_id": link.pk}, f"itsm-sync:{link.pk}:{link.next_sync_at.isoformat()}")
        count += 1
    return {"scheduled": count}
