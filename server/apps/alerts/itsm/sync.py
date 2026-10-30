import os
from datetime import timedelta
from uuid import uuid4

from django.db import transaction
from django.utils import timezone

from apps.alerts.itsm.client import ItsmClient
from apps.alerts.itsm.config import ItsmError, get_connection
from apps.alerts.itsm.service import LEASE, _teams, authorized_rule
from apps.alerts.models.action import ActionRule
from apps.alerts.models.itsm import AlertItsmTicket
from apps.alerts.models.models import Alert
from apps.alerts.service.outbox import enqueue_outbox


def sync_interval():
    try:
        return max(60, min(86400, int(os.getenv("ALERT_ITSM_SYNC_SECONDS", "300"))))
    except ValueError:
        return 300


def sync_ticket(link_id):
    now = timezone.now()
    with transaction.atomic():
        link = AlertItsmTicket.objects.select_for_update().filter(pk=link_id, ticket_id__isnull=False).first()
        if not link or link.next_sync_at > now:
            return
        claim = uuid4().hex
        link.sync_claim = claim
        link.next_sync_at = now + LEASE
        link.save(update_fields=["sync_claim", "next_sync_at", "updated_at"])
    try:
        alert_teams = Alert.objects.get(pk=link.alert_id).team
        effective_teams = _teams(link.team, alert_teams)
        connection = get_connection(link.connection, effective_teams, link.instance_id)
        detail = ItsmClient(connection).detail(link.ticket_id)
        error = ""
    except ItsmError as exc:
        detail, error = None, str(exc)
    with transaction.atomic():
        current = AlertItsmTicket.objects.select_for_update().get(pk=link_id)
        if current.sync_claim != claim:
            return
        if error and not current.sync_error:
            fault_key = f"itsm-sync-failure:{current.pk}:{timezone.now().isoformat()}"
            enqueue_outbox("itsm_failure", {"execution_id": current.current_execution_id, "fault_key": fault_key}, fault_key)
        current.sync_claim = ""
        current.sync_error = error
        current.sync_failures = current.sync_failures + 1 if error else 0
        current.next_sync_at = timezone.now() + timedelta(
            seconds=min(max(3600, sync_interval()), sync_interval() * 2 ** min(current.sync_failures, 4))
        )
        if detail:
            for key, value in detail.items():
                if key in {"ticket_title", "ticket_number"} and not value:
                    continue
                setattr(current, key, value)
            current.last_synced_at = timezone.now()
        current.save()


def apply_close(link_id):
    """调用者刚完成详情查询；pending 失败补偿也必须先重新查询工单。"""
    initial = AlertItsmTicket.objects.get(pk=link_id)
    with transaction.atomic():
        alert = Alert.objects.select_for_update().get(pk=initial.alert_id)
        link = AlertItsmTicket.objects.select_for_update().get(pk=link_id)
        if link.close_result != "pending" or not link.is_closed:
            return
        rule = ActionRule.objects.select_for_update().filter(pk=link.rule_id).first()
        if not link.close_alert_on_ticket_closed or not authorized_rule(link, alert, rule):
            link.close_result = "skipped_permission"
        else:
            get_connection(link.connection, link.team, link.instance_id, lock=True)
            from apps.alerts.service.alter_operator import close_alert_from_itsm

            link.close_result = "closed" if close_alert_from_itsm(alert, link.pk) else "skipped_inactive"
        link.close_error = ""
        link.save(update_fields=["close_result", "close_error", "updated_at"])
