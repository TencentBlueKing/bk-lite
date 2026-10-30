"""真实 ORM + HTTP 边界替身：故障交错、事务一致性及租户隔离。"""
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.db import transaction
from django.utils import timezone

from apps.alerts.itsm.config import ItsmError, form_data
from apps.alerts.itsm.reconcile import reconcile
from apps.alerts.itsm.service import enqueue_creation, evaluate_creation, execute_creation, retry_creation
from apps.alerts.itsm.sync import sync_ticket
from apps.alerts.models.action import ActionExecution
from apps.alerts.models.itsm import AlertItsmTicket
from apps.alerts.models.outbox import AlertOutbox
from apps.alerts.service.outbox import deliver_outbox_record
from apps.alerts.tests.test_itsm_client import response
from apps.alerts.tests.test_itsm_service import alert, configure_itsm, itsm_connection, prepare, rule  # noqa: F401
from apps.alerts.tests.test_itsm_sync import closed_response, linked


@pytest.mark.django_db
def test_transaction_rollback_keeps_no_orphan_creation_intent(setup_itsm):
    rule()
    with pytest.raises(RuntimeError), transaction.atomic():
        a = alert()
        enqueue_creation(a)
        raise RuntimeError("crash before commit")
    assert not AlertOutbox.objects.exists()
    assert not AlertItsmTicket.objects.exists()


@pytest.mark.django_db
def test_no_match_is_final_even_when_a_rule_is_added_later(setup_itsm):
    record = enqueue_creation(alert())
    evaluate_creation(record.pk)
    rule()
    evaluate_creation(record.pk)
    assert not AlertItsmTicket.objects.exists()


@pytest.mark.django_db
@pytest.mark.parametrize("change", [{"is_active": False}, {"action_type": "job"}, {"team": [2]}, {"auto_execute": False}])
def test_changed_permission_before_claim_skips_post(setup_itsm, change):
    a = alert()
    r = rule()
    link = prepare(a)
    for key, value in change.items():
        setattr(r, key, value)
    r.save()
    with patch("requests.Session.request") as http:
        execute_creation(link.current_execution_id)
        http.assert_not_called()
    link.current_execution.refresh_from_db()
    assert link.current_execution.status == "skipped"


@pytest.mark.django_db
def test_interleaved_delivery_and_manual_retry_do_not_resend(setup_itsm):
    a = alert()
    r = rule()
    link = prepare(a)

    def remote(*args, **kwargs):
        execute_creation(link.current_execution_id)
        current, created = retry_creation(a.pk, r.pk, "alice", "other-key", [1])
        assert not created and current.pk == link.current_execution_id
        return response({"result": True, "code": "20000", "data": {"ticket": {"id": "123"}}})

    with patch("requests.Session.request", side_effect=remote) as http:
        execute_creation(link.current_execution_id)
        assert http.call_count == 1
    assert ActionExecution.objects.filter(alert=a).count() == 1


@pytest.mark.django_db
def test_late_create_response_cannot_overwrite_unknown_decision(setup_itsm):
    rule()
    link = prepare(alert())

    def remote(*args, **kwargs):
        ActionExecution.objects.filter(pk=link.current_execution_id).update(updated_at=timezone.now() - timedelta(minutes=10))
        execute_creation(link.current_execution_id)
        return response({"result": True, "code": "20000", "data": {"ticket": {"id": "123"}}})

    with patch("requests.Session.request", side_effect=remote):
        execute_creation(link.current_execution_id)
    link.refresh_from_db()
    assert link.ticket_id is None
    assert link.current_execution.status == "unknown"


@pytest.mark.django_db
def test_outbox_restores_committed_pending_execution(setup_itsm):
    a = alert()
    rule()
    record = enqueue_creation(a)
    deliver_outbox_record(record.pk)
    link = AlertItsmTicket.objects.get(alert=a)
    pending = AlertOutbox.objects.get(kind="itsm_create")
    with patch("requests.Session.request", return_value=response({"result": True, "code": "20000", "data": {"ticket": {"id": "123"}}})) as http:
        deliver_outbox_record(pending.pk)
        deliver_outbox_record(pending.pk)
        assert http.call_count == 1
    link.refresh_from_db()
    assert link.ticket_id == "123"


