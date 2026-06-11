"""告警超时升级 BDD（中文 Gherkin）。

B 模型：初始分派人是第一棒；升级链里配置的层是分派之后逐棒升级的责任人。
有效链 = [初始分派人 zhang] + [升级层 li, wang]。

- 初始分派人 zhang 在其认领等待时长内未认领 → 升级到第一个升级层 li 并通知；
- 认领后（处理中）升级任务停用，层级不变。

2 场景：1 happy（超时升级） + 1 corner（认领后停用）。
"""

import os  # noqa: F401
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

# 升级层（分派之后逐棒升级的责任人）；初始分派人单独是 zhang
LAYERS = [
    {"personnel": ["li"], "wait_minutes": 10, "notify_channels": []},
    {"personnel": ["wang"], "wait_minutes": 20, "notify_channels": []},
]


@pytest.fixture
def ctx():
    return {}


@pytest.fixture
def _db(db):
    return db


# ---------- Given ----------


@given("存在一条配置了升级链的分派规则")
def _rule(ctx, _db):
    ctx["assignment"] = AlertAssignment.objects.create(
        name="bdd-esc",
        match_type="all",
        personnel=["zhang"],
        notify_channels=[],
        notification_scenario=[],
        notification_frequency={},
        match_rules=[],
        config={"escalation": {"enabled": True, "mode": "append", "layers": LAYERS}},
    )


@given("一条告警已分派给初始分派人且超过其认领等待时长仍未认领")
def _pending_overdue(ctx, _db):
    alert = Alert.objects.create(
        alert_id="BDD-ESC-1",
        level="0",
        title="超时升级测试",
        content="pending overdue",
        fingerprint="bddesc1",
        status="pending",
        operator=["zhang"],
        source_name="prometheus",
        team=[1],
    )
    task = EscalationService.create_escalation_task(alert, ctx["assignment"])
    # 初始分派人(zhang)的窗口 = 第一个升级层的 10 分钟；拨早 15 分钟使其超时
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
        operator=["zhang"],
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


@then("告警升级到第一个升级层并通知该层处理人")
def _at_first_escalation(ctx):
    # 有效链 [zhang, li, wang]：第0层(zhang)超时 -> 升到第1层(li)
    assert ctx["task"].current_layer_index == 1, (
        f"期望 current_layer_index=1，实际={ctx['task'].current_layer_index}"
    )


@then("第一个升级层处理人具备认领资格")
def _claimable(ctx):
    assert "li" in ctx["alert"].operator, (
        f"期望 li 在 operator 中，实际={ctx['alert'].operator}"
    )


@then("升级任务被停用且层级不变")
def _stopped(ctx):
    assert ctx["task"].is_active is False, (
        f"期望 is_active=False，实际={ctx['task'].is_active}"
    )
    assert ctx["task"].current_layer_index == 0, (
        f"期望 current_layer_index=0，实际={ctx['task'].current_layer_index}"
    )
