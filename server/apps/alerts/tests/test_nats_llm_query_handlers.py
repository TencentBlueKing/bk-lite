"""告警中心 LLM 查询 NATS handler 契约。"""

import pytest

from apps.alerts.constants.constants import AlertStatus, SessionStatus
from apps.alerts.models.models import Alert
from apps.alerts.nats import nats as alerts_nats

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
