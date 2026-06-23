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
    return AlertSource.objects.create(
        name="源1", source_id="s-hook-test", source_type="restful", secret="x"
    )


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
def test_create_alert_triggers_dispatch_async_created(
    alert_levels, source, strategy, django_capture_on_commit_callbacks
):
    e1 = _make_event(source, "HOOK-E1")
    result = {
        "fingerprint": "fp-hook-new",
        "event_ids": ["HOOK-E1"],
        "alert_level": "1",
        "alert_title": "hook创建告警",
        "alert_description": "desc",
        "first_event_time": timezone.now(),
        "last_event_time": timezone.now(),
    }

    with patch(
        "apps.alerts.action.engine.ActionEngine.dispatch_async"
    ) as mock_dispatch:
        with django_capture_on_commit_callbacks(execute=True):
            with transaction.atomic():
                alert = AlertBuilder.create_or_update_alert(result, strategy, group_by_field="")

        mock_dispatch.assert_called_once_with(alert.alert_id, "created")


# ---------------------------------------------------------------------------
# (b) Acknowledge transition fires dispatch_async(alert_id, "acknowledged")
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_acknowledge_alert_triggers_dispatch_async_acknowledged(
    db, django_capture_on_commit_callbacks
):
    _make_alert(alert_id="HOOK-A2", status=AlertStatus.PENDING, operator=["op1"])
    op = AlertOperator(user="op1")

    with patch(
        "apps.alerts.action.engine.ActionEngine.dispatch_async"
    ) as mock_dispatch:
        with django_capture_on_commit_callbacks(execute=True):
            result = op.operate("acknowledge", "HOOK-A2", {})

    assert result["result"] is True
    mock_dispatch.assert_any_call("HOOK-A2", "acknowledged")


# ---------------------------------------------------------------------------
# (c) Resolve transition fires dispatch_async(alert_id, "resolved")
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_resolve_alert_triggers_dispatch_async_resolved(
    db, django_capture_on_commit_callbacks
):
    _make_alert(alert_id="HOOK-A3", status=AlertStatus.PROCESSING, operator=["op1"])
    op = AlertOperator(user="op1")

    with patch(
        "apps.alerts.action.engine.ActionEngine.dispatch_async"
    ) as mock_dispatch:
        with django_capture_on_commit_callbacks(execute=True):
            result = op.operate("resolve", "HOOK-A3", {"note": "done"})

    assert result["result"] is True
    mock_dispatch.assert_any_call("HOOK-A3", "resolved")


# ---------------------------------------------------------------------------
# (d) Close transition fires dispatch_async(alert_id, "closed")
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_close_alert_triggers_dispatch_async_closed(
    db, django_capture_on_commit_callbacks
):
    _make_alert(alert_id="HOOK-A4", status=AlertStatus.PROCESSING, operator=["op1"])
    op = AlertOperator(user="op1")

    with patch(
        "apps.alerts.action.engine.ActionEngine.dispatch_async"
    ) as mock_dispatch:
        with django_capture_on_commit_callbacks(execute=True):
            result = op.operate("close", "HOOK-A4", {"reason": "done"})

    assert result["result"] is True
    mock_dispatch.assert_any_call("HOOK-A4", "closed")
