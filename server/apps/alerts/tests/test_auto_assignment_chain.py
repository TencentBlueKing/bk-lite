"""聚合→outbox→分派链路字段一致性验证测试（2026-07-24）。

验证点：
1. 聚合路径传递的是 Alert.alert_id（业务 ID），投递后 AlertAssignmentOperator
   以 alert_id__in 查询——字段与 ID 空间一致，链路应正常分派。
2. 当载荷中的 alert_id 在库中不存在时（历史残留 outbox 记录，告警已删除），
   属于终态：WARNING 记录缺失 id，不产生 ERROR，outbox 正常标 DELIVERED。
"""

import logging

import pytest
from django.utils import timezone

from apps.alerts.aggregation.processor.aggregation_processor import AggregationProcessor
from apps.alerts.common.assignment import AlertAssignmentOperator
from apps.alerts.constants.constants import AlertStatus
from apps.alerts.models.models import Alert
from apps.alerts.models.outbox import AlertOutbox
from apps.alerts.service.outbox import deliver_outbox_record, enqueue_outbox
from apps.alerts.service.alter_operator import AlertOperator


@pytest.fixture
def sys_user(db):
    from apps.system_mgmt.models.user import User

    return User.objects.create(username="op1", domain="domain.com", group_list=[{"id": 1}])


def _make_alert(alert_id="ALERT-CHAIN1", status=AlertStatus.UNASSIGNED, **over):
    defaults = dict(
        alert_id=alert_id, level="0", title="CPU高", content="c",
        fingerprint="fp" + alert_id, status=status, source_name="prometheus",
        team=[1],
    )
    defaults.update(over)
    return Alert.objects.create(**defaults)


def _make_assignment(name="分派", match_type="all", **over):
    from apps.alerts.models.alert_operator import AlertAssignment

    defaults = dict(
        name=name, match_type=match_type, is_active=True, personnel=["op1"],
        match_rules=[], config={}, notify_channels=[], notification_scenario=[],
        notification_frequency={},
    )
    defaults.update(over)
    return AlertAssignment.objects.create(**defaults)


@pytest.mark.django_db
def test_aggregation_to_delivery_chain_assigns_alert(sys_user):
    """聚合路径传 alert_id → outbox 载荷 → 投递 → 分派成功（字段一致性正向验证）。"""
    alert = _make_alert()
    _make_assignment(match_type="all")

    # 走聚合处理器真实的调度入口
    AggregationProcessor._schedule_auto_assignment([alert.alert_id])

    record = AlertOutbox.objects.get(kind="auto_assignment")
    assert record.payload["alert_ids"] == [alert.alert_id]

    delivered = deliver_outbox_record(record.pk)
    assert delivered is True

    alert.refresh_from_db()
    # all 匹配策略应把 UNASSIGNED 告警分派出去（状态离开 UNASSIGNED）
    assert alert.status != AlertStatus.UNASSIGNED
    assert alert.operator == ["op1"]


@pytest.mark.django_db
def test_delivery_with_missing_alert_id_is_terminal_without_error(caplog):
    """alert_id 全部查无此行（历史残留）：终态处理——WARNING、无 ERROR、DELIVERED。"""
    caplog.set_level(logging.DEBUG, logger="alert")
    enqueue_outbox(
        "auto_assignment",
        {"alert_ids": ["ALERT-NOT-EXIST"]},
        "auto-assignment:created:repro-missing",
    )
    record = AlertOutbox.objects.get(kind="auto_assignment")

    delivered = deliver_outbox_record(record.pk)

    record.refresh_from_db()
    assert delivered is True
    assert record.status == AlertOutbox.Status.DELIVERED
    # 缺失 id 必须可见（WARNING），但不允许出现 ERROR
    assert "ALERT-NOT-EXIST" in caplog.text
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]


@pytest.mark.django_db
def test_delivery_with_partially_missing_alert_ids_assigns_existing(sys_user, caplog):
    """部分 id 缺失：存在的告警照常分派，缺失 id 记 WARNING，无 ERROR。"""
    caplog.set_level(logging.DEBUG, logger="alert")
    alert = _make_alert("ALERT-EXISTS")
    _make_assignment(match_type="all")
    enqueue_outbox(
        "auto_assignment",
        {"alert_ids": ["ALERT-EXISTS", "ALERT-GONE"]},
        "auto-assignment:created:repro-partial",
    )
    record = AlertOutbox.objects.get(kind="auto_assignment")

    delivered = deliver_outbox_record(record.pk)

    assert delivered is True
    alert.refresh_from_db()
    assert alert.operator == ["op1"]
    assert "ALERT-GONE" in caplog.text
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]


