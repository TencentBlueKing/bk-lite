"""告警中心 LLM 查询 NATS handler 契约。"""

import datetime

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.alerts.constants.constants import AlertStatus, SessionStatus
from apps.alerts.models.alert_source import AlertSource
from apps.alerts.models.models import Alert, Event
from apps.alerts.nats import nats as alerts_nats
from apps.alerts.notification_templates.timefmt import format_template_datetime
from apps.system_mgmt.models.user import User

pytestmark = pytest.mark.django_db


def _user_info(*, is_superuser=True, team=1):
    return {
        "user": "admin",
        "domain": "domain.com",
        "team": team,
        "include_children": False,
        "is_superuser": is_superuser,
        "permission": {"alarm": ["Alarms-View"]},
    }


def test_list_alerts_requires_team():
    result = alerts_nats.list_alerts(query_data={}, user_info={"user": "admin", "domain": "d.com"})
    assert result["result"] is False
    assert "组织" in result["message"]


def test_list_alerts_returns_authorized_rows(mocker):
    mocker.patch.object(alerts_nats, "_llm_is_superuser", return_value=True)
    Alert.objects.create(
        alert_id="ALERT-LLM-1",
        title="cpu high",
        content="c",
        status=AlertStatus.UNASSIGNED,
        level="critical",
        fingerprint="fp1",
        team=[1],
        session_status=SessionStatus.CONFIRMED,
    )
    result = alerts_nats.list_alerts(query_data={"keyword": "cpu"}, user_info=_user_info())
    assert result["result"] is True
    assert result["data"]["count"] == 1
    assert result["data"]["items"][0]["alert_id"] == "ALERT-LLM-1"


def test_list_alerts_matches_content_and_any_keyword(mocker):
    mocker.patch.object(alerts_nats, "_llm_is_superuser", return_value=True)
    Alert.objects.create(
        alert_id="ALERT-LLM-BODY",
        title="商城页面变慢",
        content="upstream connection refused while connecting",
        status=AlertStatus.UNASSIGNED,
        level="warning",
        fingerprint="fp-body",
        team=[1],
        session_status=SessionStatus.CONFIRMED,
    )
    Alert.objects.create(
        alert_id="ALERT-LLM-OTHER",
        title="磁盘满",
        content="inode",
        status=AlertStatus.UNASSIGNED,
        level="warning",
        fingerprint="fp-other",
        team=[1],
        session_status=SessionStatus.CONFIRMED,
    )
    by_content = alerts_nats.list_alerts(query_data={"keyword": "connection refused"}, user_info=_user_info())
    assert [item["alert_id"] for item in by_content["data"]["items"]] == ["ALERT-LLM-BODY"]
    by_or = alerts_nats.list_alerts(query_data={"keywords": ["502", "商城"]}, user_info=_user_info())
    assert [item["alert_id"] for item in by_or["data"]["items"]] == ["ALERT-LLM-BODY"]


def test_list_alerts_active_status_matches_open_alerts_only(mocker):
    mocker.patch.object(alerts_nats, "_llm_is_superuser", return_value=True)
    Alert.objects.create(
        alert_id="ALERT-LLM-OPEN",
        title="磁盘使用率过高",
        content="活动告警",
        status=AlertStatus.PENDING,
        level="warning",
        fingerprint="fp-open",
        team=[1],
        session_status=SessionStatus.CONFIRMED,
    )
    Alert.objects.create(
        alert_id="ALERT-LLM-CLOSED",
        title="磁盘已关闭",
        content="已关闭",
        status=AlertStatus.CLOSED,
        level="warning",
        fingerprint="fp-closed",
        team=[1],
        session_status=SessionStatus.CONFIRMED,
    )
    result = alerts_nats.list_alerts(query_data={"status": "active"}, user_info=_user_info())
    assert result["result"] is True
    assert [item["alert_id"] for item in result["data"]["items"]] == ["ALERT-LLM-OPEN"]


