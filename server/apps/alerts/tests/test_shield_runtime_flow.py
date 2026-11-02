"""屏蔽策略的当前结果必须和实际屏蔽一致。

列表、详情返回的 runtime_status 就是这次屏蔽检查会不会把匹配事件置为屏蔽。
创建人原样返回，时段按创建人账号时区解释。
"""

import datetime
import json
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.alerts.common.shield import execute_shield_check_for_events
from apps.alerts.constants.constants import EventStatus
from apps.alerts.models.alert_operator import AlertShield
from apps.alerts.models.alert_source import AlertSource
from apps.alerts.models.models import Event
from apps.alerts.views.assignment_shield import AlertShieldModelViewSet
from apps.system_mgmt.models.user import User

SHANGHAI = ZoneInfo("Asia/Shanghai")
NOW = datetime.datetime(2026, 10, 22, 10, 48, 0, tzinfo=SHANGHAI)


@pytest.fixture
def superuser(authenticated_user):
    authenticated_user.is_superuser = True
    return authenticated_user


@pytest.fixture
def source(db):
    return AlertSource.objects.create(name="源1", source_id="shield-flow", source_type="restful", secret="x")


@pytest.fixture
def frozen_shield_clock(monkeypatch):
    monkeypatch.setattr("apps.alerts.utils.shield_runtime.timezone.now", lambda: NOW)
    monkeypatch.setattr("apps.alerts.common.shield.timezone.now", lambda: NOW)


def _render(response):
    response.render()
    return json.loads(response.content)


def _call(superuser, method, path, action, data=None, **kwargs):
    factory = APIRequestFactory()
    request = getattr(factory, method)(path, data=data, format="json") if data is not None else getattr(factory, method)(path)
    force_authenticate(request, user=superuser)
    response = AlertShieldModelViewSet.as_view({method: action})(request, **kwargs)
    body = _render(response)
    assert body["result"] is True, body
    return body["data"]


def _event(source, event_id):
    return Event.objects.create(
        source=source,
        raw_data={},
        title="t",
        level="0",
        start_time=timezone.now(),
        event_id=event_id,
        status=EventStatus.RECEIVED,
    )


def _owner(username, tz_name):
    return User.objects.create(
        username=username,
        display_name=username,
        email=f"{username}@example.com",
        password="x",
        timezone=tz_name,
        domain="shield-flow.example",
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("name", "window", "is_active", "creator", "status", "shields_event"),
    [
        (
            "每月不含今天",
            {"type": "month", "week_month": [1, 3, 6, 5, 2, 28, 30, 31, 26, 24], "start_time": "02:00:00", "end_time": "23:59:59"},
            True,
            "alice",
            "outside",
            False,
        ),
        (
            "每周三五",
            {"type": "week", "week_month": [5, 3], "start_time": "03:00:02", "end_time": "23:59:59"},
            True,
            "alice",
            "outside",
            False,
        ),
        (
            "单次窗口内",
            {"type": "one", "start_time": "2026-10-21 00:00:00", "end_time": "2026-11-21 23:59:59"},
            True,
            "bob",
            "shielding",
            True,
        ),
        (
            "每天几乎全天",
            {"type": "day", "start_time": "00:00:00", "end_time": "23:57:59"},
            True,
            "alice",
            "shielding",
            True,
        ),
        (
            "单次未开始",
            {"type": "one", "start_time": "2026-10-22 10:48:01", "end_time": "2026-11-21 23:59:59"},
            True,
            "alice",
            "not_started",
            False,
        ),
        (
            "单次刚结束",
            {"type": "one", "start_time": "2026-10-21 00:00:00", "end_time": "2026-10-22 10:47:59"},
            True,
            "alice",
            "expired",
            False,
        ),
        (
            "单次正好开始",
            {"type": "one", "start_time": "2026-10-22 10:48:00", "end_time": "2026-10-22 11:00:00"},
            True,
            "alice",
            "shielding",
            True,
        ),
        (
            "开关关闭",
            {"type": "day", "start_time": "00:00:00", "end_time": "23:59:59"},
            False,
            "alice",
            "disabled",
            False,
        ),
        (
            "未配时段",
            {},
            True,
            "alice",
            "shielding",
            True,
        ),
    ],
)
def test_list_and_detail_status_match_whether_the_event_is_shielded(
    source,
    superuser,
    frozen_shield_clock,
    name,
    window,
    is_active,
    creator,
    status,
    shields_event,
):
    event = _event(source, f"E-{name}")
    shield = AlertShield.objects.create(
        name=name,
        match_type="all",
        match_rules=[],
        suppression_time=window,
        is_active=is_active,
        created_by=creator,
    )

    result = execute_shield_check_for_events([event.event_id])
    event.refresh_from_db()
    list_data = _list(superuser)
    detail = _call(superuser, "get", f"/shield/{shield.id}/", "retrieve", pk=str(shield.id))

    row = list_data[name]
    assert row["created_by"] == creator
    assert row["runtime_status"] == status
    assert detail["created_by"] == creator
    assert detail["runtime_status"] == status
    assert detail["is_active"] is is_active
    if shields_event:
        assert event.status == EventStatus.SHIELD
        assert result["shielded_events"] == 1
    else:
        assert event.status == EventStatus.RECEIVED
        assert result["shielded_events"] == 0


