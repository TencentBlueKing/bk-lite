"""告警超时升级 BDD（中文 Gherkin）。

对照升级链规格：
- 待响应告警在第一层等待时长超时后自动推进到第二层；
- 认领后（处理中）升级任务停用，层级不变。

2 场景：1 happy（超时升级） + 1 corner（认领后停用）。
"""

import os
from datetime import timedelta
from pathlib import Path

import pytest
from django.utils import timezone
from pytest_bdd import given, scenarios, then, when

from apps.alerts.models.alert_operator import AlertAssignment, AlertEscalationTask
from apps.alerts.models.models import Alert
from apps.alerts.service.escalation_service import EscalationService

FEATURE = str(Path(__file__).parent / "escalation.feature")
scenarios(FEATURE)

LAYERS = [
    {"personnel": ["u1"], "wait_minutes": 10, "notify_channels": []},
    {"personnel": ["u2"], "wait_minutes": 20, "notify_channels": []},
]


@pytest.fixture
def ctx():
    return {}


@pytest.fixture
def _db(db):
    return db


# ---------- Given ----------


@given("存在一条配置了两层升级链的分派规则")
def _rule_two_layers(ctx, _db):
    ctx["assignment"] = AlertAssignment.objects.create(
        name="bdd-esc-two",
        match_type="all",
        personnel=["u1"],
        notify_channels=[],
        notification_scenario=[],
        notification_frequency={},
        match_rules=[],
        config={"escalation": {"enabled": True, "mode": "append", "layers": LAYERS}},
    )


@given("存在一条配置了升级链的分派规则")
def _rule_one(ctx, _db):
    ctx["assignment"] = AlertAssignment.objects.create(
        name="bdd-esc-one",
        match_type="all",
        personnel=["u1"],
        notify_channels=[],
        notification_scenario=[],
        notification_frequency={},
        match_rules=[],
        config={"escalation": {"enabled": True, "mode": "append", "layers": LAYERS}},
    )


@given("一条告警已分派且停留在待响应状态超过第一层等待时长")
def _pending_overdue(ctx, _db):
    alert = Alert.objects.create(
        alert_id="BDD-ESC-1",
        level="0",
        title="超时升级测试",
        content="pending overdue",
        fingerprint="bddesc1",
        status="pending",
        operator=["u1"],
        source_name="prometheus",
        team=[1],
    )
    task = EscalationService.create_escalation_task(alert, ctx["assignment"])
    # 把本层开始时间拨早 15 分钟，超过第一层 10 分钟等待时长
    task.layer_started_at = timezone.now() - timedelta(minutes=15)
    task.save(update_fields=["layer_started_at"])
    ctx["alert"] = alert


@given("一条告警已分派并被认领进入处理中")
def _processing(ctx, _db):
    alert = Alert.objects.create(
        alert_id="BDD-ESC-2",
        level="0",
        title="已认领测试",
        content="processing alert",
        fingerprint="bddesc2",
        status="processing",
        operator=["u1"],
        source_name="prometheus",
        team=[1],
    )
    task = EscalationService.create_escalation_task(alert, ctx["assignment"])
    task.layer_started_at = timezone.now() - timedelta(minutes=15)
    task.save(update_fields=["layer_started_at"])
    ctx["alert"] = alert


# ---------- When ----------


@when("升级扫描任务运行")
def _run(ctx, monkeypatch):
    monkeypatch.setattr(
        EscalationService,
        "_send_escalation_notification",
        classmethod(lambda cls, *a, **k: True),
    )
    EscalationService.check_and_process_escalations()
    ctx["task"] = AlertEscalationTask.objects.get(alert=ctx["alert"])
    ctx["alert"].refresh_from_db()


# ---------- Then ----------


@then("告警进入第二层并通知第二层处理人")
def _at_layer_two(ctx):
    assert ctx["task"].current_layer_index == 1, (
        f"期望 current_layer_index=1，实际={ctx['task'].current_layer_index}"
    )


@then("第二层处理人具备认领资格")
def _claimable(ctx):
    assert "u2" in ctx["alert"].operator, (
        f"期望 u2 在 operator 中，实际={ctx['alert'].operator}"
    )


@then("升级任务被停用且层级不变")
def _stopped(ctx):
    assert ctx["task"].is_active is False, (
        f"期望 is_active=False，实际={ctx['task'].is_active}"
    )
    assert ctx["task"].current_layer_index == 0, (
        f"期望 current_layer_index=0，实际={ctx['task'].current_layer_index}"
    )