def test_list_alerts_includes_alerts_assigned_to_caller_outside_current_team(mocker):
    mocker.patch.object(alerts_nats, "_llm_is_superuser", return_value=True)
    Alert.objects.create(
        alert_id="ALERT-LLM-HOME",
        title="本组织未分派",
        content="c",
        status=AlertStatus.UNASSIGNED,
        level="warning",
        fingerprint="fp-home",
        team=[1],
        operator=[],
        session_status=SessionStatus.CONFIRMED,
    )
    Alert.objects.create(
        alert_id="ALERT-LLM-ASSIGNED",
        title="其他组织分派给我",
        content="c",
        status=AlertStatus.PENDING,
        level="warning",
        fingerprint="fp-assigned",
        team=[2],
        operator=["admin"],
        session_status=SessionStatus.CONFIRMED,
    )
    Alert.objects.create(
        alert_id="ALERT-LLM-FOREIGN",
        title="其他组织未分派",
        content="c",
        status=AlertStatus.PENDING,
        level="warning",
        fingerprint="fp-foreign",
        team=[2],
        operator=[],
        session_status=SessionStatus.CONFIRMED,
    )
    Alert.objects.create(
        alert_id="ALERT-LLM-SUBSTRING",
        title="用户名子串不算分派",
        content="c",
        status=AlertStatus.PENDING,
        level="warning",
        fingerprint="fp-substring",
        team=[2],
        operator=["admin-extra"],
        session_status=SessionStatus.CONFIRMED,
    )
    result = alerts_nats.list_alerts(query_data={"status": "active"}, user_info=_user_info())
    assert result["result"] is True
    assert {item["alert_id"] for item in result["data"]["items"]} == {"ALERT-LLM-HOME", "ALERT-LLM-ASSIGNED"}


def test_get_alert_detail_not_found(mocker):
    mocker.patch.object(alerts_nats, "_llm_is_superuser", return_value=True)
    result = alerts_nats.get_alert_detail(alert_id="ALERT-MISSING", user_info=_user_info())
    assert result["result"] is False
    assert "不存在" in result["message"]


def test_list_alerts_identity_without_view_blob_still_queries(mocker):
    mocker.patch.object(alerts_nats, "_llm_is_superuser", return_value=True)
    Alert.objects.create(
        alert_id="ALERT-LLM-2",
        title="disk full",
        content="c",
        status=AlertStatus.UNASSIGNED,
        level="warning",
        fingerprint="fp2",
        team=[1],
        session_status=SessionStatus.CONFIRMED,
    )
    result = alerts_nats.list_alerts(
        query_data={},
        user_info={"user": "admin", "domain": "domain.com", "team": 1, "include_children": False},
    )
    assert result["result"] is True
    assert result["data"]["count"] == 1


def test_list_alert_events_requires_alert_id():
    result = alerts_nats.list_alert_events(alert_id="", user_info=_user_info())
    assert result["result"] is False
    assert "alert_id" in result["message"]


_CALLER_USERNAME = "tz-caller"
_CALLER_TIMEZONE = "America/New_York"
_EXPLICIT_TIMEZONE = "Europe/Berlin"
_PAGE_TIME = datetime.datetime(2026, 1, 15, 0, 0, tzinfo=datetime.timezone.utc)


def _caller_user_info(**extra):
    info = _user_info()
    info["user"] = _CALLER_USERNAME
    info.update(extra)
    return info


def _user_timezone_lookup_count(captured):
    """Count resolve_display_timezone reads: user row selected by username IN, including timezone."""
    count = 0
    for query in captured.captured_queries:
        sql = " ".join(query["sql"].split()).lower()
        if "system_mgmt_user" in sql and "timezone" in sql and " in (" in sql:
            count += 1
    return count


def _capture_timezone_lookups(callback):
    with CaptureQueriesContext(connection) as captured:
        result = callback()
    return _user_timezone_lookup_count(captured), result


def _create_caller():
    return User.objects.create(
        username=_CALLER_USERNAME,
        display_name="TZ Caller",
        email="tz-caller@example.com",
        password="x",
        domain="domain.com",
        timezone=_CALLER_TIMEZONE,
    )


def _create_alert_page():
    alerts = [
        Alert.objects.create(
            alert_id=f"ALERT-LLM-TZ-{index}",
            title=f"tz alert {index}",
            content="c",
            status=AlertStatus.UNASSIGNED,
            level="warning",
            fingerprint=f"fp-tz-{index}",
            team=[1],
            session_status=SessionStatus.CONFIRMED,
        )
        for index in range(20)
    ]
    Alert.objects.filter(pk__in=[alert.pk for alert in alerts]).update(
        created_at=_PAGE_TIME,
        updated_at=_PAGE_TIME,
        first_event_time=_PAGE_TIME,
        last_event_time=_PAGE_TIME,
    )
    return alerts


