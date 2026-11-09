from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.alerts.constants.constants import LogAction, LogTargetType
from apps.alerts.itsm.client import ItsmClient
from apps.alerts.itsm.config import ItsmError, get_connection
from apps.alerts.itsm.service import authorized_rule
from apps.alerts.models.action import ActionExecution, ActionRule
from apps.alerts.models.itsm import AlertItsmTicket
from apps.alerts.models.models import Alert
from apps.alerts.utils.operator_log import record_operator_log_deferred_mirror as record_operator_log


def _check(link, alert, rule, execution_id, teams):
    if not authorized_rule(link, alert, rule, teams):
        raise ItsmError("无权核查当前关联", "forbidden")
    if link.ticket_id or link.current_execution_id != execution_id or link.current_execution.status != "unknown":
        raise ItsmError("建单执行已变更或无需核查", "conflict")


def reconcile(alert_pk, execution_id, ticket_id, evidence, confirm, operator, teams):
    alert = Alert.objects.get(pk=alert_pk)
    link = AlertItsmTicket.objects.select_related("current_execution", "rule").filter(alert=alert).first()
    if not link:
        raise ItsmError("没有待核查关联", "conflict")
    _check(link, alert, link.rule, execution_id, teams)
    connection = get_connection(link.connection, link.team, link.instance_id)
    detail = ItsmClient(connection).detail(ticket_id)
    if not confirm:
        return {"preview": detail, "execution_id": execution_id}
    try:
        with transaction.atomic():
            alert = Alert.objects.select_for_update().get(pk=alert_pk)
            link = AlertItsmTicket.objects.select_for_update().get(pk=link.pk)
            rule = ActionRule.objects.select_for_update().filter(pk=link.rule_id).first()
            execution = ActionExecution.objects.select_for_update().get(pk=execution_id)
            link.current_execution = execution if link.current_execution_id == execution.pk else link.current_execution
            _check(link, alert, rule, execution_id, teams)
            get_connection(link.connection, link.team, link.instance_id, lock=True)
            for key, value in detail.items():
                setattr(link, key, value)
            link.last_synced_at = timezone.now()
            link.next_sync_at = timezone.now()
            link.save()
            execution.status = "success"
            execution.result = {**execution.result, "reconciled_by": operator, "reconciled_at": timezone.now().isoformat(), "evidence": evidence}
            execution.save(update_fields=["status", "result", "updated_at"])
            record_operator_log(
                action=LogAction.MODIFY,
                target_type=LogTargetType.ALERT,
                operator=operator,
                operator_object="ITSM 建单结果核查",
                target_id=alert.alert_id,
                overview=f"核查并关联 ITSM 工单，执行记录 {execution.pk}",
            )
    except IntegrityError:
        raise ItsmError("该 ITSM 工单已关联其他告警", "conflict") from None
    return {"ticket_id": detail["ticket_id"], "execution_id": execution_id, "status": "success"}
