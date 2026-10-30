"""建单资格与执行：数据库事务只持有本地锁，HTTP 永远在事务外。"""
import hashlib
from datetime import timedelta
from uuid import uuid4

from django.db import transaction
from django.utils import timezone

from apps.alerts.action.matcher import event_matches
from apps.alerts.constants.constants import LogAction, LogTargetType
from apps.alerts.itsm.client import ItsmClient
from apps.alerts.itsm.config import ItsmError, form_data, get_connection, validate_config
from apps.alerts.itsm.snapshot import capture_snapshot
from apps.alerts.models.action import ActionExecution, ActionRule
from apps.alerts.models.itsm import AlertItsmTicket
from apps.alerts.models.models import Alert
from apps.alerts.models.outbox import AlertOutbox
from apps.alerts.service.outbox import enqueue_outbox
from apps.alerts.utils.operator_log import record_operator_log_deferred_mirror as record_operator_log
from apps.alerts.utils.rule_catalog import rules_are_valid

LEASE = timedelta(minutes=5)


def enqueue_creation(alert):
    if alert.session_status == "observing":
        return None
    try:
        snapshot, error = capture_snapshot(alert), ""
    except ItsmError as exc:
        snapshot, error = {}, str(exc)
    record, _ = enqueue_outbox(
        "itsm_evaluate", {"alert_pk": alert.pk, "team": alert.team, "snapshot": snapshot, "snapshot_error": error}, f"itsm-evaluate:{alert.pk}"
    )
    return record


def _teams(*values):
    result = None
    for value in values:
        current = set(map(str, value or []))
        result = current if result is None else result & current
    return sorted(result or [])


def authorized_rule(link, alert, rule, user_teams=None):
    if not rule or not rule.is_active or not rule.auto_execute or rule.action_type != "itsm" or rule.scope != "alert":
        return False
    values = [link.team, alert.team, rule.team]
    if user_teams is not None:
        values.append(user_teams)
    return bool(_teams(*values))


def _attempt(link, rule, snapshot, *, key, operator=None, snapshot_error=""):
    config = rule.action_config
    execution = ActionExecution.objects.create(
        rule=rule,
        alert_id=link.alert_id,
        trigger_event="created",
        trigger_type="manual" if operator else "auto",
        action_type="itsm",
        idempotency_key=key,
        operator=operator,
        input_snapshot={"config": config, "payload": snapshot, "snapshot_error": snapshot_error},
    )
    record_operator_log(
        action=LogAction.EXECUTE,
        target_type=LogTargetType.ALERT,
        operator=operator or "system",
        operator_object="ITSM 建单",
        target_id=link.alert.alert_id,
        overview=f"ITSM 建单已受理，执行记录 {execution.pk}",
    )
    link.current_execution = execution
    link.save(update_fields=["current_execution", "updated_at"])
    enqueue_outbox("itsm_create", {"execution_id": execution.pk}, f"itsm-create:{execution.pk}")
    return execution


def evaluate_creation(record_id):
    with transaction.atomic():
        record = AlertOutbox.objects.select_for_update().get(pk=record_id, kind="itsm_evaluate")
        if record.payload.get("evaluated"):
            return
        data = record.payload
        alert = Alert.objects.select_for_update().filter(pk=data["alert_pk"]).first()
        if alert and not AlertItsmTicket.objects.filter(alert=alert).exists():
            rules = ActionRule.objects.filter(is_active=True, auto_execute=True, action_type="itsm", scope="alert").order_by("pk")
            for rule in rules.iterator():
                team = _teams(data["team"], rule.team)
                if not team or "created" not in rule.trigger_events or not rules_are_valid(rule.match_rules, "action"):
                    continue
                if data.get("snapshot_error"):
                    execution = ActionExecution.objects.create(
                        alert=alert,
                        action_type="itsm",
                        trigger_event="created",
                        trigger_type="auto",
                        idempotency_key=f"itsm-evaluation:{alert.pk}",
                        input_snapshot={"team": data["team"]},
                    )
                    _finish(execution, "config_error", data["snapshot_error"])
                    break
                if not event_matches(data["snapshot"], rule.match_rules):
                    continue
                link = AlertItsmTicket.objects.create(alert=alert, rule=rule, rule_name=rule.name, team=[int(value) for value in team])
                _attempt(link, rule, data["snapshot"], key=f"itsm-auto:{alert.pk}", snapshot_error=data.get("snapshot_error", ""))
                break
        record.payload = {**data, "evaluated": True}
        record.save(update_fields=["payload", "updated_at"])


