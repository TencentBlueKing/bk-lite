import pytest
from django.db import IntegrityError
from apps.alerts.models.action import ActionRule, ActionExecution
from apps.alerts.models.models import Alert


@pytest.mark.django_db
def test_action_rule_defaults():
    rule = ActionRule.objects.create(name="磁盘清理", team=[1])
    assert rule.is_active is True
    assert rule.scope == "alert"
    assert rule.action_type == "job"
    assert rule.match_rules == []
    assert rule.trigger_events == []
    assert rule.action_config == {}


@pytest.mark.django_db
def test_idempotency_key_unique_for_auto():
    alert = Alert.objects.create(alert_id="A1", fingerprint="fp1", title="t", content="c", level="0")
    rule = ActionRule.objects.create(name="r", team=[1])
    ActionExecution.objects.create(rule=rule, alert=alert, trigger_event="created",
                                   trigger_type="auto", idempotency_key="r:A1:created", status="running")
    with pytest.raises(IntegrityError):
        ActionExecution.objects.create(rule=rule, alert=alert, trigger_event="created",
                                       trigger_type="auto", idempotency_key="r:A1:created", status="running")


@pytest.mark.django_db
def test_manual_rows_allow_multiple_null_keys():
    alert = Alert.objects.create(alert_id="A2", fingerprint="fp2", title="t", content="c", level="0")
    rule = ActionRule.objects.create(name="r", team=[1])
    ActionExecution.objects.create(rule=rule, alert=alert, trigger_event="manual",
                                   trigger_type="manual", idempotency_key=None, status="running")
    ActionExecution.objects.create(rule=rule, alert=alert, trigger_event="manual",
                                   trigger_type="manual", idempotency_key=None, status="running")
    assert ActionExecution.objects.filter(trigger_type="manual").count() == 2
