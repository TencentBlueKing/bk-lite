"""Action engine lifecycle hook tests (service layer).

Verifies that ActionEngine.dispatch_async is called with the correct
(alert_id, event_name) after each alert creation / transition.

Uses pytest-django's django_capture_on_commit_callbacks so that
transaction.on_commit() callbacks actually fire inside tests.
"""

from unittest.mock import patch

import pytest
from django.db import transaction
from django.utils import timezone

from apps.alerts.aggregation.builder.alert_builder import AlertBuilder
from apps.alerts.constants.constants import AlertStatus, LevelType
from apps.alerts.models.alert_source import AlertSource
from apps.alerts.models.models import Alert, Event, Level
from apps.alerts.service.alter_operator import AlertOperator

# ---------------------------------------------------------------------------
# Shared fixtures (mirrors test_alert_builder.py / test_alert_operator.py)
# ---------------------------------------------------------------------------


@pytest.fixture
def alert_levels(db):
    AlertBuilder._valid_alert_levels = None
    for lid in (0, 1, 2):
        Level.objects.get_or_create(
            level_id=lid,
            defaults=dict(
                level_name=f"L{lid}",
                level_display_name=f"等级{lid}",
                level_type=LevelType.ALERT,
            ),
        )
    yield
    AlertBuilder._valid_alert_levels = None


@pytest.fixture
def source(db):
    return AlertSource.objects.create(name="源1", source_id="s-hook-test", source_type="restful", secret="x")


@pytest.fixture
def strategy(db):
    from apps.alerts.models.alert_operator import AlarmStrategy

    return AlarmStrategy.objects.create(
        name="hook策略",
        strategy_type="smart_denoise",
        team=[1],
        dispatch_team=[1],
        params={"window_size": 10},
    )


def _make_event(source, event_id, **over):
    defaults = dict(
        source=source,
        raw_data={},
        title="t",
        level="0",
        start_time=timezone.now(),
        event_id=event_id,
        item="cpu",
        resource_id="1",
        resource_name="host1",
        resource_type="host",
        service="svc",
        labels={},
    )
    defaults.update(over)
    return Event.objects.create(**defaults)


def _make_alert(alert_id="HOOK-A1", status=AlertStatus.UNASSIGNED, operator=None, team=None):
    return Alert.objects.create(
        alert_id=alert_id,
        level="0",
        title="hook-test",
        content="c",
        fingerprint=f"fp-{alert_id}",
        status=status,
        operator=operator or [],
        team=team or [1],
    )


# ---------------------------------------------------------------------------
# (a) Alert creation fires dispatch_async(alert_id, "created")
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_create_alert_triggers_dispatch_async_created(alert_levels, source, strategy, django_capture_on_commit_callbacks):
    _make_event(source, "HOOK-E1")
    result = {
        "fingerprint": "fp-hook-new",
        "event_ids": ["HOOK-E1"],
        "alert_level": "1",
        "alert_title": "hook创建告警",
        "alert_description": "desc",
        "first_event_time": timezone.now(),
        "last_event_time": timezone.now(),
    }

    with patch("apps.alerts.action.engine.ActionEngine.dispatch_async") as mock_dispatch:
        with django_capture_on_commit_callbacks(execute=True):
            with transaction.atomic():
                alert = AlertBuilder.create_or_update_alert(result, strategy, group_by_field="")

        mock_dispatch.assert_called_once_with(alert.alert_id, "created")


# ---------------------------------------------------------------------------
# (b) Acknowledge transition fires dispatch_async(alert_id, "acknowledged")
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_acknowledge_alert_triggers_dispatch_async_acknowledged(db, django_capture_on_commit_callbacks):
    _make_alert(alert_id="HOOK-A2", status=AlertStatus.PENDING, operator=["op1"])
    op = AlertOperator(user="op1")

    with patch("apps.alerts.action.engine.ActionEngine.dispatch_async") as mock_dispatch:
        with django_capture_on_commit_callbacks(execute=True):
            result = op.operate("acknowledge", "HOOK-A2", {})

    assert result["result"] is True
    mock_dispatch.assert_any_call("HOOK-A2", "acknowledged")


# ---------------------------------------------------------------------------
# (c) Resolve transition fires dispatch_async(alert_id, "resolved")
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_resolve_alert_triggers_dispatch_async_resolved(db, django_capture_on_commit_callbacks):
    _make_alert(alert_id="HOOK-A3", status=AlertStatus.PROCESSING, operator=["op1"])
    op = AlertOperator(user="op1")

    with patch("apps.alerts.action.engine.ActionEngine.dispatch_async") as mock_dispatch:
        with django_capture_on_commit_callbacks(execute=True):
            result = op.operate("resolve", "HOOK-A3", {"note": "done"})

    assert result["result"] is True
    mock_dispatch.assert_any_call("HOOK-A3", "resolved")


# ---------------------------------------------------------------------------
# (d) Close transition fires dispatch_async(alert_id, "closed")
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_close_alert_triggers_dispatch_async_closed(db, django_capture_on_commit_callbacks):
    _make_alert(alert_id="HOOK-A4", status=AlertStatus.PROCESSING, operator=["op1"])
    op = AlertOperator(user="op1")

    with patch("apps.alerts.action.engine.ActionEngine.dispatch_async") as mock_dispatch:
        with django_capture_on_commit_callbacks(execute=True):
            result = op.operate("close", "HOOK-A4", {"reason": "done"})

    assert result["result"] is True
    mock_dispatch.assert_any_call("HOOK-A4", "closed")


