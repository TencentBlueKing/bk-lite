import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.db import transaction
from django.utils import timezone

from apps.alerts.itsm.service import enqueue_creation, evaluate_creation, execute_creation, retry_creation
from apps.alerts.models.action import ActionExecution, ActionRule
from apps.alerts.models.itsm import AlertItsmTicket
from apps.alerts.models.models import Alert
from apps.alerts.models.outbox import AlertOutbox
from apps.alerts.tests.test_itsm_client import create_calls, itsm_connection, response  # noqa: F401


@pytest.fixture(name="setup_itsm")
def configure_itsm(settings, monkeypatch, connection):
    settings.ALERT_ITSM_CONNECTIONS = {"dev": connection}
    monkeypatch.setenv("TEST_ITSM_TOKEN", "SENSITIVE-SENTINEL")
    return connection


def alert(**kwargs):
    return Alert.objects.create(alert_id=uuid.uuid4().hex, title="CPU 高负载", content="测试告警", level="1", team=[1], **kwargs)


def rule(**kwargs):
    values = {
        "name": "ITSM",
        "team": [1],
        "trigger_events": ["created"],
        "action_type": "itsm",
        "action_config": {
            "connection": "dev",
            "workflow_key": "workflow",
            "form_bindings": [{"name": "ticket__title", "from": "field", "value": "title"}],
            "close_alert_on_ticket_closed": False,
        },
    }
    values.update(kwargs)
    return ActionRule.objects.create(**values)


def prepare(a):
    record = enqueue_creation(a)
    evaluate_creation(record.pk)
    return AlertItsmTicket.objects.get(alert=a)


@pytest.mark.django_db
def test_first_matching_rule_and_creation_snapshot_survive_dispatch(setup_itsm):
    a = alert()
    first = rule(match_rules=[[{"key": "title", "operator": "eq", "value": "CPU 高负载"}]])
    rule()
    record = enqueue_creation(a)
    a.status = "auto_recovery"
    a.title = "已恢复"
    a.save()
    evaluate_creation(record.pk)
    evaluate_creation(record.pk)
    link = AlertItsmTicket.objects.get(alert=a)
    assert link.rule_id == first.pk
    assert ActionExecution.objects.filter(alert=a).count() == 1
    with patch(
        "requests.Session.request", return_value=response({"result": True, "code": "20000", "data": {"id": "102026090716182700005102"}})
    ) as http:
        execute_creation(link.current_execution_id)
        execute_creation(link.current_execution_id)
        assert len(create_calls(http)) == 1
    link.refresh_from_db()
    a.refresh_from_db()
    assert link.ticket_id == "102026090716182700005102"
    assert a.status == "auto_recovery"
    assert link.current_execution.status == "success"


@pytest.mark.django_db
def test_worker_loss_is_unknown_and_no_second_post(setup_itsm):
    a = alert()
    rule()
    link = prepare(a)
    ActionExecution.objects.filter(pk=link.current_execution_id).update(status="running", updated_at=timezone.now() - timedelta(minutes=10))
    with patch("requests.Session.request") as http:
        execute_creation(link.current_execution_id)
        http.assert_not_called()
    link.current_execution.refresh_from_db()
    assert link.current_execution.status == "unknown"


@pytest.mark.django_db
def test_explicit_failure_retry_uses_new_config_but_replay_keeps_attempt(setup_itsm):
    a = alert()
    r = rule()
    link = prepare(a)
    with patch("requests.Session.request", return_value=response({"result": False, "code": "40000"}, 400)):
        execute_creation(link.current_execution_id)
    r.action_config["workflow_key"] = "fixed-workflow"
    r.save()
    retried, created = retry_creation(a.pk, r.pk, "alice", "client-key", [1])
    assert created
    assert retried.input_snapshot["config"]["workflow_key"] == "fixed-workflow"
    ActionExecution.objects.filter(pk=retried.pk).update(status="failed")
    replay, created = retry_creation(a.pk, r.pk, "alice", "client-key", [1])
    assert not created and replay.pk == retried.pk
    assert ActionExecution.objects.filter(alert=a).count() == 2


@pytest.mark.django_db
def test_observing_session_does_not_consume_creation_intent(setup_itsm):
    a = alert(is_session_alert=True, session_status="observing")
    rule()
    assert enqueue_creation(a) is None
    assert not AlertOutbox.objects.exists()
    a.session_status = "confirmed"
    a.save()
    assert enqueue_creation(a) is not None


@pytest.mark.django_db
def test_enqueue_failure_does_not_break_alert_creation_transaction(setup_itsm):
    rule()

    def broken_enqueue(*args, **kwargs):
        Alert.objects.create(pk=first.pk, alert_id=first.alert_id, title="dup", content="", level="1", team=[1])

    with transaction.atomic():
        first = alert()
        with patch("apps.alerts.itsm.service.enqueue_outbox", side_effect=broken_enqueue):
            assert enqueue_creation(first) is None
        second = alert()
    assert set(Alert.objects.values_list("pk", flat=True)) == {first.pk, second.pk}
    assert not AlertOutbox.objects.exists()


@pytest.mark.django_db
def test_lifecycle_comment_is_not_queued_without_native_comment_api(setup_itsm):
    from apps.alerts.itsm.comments import enqueue_comment
    from apps.alerts.tests.test_itsm_sync import linked

    a, r, _ = linked()
    r.trigger_events = ["created", "closed"]
    r.save()
    assert enqueue_comment(a, "closed") is None
    assert not AlertOutbox.objects.filter(kind="itsm_comment").exists()