@pytest.mark.django_db
def test_ended_ticket_sync_does_not_close_alert(setup_itsm):
    a, _, link = linked()
    with patch("requests.Session.request", return_value=closed_response()):
        sync_ticket(link.pk)
    a.refresh_from_db()
    link.refresh_from_db()
    assert a.status == "unassigned"
    assert link.status_label == "工单已关闭"
    assert link.close_result == "unprocessed"
    assert not AlertOutbox.objects.filter(kind="action", payload__event_name="closed").exists()


@pytest.mark.django_db
def test_stale_sync_cannot_overwrite_newer_observation(setup_itsm):
    a, _, link = linked()

    def remote(*args, **kwargs):
        AlertItsmTicket.objects.filter(pk=link.pk).update(sync_claim="new-generation", ticket_status="new-status")
        return closed_response()

    with patch("requests.Session.request", side_effect=remote):
        sync_ticket(link.pk)
    link.refresh_from_db()
    a.refresh_from_db()
    assert link.ticket_status == "new-status" and a.status == "unassigned"


@pytest.mark.django_db
def test_reconcile_only_unknown_and_remote_ticket_unique(setup_itsm):
    a, _, link = linked()
    a2 = alert()
    second = prepare(a2)
    second.connection, second.instance_id = "dev", "test-itsm"
    second.save()
    ActionExecution.objects.filter(pk=second.current_execution_id).update(status="unknown", result={"message": "timeout"})
    with patch("requests.Session.request", return_value=closed_response()):
        with pytest.raises(ItsmError, match="已关联"):
            reconcile(a2.pk, second.current_execution_id, "123", "checked", True, "alice", [1])
    second.refresh_from_db()
    assert second.ticket_id is None and second.current_execution.status == "unknown"
    with patch(
        "requests.Session.request", return_value=response({"result": True, "code": "20000", "data": {"ticket": {"id": "456", "status": "running"}}})
    ):
        preview = reconcile(a2.pk, second.current_execution_id, "456", "", False, "alice", [1])
        assert preview["preview"]["ticket_id"] == "456"
        reconcile(a2.pk, second.current_execution_id, "456", "ITSM confirmed source alert", True, "alice", [1])
    second.refresh_from_db()
    assert second.ticket_id == "456"
    assert second.current_execution.result["message"] == "timeout"
    assert second.current_execution.result["reconciled_by"] == "alice"


@pytest.mark.django_db
def test_repeated_sync_fault_notifies_once_and_keeps_creation_success(setup_itsm):
    _, _, link = linked(close=False)
    ActionExecution.objects.filter(pk=link.current_execution_id).update(status="success")
    with patch("requests.Session.request", return_value=response({}, 401)):
        sync_ticket(link.pk)
        AlertItsmTicket.objects.filter(pk=link.pk).update(next_sync_at=timezone.now())
        sync_ticket(link.pk)
    assert AlertOutbox.objects.filter(kind="itsm_failure").count() == 1
    link.current_execution.refresh_from_db()
    assert link.current_execution.status == "success"


def test_form_mapping_preserves_zero_false_and_structured_values():
    cfg = {
        "form_bindings": [
            {"name": "ticket__title", "from": "field", "value": "title"},
            {"name": "number", "from": "const", "value": 0},
            {"name": "flag", "from": "const", "value": False},
            {"name": "obj", "from": "const", "value": {"tags": ["cpu"]}},
        ]
    }
    assert form_data(cfg, {"title": "test"}) == {"ticket__title": "test", "number": 0, "flag": False, "obj": {"tags": ["cpu"]}}
    with pytest.raises(ItsmError, match="缺失"):
        form_data(cfg, {})