# ---------------------------------------------------------------------------
# (e) Assign transition fires dispatch_async(alert_id, "assigned")
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_assign_alert_triggers_dispatch_async_assigned(db, django_capture_on_commit_callbacks):
    from apps.system_mgmt.models.user import User

    User.objects.create(username="op1", domain="domain.com", group_list=[{"id": 1}])
    _make_alert(alert_id="HOOK-A5", status=AlertStatus.UNASSIGNED, team=[1])
    op = AlertOperator(user="system")

    with patch("apps.alerts.action.engine.ActionEngine.dispatch_async") as mock_dispatch:
        with django_capture_on_commit_callbacks(execute=True):
            result = op.operate("assign", "HOOK-A5", {"assignee": ["op1"]})

    assert result["result"] is True
    mock_dispatch.assert_any_call("HOOK-A5", "assigned")


# ---------------------------------------------------------------------------
# (f) Reassign transition fires dispatch_async(alert_id, "reassigned")
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_reassign_alert_triggers_dispatch_async_reassigned(db, django_capture_on_commit_callbacks):
    from apps.system_mgmt.models.user import User

    User.objects.create(username="op1", domain="domain.com", group_list=[{"id": 1}])
    _make_alert(alert_id="HOOK-A6", status=AlertStatus.PROCESSING, operator=["op1"], team=[1])
    op = AlertOperator(user="op1")

    with patch("apps.alerts.action.engine.ActionEngine.dispatch_async") as mock_dispatch:
        with django_capture_on_commit_callbacks(execute=True):
            result = op.operate("reassign", "HOOK-A6", {"assignee": ["op1"]})

    assert result["result"] is True
    mock_dispatch.assert_any_call("HOOK-A6", "reassigned")


# ---------------------------------------------------------------------------
# (g) 人工关闭后评估规则，处理动作里要留下 closed 记录
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
@patch("apps.alerts.action.engine.get_handler")
def test_close_alert_creates_closed_action_execution(mock_get, django_capture_on_commit_callbacks):
    from apps.alerts.action.engine import ActionEngine
    from apps.alerts.models.action import ActionExecution, ActionRule
    from apps.alerts.models.outbox import AlertOutbox
    from apps.alerts.service.outbox import deliver_outbox_record

    alert = _make_alert(alert_id="HOOK-A7", status=AlertStatus.PROCESSING, operator=["op1"], team=[1])
    ActionRule.objects.create(
        name="close-rule",
        is_active=True,
        team=[1],
        trigger_events=["created", "closed"],
        match_rules=[],
        action_type="job",
        action_config={"script_id": 1},
    )
    ActionEngine().evaluate(alert, "created")
    assert ActionExecution.objects.filter(alert=alert, trigger_event="created").count() == 1

    op = AlertOperator(user="op1")
    with patch("apps.alerts.tasks.deliver_alert_outbox.delay"):
        with django_capture_on_commit_callbacks(execute=True):
            result = op.operate("close", "HOOK-A7", {"reason": "done"})
    assert result["result"] is True

    record = AlertOutbox.objects.get(idempotency_key="action:HOOK-A7:closed")
    deliver_outbox_record(record.pk)

    assert ActionExecution.objects.filter(alert=alert, trigger_event="closed").count() == 1


# ---------------------------------------------------------------------------
# (h) 超时自动关闭也要派发 closed
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_auto_close_triggers_dispatch_async_closed(django_capture_on_commit_callbacks):
    from datetime import timedelta

    from apps.alerts.common.auto_close import AlertAutoClose
    from apps.alerts.models.alert_operator import AlarmStrategy

    strategy = AlarmStrategy.objects.create(
        name="auto-close-hook",
        strategy_type="smart_denoise",
        is_active=True,
        auto_close=True,
        close_minutes=60,
        team=[1],
    )
    now = timezone.now()
    alert = _make_alert(
        alert_id="HOOK-A8",
        status=AlertStatus.PROCESSING,
        operator=["op1"],
        team=[1],
    )
    Alert.objects.filter(pk=alert.pk).update(
        rule_id=str(strategy.id),
        first_event_time=now - timedelta(minutes=120),
        last_event_time=now - timedelta(minutes=120),
    )
    alert.refresh_from_db()

    with patch("apps.alerts.action.engine.ActionEngine.dispatch_async") as mock_dispatch:
        with django_capture_on_commit_callbacks(execute=True):
            assert AlertAutoClose().auto_close_alert(alert, strategy) is True

    mock_dispatch.assert_called_with("HOOK-A8", "closed")


# ---------------------------------------------------------------------------
# (i) 源侧恢复/关闭导致自动恢复时，要派发 resolved（对应勾选「恢复」）
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_auto_recovery_from_closed_event_triggers_dispatch_async_resolved(source, django_capture_on_commit_callbacks):
    from datetime import timedelta

    from apps.alerts.aggregation.recovery.recovery_checker import AlertRecoveryChecker
    from apps.alerts.constants.constants import EventAction

    created = _make_event(
        source,
        "HOOK-E-created",
        external_id="hook-ext-1",
        action=EventAction.CREATED,
        start_time=timezone.now() - timedelta(minutes=30),
    )
    closed = _make_event(
        source,
        "HOOK-E-closed",
        external_id="hook-ext-1",
        action=EventAction.CLOSED,
        start_time=timezone.now() - timedelta(minutes=5),
    )
    alert = _make_alert(alert_id="HOOK-A9", status=AlertStatus.PENDING, team=[1])
    alert.events.add(created, closed)

    with patch("apps.alerts.action.engine.ActionEngine.dispatch_async") as mock_dispatch:
        with django_capture_on_commit_callbacks(execute=True):
            assert AlertRecoveryChecker.check_and_recover_alert(alert) is True

    mock_dispatch.assert_called_with("HOOK-A9", "resolved")