def _finish(execution, status, message):
    execution.status = status
    execution.result = {"message": message}
    execution.save(update_fields=["status", "result", "updated_at"])
    if status in {"failed", "config_error", "unknown"}:
        enqueue_outbox("itsm_failure", {"execution_id": execution.pk}, f"itsm-failure:{execution.pk}")


def execute_creation(execution_id):
    with transaction.atomic():
        # 一致锁顺序：Alert → 关联 → execution → 规则（同一 Alert 串行）。
        initial = ActionExecution.objects.filter(pk=execution_id, action_type="itsm").first()
        if not initial:
            return
        alert = Alert.objects.select_for_update().get(pk=initial.alert_id)
        link = AlertItsmTicket.objects.select_for_update().get(alert=alert)
        execution = ActionExecution.objects.select_for_update().get(pk=execution_id)
        if link.current_execution_id != execution.pk or link.ticket_id:
            return
        if execution.status == "running":
            if execution.updated_at <= timezone.now() - LEASE:
                _finish(execution, "unknown", "建单执行失联，远端结果待确认")
            return
        if execution.status != "pending":
            return
        rule = ActionRule.objects.select_for_update().filter(pk=link.rule_id).first()
        if not authorized_rule(link, alert, rule):
            _finish(execution, "skipped", "归属规则已停用或授权失效")
            return
        try:
            config = execution.input_snapshot["config"]
            conn = validate_config(config, link.team, lock_connection=True)
            if execution.input_snapshot.get("snapshot_error"):
                raise ItsmError(execution.input_snapshot["snapshot_error"])
            fields = form_data(config, execution.input_snapshot["payload"])
        except ItsmError as exc:
            _finish(execution, "config_error", str(exc))
            return
        claim = uuid4().hex
        execution.status = "running"
        execution.claim_token = claim
        execution.save(update_fields=["status", "claim_token", "updated_at"])
        link.connection = config["connection"]
        link.instance_id = conn["instance_id"]
        link.close_alert_on_ticket_closed = config.get("close_alert_on_ticket_closed", False)
        link.save(update_fields=["connection", "instance_id", "close_alert_on_ticket_closed", "updated_at"])
    try:
        ticket_id = ItsmClient(conn).create(config["workflow_key"], fields)
        outcome, message = "success", "工单已创建"
    except ItsmError as exc:
        ticket_id, outcome, message = None, exc.outcome, str(exc)
    with transaction.atomic():
        Alert.objects.select_for_update().get(pk=alert.pk)
        link = AlertItsmTicket.objects.select_for_update().get(pk=link.pk)
        execution = ActionExecution.objects.select_for_update().get(pk=execution_id)
        if execution.claim_token != claim or execution.status != "running" or link.current_execution_id != execution.pk or link.ticket_id:
            return
        if ticket_id:
            link.ticket_id = ticket_id
            link.ticket_title = fields["ticket__title"][:500]
            link.next_sync_at = timezone.now()
            link.save(update_fields=["ticket_id", "ticket_title", "next_sync_at", "updated_at"])
        _finish(execution, outcome, message)


def retry_creation(alert_pk, rule_id, operator, client_key, user_teams):
    digest = hashlib.sha256(client_key.encode()).hexdigest()
    key = f"itsm-manual:{operator}:{alert_pk}:{digest}"
    with transaction.atomic():
        alert = Alert.objects.select_for_update().get(pk=alert_pk)
        link = AlertItsmTicket.objects.select_for_update().filter(alert=alert, rule_id=rule_id).first()
        rule = ActionRule.objects.select_for_update().filter(pk=rule_id).first()
        if not link or not authorized_rule(link, alert, rule, user_teams):
            raise ItsmError("无可补建的归属规则或无权操作", "forbidden")
        get_connection(rule.action_config.get("connection"), _teams(link.team, alert.team, rule.team, user_teams))
        replay = ActionExecution.objects.filter(idempotency_key=key).first()
        if replay:
            return replay, False
        current = ActionExecution.objects.get(pk=link.current_execution_id)
        if link.ticket_id or current.status in {"pending", "running"}:
            return current, False
        if current.status not in {"failed", "config_error"}:
            raise ItsmError("当前建单结果不允许重试，请先核查", "conflict")
        return (
            _attempt(
                link,
                rule,
                current.input_snapshot["payload"],
                key=key,
                operator=operator,
                snapshot_error=current.input_snapshot.get("snapshot_error", ""),
            ),
            True,
        )