def _create_event_page(alert):
    source = AlertSource.objects.create(name="tz-source", source_id="src-llm-tz", source_type="restful", secret="x")
    events = [
        Event.objects.create(
            source=source,
            raw_data={},
            title=f"event-{index}",
            level="0",
            start_time=_PAGE_TIME,
            event_id=f"E-LLM-TZ-{index}",
        )
        for index in range(20)
    ]
    Event.objects.filter(pk__in=[event.pk for event in events]).update(received_at=_PAGE_TIME)
    alert.events.add(*events)
    return events


def test_list_pages_lookup_caller_timezone_once(mocker):
    mocker.patch.object(alerts_nats, "_llm_is_superuser", return_value=True)
    _create_caller()
    alerts = _create_alert_page()
    _create_event_page(alerts[0])
    event_alert_id = alerts[0].alert_id
    empty_event_alert_id = alerts[1].alert_id

    def _alerts(page_size, **user_extra):
        return alerts_nats.list_alerts(
            query_data={"page": 1, "page_size": page_size},
            user_info=_caller_user_info(**user_extra),
        )

    def _events(alert_id, page_size, **user_extra):
        return alerts_nats.list_alert_events(
            alert_id=alert_id,
            query_data={"page": 1, "page_size": page_size},
            user_info=_caller_user_info(**user_extra),
        )

    alert_counts = {}
    alert_pages = {}
    event_counts = {}
    event_pages = {}
    for page_size in (2, 20):
        alert_counts[page_size], alert_pages[page_size] = _capture_timezone_lookups(lambda page_size=page_size: _alerts(page_size))
        event_counts[page_size], event_pages[page_size] = _capture_timezone_lookups(
            lambda page_size=page_size: _events(event_alert_id, page_size)
        )

    empty_alert_count, empty_alerts = _capture_timezone_lookups(lambda: _alerts(20, team=2))
    empty_event_count, empty_events = _capture_timezone_lookups(lambda: _events(empty_event_alert_id, 20))
    explicit_alert_count, explicit_alerts = _capture_timezone_lookups(lambda: _alerts(2, timezone=_EXPLICIT_TIMEZONE))
    explicit_event_count, explicit_events = _capture_timezone_lookups(
        lambda: _events(event_alert_id, 2, timezone=_EXPLICIT_TIMEZONE)
    )

    observed = {
        "list_alerts": alert_counts,
        "list_alert_events": event_counts,
        "empty_list_alerts": empty_alert_count,
        "empty_list_alert_events": empty_event_count,
        "explicit_list_alerts": explicit_alert_count,
        "explicit_list_alert_events": explicit_event_count,
    }
    expected = {
        "list_alerts": {2: 1, 20: 1},
        "list_alert_events": {2: 1, 20: 1},
        "empty_list_alerts": 0,
        "empty_list_alert_events": 0,
        "explicit_list_alerts": 0,
        "explicit_list_alert_events": 0,
    }
    assert observed == expected, f"TIMEZONE_LOOKUP_COUNTS {observed}"

    account_time = format_template_datetime(_PAGE_TIME, _CALLER_TIMEZONE)
    explicit_time = format_template_datetime(_PAGE_TIME, _EXPLICIT_TIMEZONE)
    assert account_time != explicit_time
    assert [item["created_at"] for item in alert_pages[2]["data"]["items"]] == [account_time, account_time]
    assert [item["created_at"] for item in alert_pages[20]["data"]["items"]] == [account_time] * 20
    assert [item["received_at"] for item in event_pages[2]["data"]["items"]] == [account_time, account_time]
    assert [item["received_at"] for item in event_pages[20]["data"]["items"]] == [account_time] * 20
    assert [item["created_at"] for item in explicit_alerts["data"]["items"]] == [explicit_time, explicit_time]
    assert [item["received_at"] for item in explicit_events["data"]["items"]] == [explicit_time, explicit_time]
    assert empty_alerts["data"]["items"] == []
    assert empty_events["data"]["items"] == []