def _raise_runtime_error(alert_ids):
    raise RuntimeError("db down")


@pytest.mark.django_db
def test_delivery_with_transient_error_marks_pending_for_retry(monkeypatch):
    """非终态错误（如 DB 抖动）：必须冒泡 → outbox 回 PENDING + 退避 + last_error，可重试。"""
    monkeypatch.setattr(
        "apps.alerts.common.assignment.execute_auto_assignment_for_alerts",
        _raise_runtime_error,
    )
    enqueue_outbox(
        "auto_assignment",
        {"alert_ids": ["ALERT-X"]},
        "auto-assignment:created:repro-transient-error",
    )
    record = AlertOutbox.objects.get(kind="auto_assignment")

    with pytest.raises(RuntimeError):
        deliver_outbox_record(record.pk)

    record.refresh_from_db()
    assert record.status == AlertOutbox.Status.PENDING
    assert record.attempts == 1
    assert "db down" in record.last_error
    assert record.next_retry_at is not None
    assert record.next_retry_at > timezone.now()


@pytest.mark.django_db
def test_delivery_with_internal_matching_error_marks_pending_for_retry(monkeypatch):
    """策略匹配内部的运行异常也必须冒泡，不能被翻译成一次成功投递。"""
    alert = _make_alert("ALERT-INTERNAL-ERROR")
    _make_assignment(match_type="all")

    def fail_matching(self, assignment, excluded_ids=None):
        raise RuntimeError("transient matching failure")

    monkeypatch.setattr(
        AlertAssignmentOperator, "_batch_find_matching_alerts", fail_matching
    )
    enqueue_outbox(
        "auto_assignment",
        {"alert_ids": [alert.alert_id]},
        "auto-assignment:created:repro-internal-error",
    )
    record = AlertOutbox.objects.get(kind="auto_assignment")

    with pytest.raises(RuntimeError, match="transient matching failure"):
        deliver_outbox_record(record.pk)

    record.refresh_from_db()
    assert record.status == AlertOutbox.Status.PENDING
    assert record.attempts == 1
    assert "transient matching failure" in record.last_error
    assert record.next_retry_at is not None


@pytest.mark.django_db
def test_delivery_with_internal_assign_error_marks_pending_for_retry(
    sys_user, monkeypatch
):
    """单条分派执行的运行异常必须冒泡，让整个载荷稍后安全重试。"""
    alert = _make_alert("ALERT-ASSIGN-ERROR")
    _make_assignment(match_type="all")

    def fail_assignment(self, action, alert_id, data):
        raise RuntimeError("transient assign failure")

    monkeypatch.setattr(AlertOperator, "operate", fail_assignment)
    enqueue_outbox(
        "auto_assignment",
        {"alert_ids": [alert.alert_id]},
        "auto-assignment:created:repro-assign-error",
    )
    record = AlertOutbox.objects.get(kind="auto_assignment")

    with pytest.raises(RuntimeError, match="transient assign failure"):
        deliver_outbox_record(record.pk)

    record.refresh_from_db()
    alert.refresh_from_db()
    assert record.status == AlertOutbox.Status.PENDING
    assert record.attempts == 1
    assert "transient assign failure" in record.last_error
    assert alert.status == AlertStatus.UNASSIGNED


@pytest.mark.django_db
def test_delivery_with_persistent_error_marks_failed_after_max_attempts(monkeypatch):
    """持续失败累计到 max_attempts 后标 FAILED 终态，错误留痕不再自动重投。"""
    monkeypatch.setattr(
        "apps.alerts.common.assignment.execute_auto_assignment_for_alerts",
        _raise_runtime_error,
    )
    enqueue_outbox(
        "auto_assignment",
        {"alert_ids": ["ALERT-X"]},
        "auto-assignment:created:repro-persistent-error",
    )
    record = AlertOutbox.objects.get(kind="auto_assignment")
    record.attempts = record.max_attempts - 1
    record.save(update_fields=["attempts"])

    with pytest.raises(RuntimeError):
        deliver_outbox_record(record.pk)

    record.refresh_from_db()
    assert record.status == AlertOutbox.Status.FAILED
    assert record.attempts == record.max_attempts
    assert "db down" in record.last_error
