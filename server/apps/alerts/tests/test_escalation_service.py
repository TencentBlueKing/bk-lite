"""告警升级服务覆盖测试。

对照 spec/requirements/告警中心/20260531.告警中心-新增告警升级策略.md
"""
import pytest
from django.utils import timezone

from apps.alerts.models.alert_operator import AlertAssignment, AlertEscalationTask
from apps.alerts.models.models import Alert


def _make_alert(alert_id="A1", level="0", status="pending", operator=None):
    return Alert.objects.create(
        alert_id=alert_id, level=level, title="t", content="c",
        fingerprint="fp-" + alert_id, status=status, operator=operator or [],
    )


def _chain(mode="append", layers=None):
    return {"enabled": True, "mode": mode, "layers": layers or [
        {"personnel": ["u1"], "wait_minutes": 10, "notify_channels": []},
        {"personnel": ["u2"], "wait_minutes": 20, "notify_channels": []},
    ]}


def _make_assignment(name="分派", escalation=None, channels=None, personnel=None):
    return AlertAssignment.objects.create(
        name=name, match_type="all",
        personnel=personnel or ["u1"],
        notify_channels=channels or [{"id": 1, "channel_type": "email", "name": "邮件"}],
        config={"escalation": escalation} if escalation else {},
    )


@pytest.mark.django_db
def test_escalation_task_fields_persist():
    alert = _make_alert()
    assignment = _make_assignment(escalation=_chain())
    task = AlertEscalationTask.objects.create(
        alert=alert, assignment=assignment, is_active=True,
        mode="append", layers=_chain()["layers"],
        current_layer_index=0, layer_started_at=timezone.now(),
    )
    task.refresh_from_db()
    assert task.current_layer_index == 0
    assert task.mode == "append"
    assert task.layers[1]["wait_minutes"] == 20
    assert task.is_active is True


from apps.alerts.service.escalation_service import EscalationService as ES


def test_parse_escalation_config_disabled():
    assert ES.parse_escalation_config({}) is None
    assert ES.parse_escalation_config({"escalation": {"enabled": False, "mode": "append", "layers": [{"personnel": ["u1"], "wait_minutes": 5}]}}) is None


def test_parse_escalation_config_invalid_mode():
    cfg = {"escalation": {"enabled": True, "mode": "bogus", "layers": [{"personnel": ["u1"], "wait_minutes": 5}]}}
    assert ES.parse_escalation_config(cfg) is None


def test_parse_escalation_config_empty_layers():
    cfg = {"escalation": {"enabled": True, "mode": "append", "layers": []}}
    assert ES.parse_escalation_config(cfg) is None


def test_parse_escalation_config_layer_missing_personnel():
    cfg = {"escalation": {"enabled": True, "mode": "append", "layers": [{"personnel": [], "wait_minutes": 5}]}}
    assert ES.parse_escalation_config(cfg) is None


def test_parse_escalation_config_layer_bad_wait():
    cfg = {"escalation": {"enabled": True, "mode": "append", "layers": [{"personnel": ["u1"], "wait_minutes": 0}]}}
    assert ES.parse_escalation_config(cfg) is None


def test_parse_escalation_config_valid():
    cfg = {"escalation": {"enabled": True, "mode": "replace", "layers": [
        {"personnel": ["u1"], "wait_minutes": 10, "notify_channels": []},
        {"personnel": ["u2"], "wait_minutes": 20},
    ]}}
    result = ES.parse_escalation_config(cfg)
    assert result["mode"] == "replace"
    assert len(result["layers"]) == 2
    assert result["layers"][1]["notify_channels"] == []  # 默认补空


def test_compute_roster_replace():
    layers = [{"personnel": ["u1"]}, {"personnel": ["u2", "u3"]}]
    assert ES.compute_roster(layers, 0, "replace") == ["u1"]
    assert ES.compute_roster(layers, 1, "replace") == ["u2", "u3"]


def test_compute_roster_append_dedups_and_orders():
    layers = [{"personnel": ["u1", "u2"]}, {"personnel": ["u2", "u3"]}]
    assert ES.compute_roster(layers, 0, "append") == ["u1", "u2"]
    assert ES.compute_roster(layers, 1, "append") == ["u1", "u2", "u3"]


@pytest.mark.django_db
def test_create_escalation_task_none_when_disabled():
    alert = _make_alert()
    assignment = _make_assignment(escalation=None)
    assert ES.create_escalation_task(alert, assignment) is None


@pytest.mark.django_db
def test_create_escalation_task_creates_at_layer_zero():
    alert = _make_alert(operator=["existing"])
    assignment = _make_assignment(escalation=_chain(mode="append"))
    task = ES.create_escalation_task(alert, assignment)
    assert task is not None
    assert task.current_layer_index == 0
    assert task.mode == "append"
    assert task.is_active is True
    alert.refresh_from_db()
    assert "existing" in alert.operator
    assert "u1" in alert.operator


@pytest.mark.django_db
def test_create_escalation_task_idempotent_reactivates():
    alert = _make_alert()
    assignment = _make_assignment(escalation=_chain())
    first = ES.create_escalation_task(alert, assignment)
    first.is_active = False
    first.current_layer_index = 1
    first.save()
    second = ES.create_escalation_task(alert, assignment)
    assert second.alert_id == first.alert_id
    assert second.is_active is True
    assert second.current_layer_index == 0


@pytest.mark.django_db
def test_stop_escalation_task():
    alert = _make_alert()
    assignment = _make_assignment(escalation=_chain())
    ES.create_escalation_task(alert, assignment)
    assert ES.stop_escalation_task(alert) is True
    assert AlertEscalationTask.objects.get(alert=alert).is_active is False


@pytest.mark.django_db
def test_reset_escalation_task_back_to_layer_zero():
    alert = _make_alert()
    assignment = _make_assignment(escalation=_chain())
    task = ES.create_escalation_task(alert, assignment)
    task.current_layer_index = 1
    task.is_active = False
    task.save()
    reset = ES.reset_escalation_task(alert, assignment)
    assert reset.current_layer_index == 0
    assert reset.is_active is True
