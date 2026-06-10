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