def _list(superuser):
    data = _call(superuser, "get", "/shield/", "list")
    items = data["items"] if isinstance(data, dict) else data
    return {item["name"]: item for item in items}


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("tz_name", "status", "shields_event"),
    [
        ("UTC", "outside", False),
        ("Asia/Shanghai", "shielding", True),
    ],
)
def test_creator_timezone_decides_status_and_shielding(source, superuser, frozen_shield_clock, tz_name, status, shields_event):
    username = "utc-owner" if tz_name == "UTC" else "sh-owner"
    _owner(username, tz_name)
    event = _event(source, f"E-{tz_name}")
    shield = AlertShield.objects.create(
        name=f"按时区-{tz_name}",
        match_type="all",
        match_rules=[],
        suppression_time={"type": "day", "start_time": "09:00:00", "end_time": "17:00:00"},
        is_active=True,
        created_by=username,
    )

    execute_shield_check_for_events([event.event_id])
    event.refresh_from_db()
    detail = _call(superuser, "get", f"/shield/{shield.id}/", "retrieve", pk=str(shield.id))

    assert detail["runtime_status"] == status
    assert detail["created_by"] == username
    assert (event.status == EventStatus.SHIELD) is shields_event


@pytest.mark.django_db
def test_out_of_window_shield_does_not_block_an_in_window_shield(source, superuser, frozen_shield_clock):
    event = _event(source, "E-both")
    AlertShield.objects.create(
        name="今天不在每月",
        match_type="all",
        suppression_time={"type": "month", "week_month": [1], "start_time": "00:00:00", "end_time": "23:59:59"},
        is_active=True,
        created_by="alice",
    )
    AlertShield.objects.create(
        name="全天仍生效",
        match_type="all",
        suppression_time={"type": "day", "start_time": "00:00:00", "end_time": "23:59:59"},
        is_active=True,
        created_by="bob",
    )

    result = execute_shield_check_for_events([event.event_id])
    event.refresh_from_db()
    listed = _list(superuser)

    assert result["shielded_events"] == 1
    assert event.status == EventStatus.SHIELD
    assert listed["今天不在每月"]["runtime_status"] == "outside"
    assert listed["全天仍生效"]["runtime_status"] == "shielding"


@pytest.mark.django_db
def test_turning_shield_off_stops_later_events_and_keeps_creator(source, superuser, frozen_shield_clock):
    shield = AlertShield.objects.create(
        name="可停用",
        match_type="all",
        suppression_time={"type": "day", "start_time": "00:00:00", "end_time": "23:59:59"},
        is_active=True,
        created_by="alice",
    )
    first = _event(source, "E-before-off")
    execute_shield_check_for_events([first.event_id])
    first.refresh_from_db()
    assert first.status == EventStatus.SHIELD

    updated = _call(superuser, "patch", f"/shield/{shield.id}/", "partial_update", data={"is_active": False}, pk=str(shield.id))
    assert updated["is_active"] is False
    assert updated["runtime_status"] == "disabled"
    assert updated["created_by"] == "alice"

    second = _event(source, "E-after-off")
    result = execute_shield_check_for_events([second.event_id])
    second.refresh_from_db()
    detail = _call(superuser, "get", f"/shield/{shield.id}/", "retrieve", pk=str(shield.id))

    assert result["shielded_events"] == 0
    assert second.status == EventStatus.RECEIVED
    assert detail["runtime_status"] == "disabled"
    assert detail["created_by"] == "alice"