@pytest.mark.django_db
def test_failure_notification_uses_scoped_recipients_and_one_durable_intent(setup_itsm):
    from apps.alerts.itsm.notification import notify_failure
    from apps.system_mgmt.models.channel import Channel
    from apps.system_mgmt.models.user import Group, User

    Group.objects.get_or_create(id=1, defaults={"name": "team-one"})
    User.objects.create(username="operator", group_list=[1], email="test@example.invalid")
    User.objects.create(username="outsider", group_list=[2], email="other@example.invalid")
    channel = Channel.objects.create(name="test", channel_type="email", team=[1])
    setup_itsm["failure_notification"] = {"usernames": ["operator", "outsider"], "channel_ids": [channel.pk]}
    rule()
    link = prepare(alert())
    with patch("requests.Session.request", return_value=response({"result": False, "code": "40000"}, 400)):
        execute_creation(link.current_execution_id)
    notify_failure(link.current_execution_id)
    notify_failure(link.current_execution_id)
    records = AlertOutbox.objects.filter(kind="notification")
    assert records.count() == 1
    params = records.get().payload["params"]
    assert params[0]["username_list"] == ["operator"]
    assert "SENSITIVE-SENTINEL" not in str(params)
    link.current_execution.refresh_from_db()
    assert link.current_execution.status == "failed"
    assert link.current_execution.result["notification"] == "queued"


@pytest.mark.django_db
def test_synthetic_alert_persists_creation_snapshot(setup_itsm):
    from apps.alerts.aggregation.builder.synthetic_alert_builder import SyntheticAlertBuilder
    from apps.alerts.models.alert_operator import AlarmStrategy

    strategy = AlarmStrategy.objects.create(name="heartbeat", dispatch_team=[1])
    created = SyntheticAlertBuilder.create_alert(strategy, {"alert_template": {"title": "heartbeat missing"}}, timezone.now())
    record = AlertOutbox.objects.get(kind="itsm_evaluate")
    assert record.payload["alert_pk"] == created.pk
    assert record.payload["snapshot"]["title"] == "heartbeat missing"


@pytest.mark.django_db
def test_session_confirm_and_observation_recovery_are_separate(setup_itsm):
    from apps.alerts.aggregation.recovery.timeout_checker import TimeoutChecker

    a = alert(is_session_alert=True, session_status="observing", session_end_time=timezone.now())
    rule()
    assert enqueue_creation(a) is None
    TimeoutChecker._confirm_session_alert(a)
    TimeoutChecker._confirm_session_alert(a)
    record = AlertOutbox.objects.get(kind="itsm_evaluate")
    evaluate_creation(record.pk)
    assert AlertItsmTicket.objects.filter(alert=a).count() == 1
    recovered = alert(status="auto_recovery", is_session_alert=True, session_status="observing", session_end_time=timezone.now())
    TimeoutChecker._confirm_session_alert(recovered)
    assert not AlertOutbox.objects.filter(kind="itsm_evaluate", payload__alert_pk=recovered.pk).exists()


@pytest.mark.django_db
def test_close_releases_fingerprint_stops_reminders_and_queues_closed_jobs(setup_itsm):
    from apps.alerts.models.active_fingerprint import ActiveAlertFingerprint
    from apps.alerts.models.alert_operator import AlertAssignment, AlertEscalationTask, AlertReminderTask

    a, _, link = linked()
    ActiveAlertFingerprint.objects.create(fingerprint="active-test", alert=a)
    assignment = AlertAssignment.objects.create(name="test", match_type="all")
    AlertReminderTask.objects.create(
        alert=a, assignment=assignment, current_frequency_minutes=5, current_max_reminders=3, next_reminder_time=timezone.now()
    )
    AlertEscalationTask.objects.create(
        alert=a, assignment=assignment, mode="append", layer_started_at=timezone.now(), next_escalation_at=timezone.now()
    )
    # 原有关闭作业的投递意图必须和关闭状态一起提交。
    with patch("requests.Session.request", return_value=closed_response()):
        sync_ticket(link.pk)
    a.refresh_from_db()
    link.refresh_from_db()
    assert a.closed_at is None
    assert a.status == "unassigned"
    assert link.status_label == "工单已关闭"
    assert ActiveAlertFingerprint.objects.filter(alert=a).exists()
    assert not AlertOutbox.objects.filter(kind="action", payload__event_name="closed", payload__alert_id=a.alert_id).exists()


