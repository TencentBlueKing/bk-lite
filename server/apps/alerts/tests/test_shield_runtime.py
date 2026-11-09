"""屏蔽策略当前结果：启用开关与生效时段分开。"""

import datetime
import json
from zoneinfo import ZoneInfo

import pytest
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.alerts.models.alert_operator import AlertShield
from apps.alerts.serializers.assignment_shield import AlertShieldModelSerializer
from apps.alerts.utils.shield_runtime import (
    RUNTIME_DISABLED,
    RUNTIME_EXPIRED,
    RUNTIME_NOT_STARTED,
    RUNTIME_OUTSIDE,
    RUNTIME_SHIELDING,
    classify_shield_runtime,
)
from apps.alerts.views.assignment_shield import AlertShieldModelViewSet

SHANGHAI = ZoneInfo("Asia/Shanghai")
NOW = datetime.datetime(2026, 10, 22, 10, 48, 0, tzinfo=SHANGHAI)


def _classify(is_active, suppression_time, created_by="alice"):
    return classify_shield_runtime(is_active, suppression_time, created_by, NOW)


def test_screenshot_rows_split_enablement_from_window(monkeypatch):
    monkeypatch.setattr("apps.alerts.utils.shield_runtime.resolve_display_timezone", lambda usernames: "Asia/Shanghai")
    month_days = {"type": "month", "week_month": [1, 3, 6, 5, 2, 28, 30, 31, 26, 24], "start_time": "02:00:00", "end_time": "23:59:59"}
    weekdays = {"type": "week", "week_month": [3, 5], "start_time": "03:00:02", "end_time": "23:59:59"}
    once = {"type": "one", "start_time": "2026-10-21 00:00:00", "end_time": "2026-11-21 23:59:59"}
    daily = {"type": "day", "start_time": "00:00:00", "end_time": "23:57:59"}

    assert _classify(True, month_days) == RUNTIME_OUTSIDE
    assert _classify(True, weekdays) == RUNTIME_OUTSIDE
    assert _classify(True, once) == RUNTIME_SHIELDING
    assert _classify(True, daily) == RUNTIME_SHIELDING
    assert _classify(False, once) == RUNTIME_DISABLED


def test_one_time_before_and_after(monkeypatch):
    monkeypatch.setattr("apps.alerts.utils.shield_runtime.resolve_display_timezone", lambda usernames: "Asia/Shanghai")
    config = {"type": "one", "start_time": "2026-10-21 00:00:00", "end_time": "2026-11-21 23:59:59"}

    before = datetime.datetime(2026, 10, 20, 23, 59, 59, tzinfo=SHANGHAI)
    after = datetime.datetime(2026, 11, 22, 0, 0, 0, tzinfo=SHANGHAI)
    assert classify_shield_runtime(True, config, "alice", before) == RUNTIME_NOT_STARTED
    assert classify_shield_runtime(True, config, "alice", after) == RUNTIME_EXPIRED


def test_daily_window_follows_creator_timezone(monkeypatch):
    config = {"type": "day", "start_time": "09:00:00", "end_time": "17:00:00"}
    # 02:00 UTC == 10:00 Asia/Shanghai
    moment = datetime.datetime(2026, 10, 22, 2, 0, 0, tzinfo=datetime.timezone.utc)

    monkeypatch.setattr("apps.alerts.utils.shield_runtime.resolve_display_timezone", lambda usernames: "Asia/Shanghai")
    assert classify_shield_runtime(True, config, "alice", moment) == RUNTIME_SHIELDING

    monkeypatch.setattr("apps.alerts.utils.shield_runtime.resolve_display_timezone", lambda usernames: "UTC")
    assert classify_shield_runtime(True, config, "alice", moment) == RUNTIME_OUTSIDE


def test_empty_window_is_always_shielding_when_enabled(monkeypatch):
    monkeypatch.setattr("apps.alerts.utils.shield_runtime.resolve_display_timezone", lambda usernames: "Asia/Shanghai")
    assert _classify(True, {}) == RUNTIME_SHIELDING


def test_malformed_one_time_is_outside(monkeypatch):
    monkeypatch.setattr("apps.alerts.utils.shield_runtime.resolve_display_timezone", lambda usernames: "Asia/Shanghai")
    assert _classify(True, {"type": "one", "start_time": "not-a-time", "end_time": "2026-11-21 23:59:59"}) == RUNTIME_OUTSIDE


def test_serializer_includes_creator_and_runtime_status(monkeypatch):
    monkeypatch.setattr("apps.alerts.utils.shield_runtime.timezone.now", lambda: NOW)
    monkeypatch.setattr("apps.alerts.utils.shield_runtime.resolve_display_timezone", lambda usernames: "Asia/Shanghai")
    shield = AlertShield(
        name="单次窗口内",
        match_type="all",
        suppression_time={"type": "one", "start_time": "2026-10-21 00:00:00", "end_time": "2026-11-21 23:59:59"},
        is_active=True,
        created_by="alice",
    )

    data = AlertShieldModelSerializer(shield).data

    assert data["created_by"] == "alice"
    assert data["runtime_status"] == RUNTIME_SHIELDING


@pytest.fixture
def superuser(authenticated_user):
    authenticated_user.is_superuser = True
    return authenticated_user


def _render(response):
    response.render()
    return json.loads(response.content)


@pytest.mark.django_db
def test_shield_list_returns_creator_and_runtime_status(superuser, monkeypatch):
    monkeypatch.setattr("apps.alerts.utils.shield_runtime.timezone.now", lambda: NOW)
    AlertShield.objects.create(
        name="单次窗口内",
        match_type="all",
        suppression_time={"type": "one", "start_time": "2026-10-21 00:00:00", "end_time": "2026-11-21 23:59:59"},
        is_active=True,
        created_by="alice",
    )
    AlertShield.objects.create(
        name="已停用",
        match_type="all",
        suppression_time={"type": "day", "start_time": "00:00:00", "end_time": "23:59:59"},
        is_active=False,
        created_by="bob",
    )

    factory = APIRequestFactory()
    request = factory.get("/shield/")
    force_authenticate(request, user=superuser)
    response = AlertShieldModelViewSet.as_view({"get": "list"})(request)
    payload = _render(response)
    data = payload["data"]
    items = data["items"] if isinstance(data, dict) else data
    by_name = {item["name"]: item for item in items}

    assert response.status_code == status.HTTP_200_OK
    assert by_name["单次窗口内"]["created_by"] == "alice"
    assert by_name["单次窗口内"]["runtime_status"] == RUNTIME_SHIELDING
    assert by_name["已停用"]["created_by"] == "bob"
    assert by_name["已停用"]["runtime_status"] == RUNTIME_DISABLED