@pytest.mark.django_db
def test_periodic_scan_recovers_lost_creation_and_schedules_due_ticket(setup_itsm):
    from apps.alerts.tasks.itsm_tasks import scan_itsm_tickets

    _, _, linked_ticket = linked(close=False, status="auto_recovery")
    other = prepare(alert())
    ActionExecution.objects.filter(pk=other.current_execution_id).update(status="running", updated_at=timezone.now() - timedelta(minutes=10))
    with patch("requests.Session.request") as http:
        assert scan_itsm_tickets()["scheduled"] == 1
        scan_itsm_tickets()
        http.assert_not_called()
    assert AlertOutbox.objects.filter(kind="itsm_sync").count() == 1
    other.current_execution.refresh_from_db()
    assert other.current_execution.status == "unknown"
    record = AlertOutbox.objects.get(kind="itsm_sync")
    with patch("requests.Session.request", return_value=closed_response()):
        deliver_outbox_record(record.pk)
    linked_ticket.refresh_from_db()
    assert linked_ticket.ticket_status == "finished"
    assert linked_ticket.status_label == "工单已关闭"


@pytest.mark.django_db
def test_missing_notification_configuration_is_visible_without_changing_creation(setup_itsm):
    from apps.alerts.itsm.notification import notify_failure

    rule()
    link = prepare(alert())
    ActionExecution.objects.filter(pk=link.current_execution_id).update(status="unknown", result={"message": "timeout"})
    with pytest.raises(ItsmError):
        notify_failure(link.current_execution_id)
    link.current_execution.refresh_from_db()
    assert link.current_execution.status == "unknown"
    assert "通知" in link.current_execution.result["notification"]


@pytest.mark.django_db
@pytest.mark.parametrize("oversize", ["content", "labels", "push_source_ids"])
def test_oversized_input_is_visible_failure_not_false_no_match(setup_itsm, oversize):
    a = alert()
    if oversize == "content":
        a.content = "x" * 70000
    elif oversize == "labels":
        a.labels = {"large": "x" * 70000}
    else:
        a.push_source_ids = ["source" + str(i) for i in range(2000)]
    a.save()
    rule(match_rules=[[{"key": "content", "operator": "contains", "value": "x"}]])
    record = enqueue_creation(a)
    assert record.payload["snapshot"] == {}
    evaluate_creation(record.pk)
    failed = ActionExecution.objects.get(alert=a)
    assert failed.status == "config_error"
    assert "未评估" in failed.result["message"]
    assert not AlertItsmTicket.objects.filter(alert=a).exists()
    assert AlertOutbox.objects.filter(kind="itsm_failure").exists()


@pytest.mark.django_db
def test_deep_input_does_not_abort_alert_transaction(setup_itsm):
    rule()
    nested = "leaf"
    for _ in range(30):
        nested = {"nested": nested}
    with transaction.atomic():
        a = alert(labels=nested)
        record = enqueue_creation(a)
    evaluate_creation(record.pk)
    assert ActionExecution.objects.get(alert=a).status == "config_error"


@pytest.mark.django_db
@pytest.mark.parametrize("candidate", ["none", "disabled", "different_team"])
def test_oversized_input_without_eligible_rule_does_not_report_itsm_failure(setup_itsm, candidate):
    if candidate == "disabled":
        rule(is_active=False)
    elif candidate == "different_team":
        rule(team=[999])
    a = alert()
    a.content = "x" * 70000
    a.save()
    record = enqueue_creation(a)
    evaluate_creation(record.pk)
    record.refresh_from_db()
    assert record.payload["evaluated"] is True
    assert not ActionExecution.objects.filter(alert=a).exists()
    assert not AlertOutbox.objects.filter(kind="itsm_failure").exists()
