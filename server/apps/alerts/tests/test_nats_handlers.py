"""告警中心 NATS RPC 统计处理器与辅助函数覆盖测试。

对照 spec/prd/告警中心：运营统计（趋势/分布/TOP）按组织与权限范围聚合。
"""

import datetime

import pytest
from django.utils import timezone

from apps.alerts.constants.constants import AlertStatus, LevelType
from apps.alerts.models.models import Alert, Level
from apps.alerts.nats import nats as N

# --------------------------------------------------------------------------
# 纯辅助函数
# --------------------------------------------------------------------------


def test_has_alerts_view_permission_superuser():
    assert N._has_alerts_view_permission({"is_superuser": True}) is True


def test_has_alerts_view_permission_dict_perm():
    assert N._has_alerts_view_permission({"permission": {"alarm": ["Alarms-View"]}}) is True
    assert N._has_alerts_view_permission({"permission": {"alarm": ["Other"]}}) is False


def test_has_alerts_view_permission_list_perm():
    assert N._has_alerts_view_permission({"permission": ["Alarms-View"]}) is True


def test_has_alerts_view_permission_none():
    assert N._has_alerts_view_permission(None) is False


def test_group_dy_date_format_variants():
    from django.db.models.functions import TruncDate, TruncHour

    trunc, fmt = N.group_dy_date_format("hour")
    assert trunc is TruncHour
    trunc2, fmt2 = N.group_dy_date_format("unknown")
    assert trunc2 is TruncDate


def test_group_dy_date_format_all_branches():
    from django.db.models.functions import TruncMinute, TruncMonth, TruncWeek

    assert N.group_dy_date_format("minute")[0] is TruncMinute
    assert N.group_dy_date_format("week")[0] is TruncWeek
    assert N.group_dy_date_format("month")[0] is TruncMonth


def test_generate_time_periods_minute_week_month():
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.datetime(2026, 1, 1, 0, 0), tz)
    end = timezone.make_aware(datetime.datetime(2026, 1, 1, 0, 3), tz)
    assert len(N._generate_time_periods("minute", start, end)) == 3

    wk_end = timezone.make_aware(datetime.datetime(2026, 1, 20), tz)
    assert len(N._generate_time_periods("week", start, wk_end)) >= 2

    mo_end = timezone.make_aware(datetime.datetime(2026, 4, 1), tz)
    assert len(N._generate_time_periods("month", start, mo_end)) >= 3


def test_format_period_value_aware_and_naive():
    tz = timezone.get_current_timezone()
    aware = timezone.make_aware(datetime.datetime(2026, 1, 1, 10, 0), tz)
    assert "2026-01-01" in N._format_period_value(aware, tz)
    naive = datetime.datetime(2026, 1, 1, 10, 0)
    assert "2026-01-01" in N._format_period_value(naive, tz)


def test_resolve_target_timezone_valid():
    tz = N._resolve_target_timezone("Asia/Shanghai")
    assert tz is not None


def test_resolve_target_timezone_invalid_falls_back():
    tz = N._resolve_target_timezone("Not/AZone")
    assert tz == timezone.get_current_timezone()


def test_parse_client_datetime_iso():
    tz = timezone.get_current_timezone()
    dt = N._parse_client_datetime("2026-01-01T10:00:00Z", tz)
    assert isinstance(dt, datetime.datetime)


def test_parse_client_datetime_plain():
    tz = timezone.get_current_timezone()
    dt = N._parse_client_datetime("2026-01-01 10:00:00", tz)
    assert isinstance(dt, datetime.datetime)


def test_generate_time_periods_day():
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.datetime(2026, 1, 1), tz)
    end = timezone.make_aware(datetime.datetime(2026, 1, 3), tz)
    periods = N._generate_time_periods("day", start, end)
    assert len(periods) == 3


def test_generate_time_periods_hour():
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.datetime(2026, 1, 1, 0, 0), tz)
    end = timezone.make_aware(datetime.datetime(2026, 1, 1, 3, 0), tz)
    periods = N._generate_time_periods("hour", start, end)
    assert len(periods) == 3


def test_format_period_value_date():
    tz = timezone.get_current_timezone()
    out = N._format_period_value(datetime.date(2026, 1, 1), tz)
    assert "2026-01-01" in out


# --------------------------------------------------------------------------
# _get_authorized_alert_queryset
# --------------------------------------------------------------------------


def test_authorized_queryset_no_team():
    qs, err = N._get_authorized_alert_queryset({})
    assert qs is None
    assert err["result"] is False


def test_authorized_queryset_no_permission():
    qs, err = N._get_authorized_alert_queryset({"team": 1, "is_superuser": False, "permission": {}})
    assert qs is None
    assert "permission" in err["message"].lower() or err["result"] is False


@pytest.mark.django_db
def test_authorized_queryset_superuser_scoped():
    Alert.objects.create(alert_id="A1", level="0", title="t", content="c", fingerprint="fp", team=[1])
    Alert.objects.create(alert_id="A2", level="0", title="t", content="c", fingerprint="fp2", team=[2])
    qs, err = N._get_authorized_alert_queryset({"team": 1, "is_superuser": True})
    assert err is None
    assert set(qs.values_list("alert_id", flat=True)) == {"A1"}


@pytest.mark.django_db
def test_authorized_queryset_uses_alert_permission_rules(monkeypatch):
    team_alert = Alert.objects.create(
        alert_id="A1",
        level="0",
        title="t",
        content="c",
        fingerprint="fp1",
        team=[1],
    )
    instance_alert = Alert.objects.create(
        alert_id="A2",
        level="0",
        title="t",
        content="c",
        fingerprint="fp2",
        team=[2],
    )
    hidden_alert = Alert.objects.create(
        alert_id="A3",
        level="0",
        title="t",
        content="c",
        fingerprint="fp3",
        team=[3],
    )
    calls = []

    def fake_get_permission_rules(user, current_team, app_name, permission_key, include_children=False):
        calls.append((user.username, user.domain, current_team, app_name, permission_key, include_children))
        return {
            "team": [1],
            "instance": [{"id": instance_alert.id, "permission": ["View"]}],
        }

    monkeypatch.setattr(N, "get_permission_rules", fake_get_permission_rules)

    qs, err = N._get_authorized_alert_queryset(
        {
            "team": 1,
            "user": "alice",
            "domain": "tenant.example",
            "is_superuser": False,
            "include_children": True,
            "permission": {"alarm": ["Alarms-View"]},
        }
    )

    assert err is None
    assert set(qs.values_list("id", flat=True)) == {team_alert.id, instance_alert.id}
    assert hidden_alert.id not in set(qs.values_list("id", flat=True))
    assert calls == [("alice", "tenant.example", 1, "alerts", "alert", True)]


@pytest.mark.django_db
def test_authorized_queryset_requires_permission_identity_for_non_superuser():
    qs, err = N._get_authorized_alert_queryset(
        {
            "team": 1,
            "user": "alice",
            "is_superuser": False,
            "permission": {"alarm": ["Alarms-View"]},
        }
    )

    assert qs is None
    assert err["result"] is False
    assert "用户信息" in err["message"]


# --------------------------------------------------------------------------
# RPC 统计处理器
# --------------------------------------------------------------------------


@pytest.fixture
def user_info():
    return {"team": 1, "is_superuser": True}


@pytest.mark.django_db
def test_get_alert_statistics(user_info):
    Alert.objects.create(alert_id="A1", level="0", title="t", content="c", fingerprint="fp", team=[1], status=AlertStatus.PENDING)
    Alert.objects.create(alert_id="A2", level="0", title="t", content="c", fingerprint="fp2", team=[1], status=AlertStatus.PROCESSING)
    result = N.get_alert_statistics(user_info=user_info)
    assert result["result"] is True
    assert result["data"]["total_count"] == 2
    assert result["data"]["pending_count"] == 1
    assert result["data"]["processing_count"] == 1


@pytest.mark.django_db
def test_get_alert_statistics_permission_error():
    result = N.get_alert_statistics(user_info={"team": 1, "is_superuser": False, "permission": {}})
    assert result["result"] is False


@pytest.mark.django_db
def test_get_alert_today_status_summary_counts_created_closed_and_processing(user_info):
    now = timezone.now()
    old_alert = Alert.objects.create(
        alert_id="OLD",
        level="0",
        title="old",
        content="c",
        fingerprint="old-fp",
        team=[1],
        status=AlertStatus.CLOSED,
    )
    today_closed = Alert.objects.create(
        alert_id="TODAY-CLOSED",
        level="0",
        title="closed",
        content="c",
        fingerprint="closed-fp",
        team=[1],
        status=AlertStatus.CLOSED,
    )
    today_processing = Alert.objects.create(
        alert_id="TODAY-PROCESSING",
        level="0",
        title="processing",
        content="c",
        fingerprint="processing-fp",
        team=[1],
        status=AlertStatus.PROCESSING,
    )
    other_team = Alert.objects.create(
        alert_id="OTHER",
        level="0",
        title="other",
        content="c",
        fingerprint="other-fp",
        team=[2],
        status=AlertStatus.PROCESSING,
    )
    Alert.objects.filter(pk=old_alert.pk).update(
        created_at=now - datetime.timedelta(days=2),
        updated_at=now - datetime.timedelta(days=2),
    )
    Alert.objects.filter(pk=today_closed.pk).update(created_at=now, updated_at=now)
    Alert.objects.filter(pk=today_processing.pk).update(created_at=now, updated_at=now)
    Alert.objects.filter(pk=other_team.pk).update(created_at=now, updated_at=now)

    result = N.get_alert_today_status_summary(user_info=user_info)

    assert result["result"] is True
    assert result["data"] == {
        "today_created_count": 2,
        "today_closed_count": 1,
        "processing_count": 1,
    }


@pytest.mark.django_db
def test_get_alert_status_distribution_returns_active_status_labels(user_info):
    Alert.objects.create(
        alert_id="A1",
        level="0",
        title="t",
        content="c",
        fingerprint="fp1",
        team=[1],
        status=AlertStatus.UNASSIGNED,
    )
    Alert.objects.create(
        alert_id="A2",
        level="0",
        title="t",
        content="c",
        fingerprint="fp2",
        team=[1],
        status=AlertStatus.PENDING,
    )
    Alert.objects.create(
        alert_id="A3",
        level="0",
        title="t",
        content="c",
        fingerprint="fp3",
        team=[1],
        status=AlertStatus.PROCESSING,
    )
    Alert.objects.create(
        alert_id="A4",
        level="0",
        title="t",
        content="c",
        fingerprint="fp4",
        team=[1],
        status=AlertStatus.CLOSED,
    )

    result = N.get_alert_status_distribution(user_info=user_info)

    assert result["result"] is True
    assert result["data"] == [
        {"name": "未分派", "value": 1},
        {"name": "待响应", "value": 1},
        {"name": "处理中", "value": 1},
    ]


@pytest.mark.django_db
def test_get_alert_level_trend_returns_multiseries_by_level(user_info):
    Level.objects.create(
        level_id=0,
        level_name="fatal",
        level_display_name="致命",
        level_type=LevelType.ALERT,
    )
    Level.objects.create(
        level_id=1,
        level_name="warning",
        level_display_name="预警",
        level_type=LevelType.ALERT,
    )
    now = timezone.now()
    fatal_alert = Alert.objects.create(
        alert_id="A1",
        level="0",
        title="t",
        content="c",
        fingerprint="fp1",
        team=[1],
    )
    warning_alert = Alert.objects.create(
        alert_id="A2",
        level="1",
        title="t",
        content="c",
        fingerprint="fp2",
        team=[1],
    )
    Alert.objects.filter(pk=fatal_alert.pk).update(created_at=now)
    Alert.objects.filter(pk=warning_alert.pk).update(created_at=now)
    start = (now - datetime.timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    end = (now + datetime.timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")

    result = N.get_alert_level_trend(user_info=user_info, time=[start, end], group_by="day")

    assert result["result"] is True
    assert set(result["data"]) == {"致命", "预警"}
    assert sum(point[1] for point in result["data"]["致命"]) == 1
    assert sum(point[1] for point in result["data"]["预警"]) == 1


@pytest.mark.django_db
def test_get_alert_level_distribution(user_info):
    Level.objects.create(level_id=0, level_name="Critical", level_display_name="严重", level_type="alert")
    Alert.objects.create(alert_id="A1", level="0", title="t", content="c", fingerprint="fp", team=[1])
    Alert.objects.create(alert_id="A2", level="0", title="t", content="c", fingerprint="fp2", team=[1])
    result = N.get_alert_level_distribution(user_info=user_info)
    assert result["result"] is True
    assert result["data"][0]["name"] == "严重"
    assert result["data"][0]["value"] == 2


@pytest.mark.django_db
def test_get_active_alert_top(user_info):
    Alert.objects.create(alert_id="A1", level="0", title="t", content="c", fingerprint="fp", team=[1], status=AlertStatus.PENDING)
    result = N.get_active_alert_top(limit=5, user_info=user_info)
    assert result["result"] is True
    assert len(result["data"]) == 1
    assert result["data"][0]["alert_id"] == "A1"
    assert "duration_seconds" in result["data"][0]


@pytest.mark.django_db
def test_get_active_alert_top_limit_normalized(user_info):
    result = N.get_active_alert_top(limit=0, user_info=user_info)
    assert result["result"] is True


# --------------------------------------------------------------------------
# trend / source / notification / data quality
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_get_alert_trend_data_requires_time(user_info):
    result = N.get_alert_trend_data(user_info=user_info)
    assert result["result"] is False
    assert "required" in result["message"]


@pytest.mark.django_db
def test_get_alert_trend_data_minute_span_over_limit_rejected(user_info):
    """minute 粒度时间跨度超过 7 天上限时，应返回 result=False（拒绝生成超大时间序列）。
    若移除 get_alert_trend_data 中的跨度校验代码，本测试将失败。
    """
    result = N.get_alert_trend_data(
        user_info=user_info,
        time=["2026-01-01 00:00:00", "2026-01-09 00:00:00"],  # 8 天，超过 minute 粒度 7 天上限
        group_by="minute",
    )
    assert result["result"] is False, "超出 minute 粒度上限的请求必须被拒绝，防止 OOM"
    assert "minute" in result["message"]


@pytest.mark.django_db
def test_get_alert_trend_data_minute_span_within_limit_ok(user_info):
    """minute 粒度时间跨度在 7 天以内，应正常返回数据。"""
    result = N.get_alert_trend_data(
        user_info=user_info,
        time=["2026-01-01 00:00:00", "2026-01-06 00:00:00"],  # 5 天，在上限内
        group_by="minute",
    )
    assert result["result"] is True
    assert "告警数" in result["data"]


@pytest.mark.django_db
def test_get_alert_trend_data_hour_span_over_limit_rejected(user_info):
    """hour 粒度时间跨度超过 90 天上限时，应返回 result=False。
    若移除跨度校验代码，本测试将失败。
    """
    result = N.get_alert_trend_data(
        user_info=user_info,
        time=["2026-01-01 00:00:00", "2026-04-15 00:00:00"],  # ~104 天，超过 hour 粒度 90 天上限
        group_by="hour",
    )
    assert result["result"] is False, "超出 hour 粒度上限的请求必须被拒绝，防止 OOM"
    assert "hour" in result["message"]


@pytest.mark.django_db
def test_get_alert_trend_data_returns_series(user_info):
    Alert.objects.create(alert_id="A1", level="0", title="t", content="c", fingerprint="fp", team=[1])
    result = N.get_alert_trend_data(
        user_info=user_info,
        time=["2026-01-01 00:00:00", "2026-01-03 00:00:00"],
        group_by="day",
    )
    assert result["result"] is True
    assert "告警数" in result["data"]
    assert "事件数" in result["data"]


@pytest.mark.django_db
def test_get_alert_trend_data_with_events_in_window(user_info):
    # 在时间窗口内创建告警，覆盖 _build_period_series 的实际分桶逻辑
    now = timezone.now()
    alert = Alert.objects.create(alert_id="A1", level="0", title="t", content="c", fingerprint="fp", team=[1])
    Alert.objects.filter(pk=alert.pk).update(created_at=now)
    start = (now - datetime.timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    end = (now + datetime.timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    result = N.get_alert_trend_data(user_info=user_info, time=[start, end], group_by="day")
    assert result["result"] is True
    # 告警数序列非空且为 [时间, 数量] 形式
    series = result["data"]["告警数"]
    assert isinstance(series, list)
    total = sum(point[1] for point in series)
    assert total >= 1


@pytest.mark.django_db
def test_get_alert_source_event_top(user_info):
    from django.utils import timezone

    from apps.alerts.models.alert_source import AlertSource
    from apps.alerts.models.models import Event

    src = AlertSource.objects.create(name="Zabbix", source_id="s1", source_type="zabbix", secret="x")
    alert = Alert.objects.create(alert_id="A1", level="0", title="t", content="c", fingerprint="fp", team=[1])
    event = Event.objects.create(source=src, raw_data={}, title="e", level="0", start_time=timezone.now(), event_id="E1")
    alert.events.add(event)
    result = N.get_alert_source_event_top(user_info=user_info, limit=5)
    assert result["result"] is True
    assert result["data"][0] == {"source_name": "Zabbix", "count": 1}


@pytest.mark.django_db
def test_get_alert_source_statistics(user_info):
    from apps.alerts.models.alert_source import AlertSource
    from apps.alerts.models.models import Event

    AlertSource.objects.create(name="s1", source_id="s1", source_type="restful", secret="x", is_active=True)
    src2 = AlertSource.objects.create(name="s2", source_id="s2", source_type="restful", secret="x", is_active=False)
    alert = Alert.objects.create(alert_id="A1", level="0", title="t", content="c", fingerprint="fp", team=[1])
    event = Event.objects.create(
        source=src2,
        raw_data={},
        title="e",
        level="0",
        start_time=timezone.now(),
        event_id="E1",
    )
    alert.events.add(event)

    result = N.get_alert_source_statistics(user_info=user_info)

    assert result["result"] is True
    assert result["data"]["total_count"] == 1
    assert result["data"]["enabled_count"] == 0


@pytest.mark.django_db
def test_get_alert_source_statistics_counts_only_sources_from_authorized_alerts(user_info):
    from apps.alerts.models.alert_source import AlertSource
    from apps.alerts.models.models import Event

    visible_source = AlertSource.objects.create(
        name="visible",
        source_id="visible",
        source_type="restful",
        secret="x",
        is_active=True,
    )
    hidden_source = AlertSource.objects.create(
        name="hidden",
        source_id="hidden",
        source_type="restful",
        secret="x",
        is_active=True,
    )
    unused_source = AlertSource.objects.create(
        name="unused",
        source_id="unused",
        source_type="restful",
        secret="x",
        is_active=True,
    )

    visible_alert = Alert.objects.create(
        alert_id="A1",
        level="0",
        title="t",
        content="c",
        fingerprint="fp1",
        team=[1],
    )
    hidden_alert = Alert.objects.create(
        alert_id="A2",
        level="0",
        title="t",
        content="c",
        fingerprint="fp2",
        team=[2],
    )
    visible_event = Event.objects.create(
        source=visible_source,
        raw_data={},
        title="e1",
        level="0",
        start_time=timezone.now(),
        event_id="E1",
    )
    hidden_event = Event.objects.create(
        source=hidden_source,
        raw_data={},
        title="e2",
        level="0",
        start_time=timezone.now(),
        event_id="E2",
    )
    visible_alert.events.add(visible_event)
    hidden_alert.events.add(hidden_event)

    result = N.get_alert_source_statistics(user_info=user_info)

    assert result["result"] is True
    assert result["data"]["total_count"] == 1
    assert result["data"]["enabled_count"] == 1
    assert result["data"]["active_count"] == 1
    assert AlertSource.objects.filter(pk=unused_source.pk).exists()


@pytest.mark.django_db
def test_get_alert_source_statistics_permission_error():
    result = N.get_alert_source_statistics(user_info={"is_superuser": False, "permission": {}})
    assert result["result"] is False


@pytest.mark.django_db
def test_get_notification_statistics(user_info):
    from apps.alerts.constants.constants import NotifyResultStatus
    from apps.alerts.models import NotifyResult

    Alert.objects.create(alert_id="A1", level="0", title="t", content="c", fingerprint="fp1", team=[1])
    Alert.objects.create(alert_id="A2", level="0", title="t", content="c", fingerprint="fp2", team=[1])
    NotifyResult.objects.create(
        notify_type="alert",
        notify_object="A1",
        notify_result=NotifyResultStatus.SUCCESS,
    )
    NotifyResult.objects.create(
        notify_type="alert",
        notify_object="A2",
        notify_result=NotifyResultStatus.FAILED,
    )
    result = N.get_notification_statistics(user_info=user_info)
    assert result["result"] is True
    assert result["data"]["total_count"] == 2
    assert result["data"]["success_count"] == 1
    assert result["data"]["failed_count"] == 1


@pytest.mark.django_db
def test_get_notification_statistics_counts_only_authorized_alerts(user_info):
    from apps.alerts.constants.constants import NotifyResultStatus
    from apps.alerts.models import NotifyResult

    Alert.objects.create(alert_id="A1", level="0", title="t", content="c", fingerprint="fp1", team=[1])
    Alert.objects.create(alert_id="A2", level="0", title="t", content="c", fingerprint="fp2", team=[2])
    NotifyResult.objects.create(
        notify_type="alert",
        notify_object="A1",
        notify_result=NotifyResultStatus.SUCCESS,
    )
    NotifyResult.objects.create(
        notify_type="alert",
        notify_object="A2",
        notify_result=NotifyResultStatus.FAILED,
    )

    result = N.get_notification_statistics(user_info=user_info)

    assert result["result"] is True
    assert result["data"]["total_count"] == 1
    assert result["data"]["success_count"] == 1
    assert result["data"]["failed_count"] == 0


@pytest.mark.django_db
def test_get_alert_data_quality_empty(user_info):
    result = N.get_alert_data_quality(user_info=user_info)
    assert result["result"] is True
    assert result["data"]["total_count"] == 0


@pytest.mark.django_db
def test_get_alert_data_quality_with_data(user_info):
    Alert.objects.create(alert_id="A1", level="0", title="t", content="c", fingerprint="fp", team=[1], resource_id="", rule_id="")
    result = N.get_alert_data_quality(user_info=user_info)
    assert result["result"] is True
    assert result["data"]["total_count"] == 1
    # 缺失 resource_id → 100%
    assert result["data"]["missing_resource_id_rate"] == 100.0


# --------------------------------------------------------------------------
# receive_alert_events / alert_test
# --------------------------------------------------------------------------


def test_alert_test():
    result = N.alert_test()
    assert result["result"] is True


@pytest.mark.django_db
def test_receive_alert_events_missing_source_id():
    result = N.receive_alert_events(events=[{}], pusher="p")
    assert result["result"] is False
    assert "source_id" in result["message"]


@pytest.mark.django_db
def test_receive_alert_events_missing_events():
    result = N.receive_alert_events(source_id="nats", pusher="p")
    assert result["result"] is False
    assert "events" in result["message"].lower()


@pytest.mark.django_db
def test_receive_alert_events_missing_pusher():
    result = N.receive_alert_events(source_id="nats", events=[{}])
    assert result["result"] is False
    assert "pusher" in result["message"].lower()


@pytest.mark.django_db
def test_receive_alert_events_invalid_source():
    result = N.receive_alert_events(source_id="missing", events=[{}], pusher="p")
    assert result["result"] is False
    assert "Invalid source_id" in result["message"]


@pytest.mark.django_db
def test_receive_alert_events_success():
    from apps.alerts.constants.constants import LevelType
    from apps.alerts.models.alert_source import AlertSource
    from apps.alerts.models.models import Event

    for lid in (0, 1, 2, 3):
        Level.objects.create(level_id=lid, level_name=f"L{lid}", level_display_name=f"等级{lid}", level_type=LevelType.EVENT)
    AlertSource.objects.create(
        name="nats源",
        source_id="nats",
        source_type="nats",
        secret="x",
        is_active=True,
        is_effective=True,
        config={"event_fields_mapping": {"title": "title", "level": "level", "item": "item", "start_time": "start_time"}},
    )
    events = [{"title": "事件A", "level": "0", "item": "cpu", "start_time": "1700000000"}]
    result = N.receive_alert_events(source_id="nats", events=events, pusher="lite-monitor")
    assert result["result"] is True
    assert result["data"]["processed_events"] == 1
    assert Event.objects.filter(title="事件A").exists()


@pytest.mark.django_db
def test_receive_alert_events_marks_lite_log_as_trusted_internal(mocker):
    from apps.alerts.models.alert_source import AlertSource

    source = AlertSource.objects.create(
        name="日志中心 NATS 源",
        source_id="nats",
        source_type="nats",
        secret="source-secret",
        team_secrets={"3": "team-secret"},
        is_active=True,
        is_effective=True,
        config={},
    )
    adapter = mocker.Mock()
    adapter_class = mocker.Mock(return_value=adapter)
    mocker.patch.object(N.AlertSourceAdapterFactory, "get_adapter", return_value=adapter_class)

    result = N.receive_alert_events(
        source_id="nats",
        pusher="lite-log",
        events=[{"title": "日志错误", "organizations": [3]}],
    )

    assert result["result"] is True
    adapter_class.assert_called_once_with(
        alert_source=source,
        secret="",
        events=[{"title": "日志错误", "organizations": [3], "push_source_id": "lite-log"}],
        trusted_internal=True,
    )
    adapter.main.assert_called_once_with()


@pytest.mark.django_db
def test_receive_alert_events_does_not_log_event_payload_or_secret(mocker):
    from apps.alerts.models.alert_source import AlertSource

    AlertSource.objects.create(
        name="日志中心 NATS 源",
        source_id="nats",
        source_type="nats",
        secret="source-secret",
        team_secrets={"3": "team-secret"},
        is_active=True,
        is_effective=True,
        config={},
    )
    adapter = mocker.Mock()
    adapter_class = mocker.Mock(return_value=adapter)
    mocker.patch.object(N.AlertSourceAdapterFactory, "get_adapter", return_value=adapter_class)
    info = mocker.patch.object(N.logger, "info")

    N.receive_alert_events(
        source_id="nats",
        pusher="lite-log",
        events=[{"title": "sensitive-log-content", "organizations": [3], "secret": "event-secret"}],
    )

    logged = " ".join(str(call) for call in info.call_args_list)
    assert "sensitive-log-content" not in logged
    assert "event-secret" not in logged
    assert "source_id=%s" in logged
    assert "pusher=%s" in logged
    assert "event_count=%s" in logged


# --------------------------------------------------------------------------
# get_notification_channel_stats
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_get_notification_channel_stats_permission_error():
    result = N.get_notification_channel_stats(user_info={"is_superuser": False, "permission": {}})
    assert result["result"] is False


@pytest.mark.django_db
def test_get_notification_channel_stats_ok(user_info):
    result = N.get_notification_channel_stats(user_info=user_info)
    assert result["result"] is True
    assert isinstance(result["data"], list)


@pytest.mark.django_db
def test_get_notification_channel_stats_counts_only_authorized_alerts(user_info):
    from apps.alerts.constants.constants import NotifyResultStatus
    from apps.alerts.models import NotifyResult

    Alert.objects.create(alert_id="A1", level="0", title="t", content="c", fingerprint="fp1", team=[1])
    Alert.objects.create(alert_id="A2", level="0", title="t", content="c", fingerprint="fp2", team=[2])
    NotifyResult.objects.create(
        notify_type="alert",
        notify_object="A1",
        notify_channel="email",
        notify_channel_name="邮件",
        notify_result=NotifyResultStatus.SUCCESS,
    )
    NotifyResult.objects.create(
        notify_type="alert",
        notify_object="A2",
        notify_channel="sms",
        notify_channel_name="短信",
        notify_result=NotifyResultStatus.SUCCESS,
    )

    result = N.get_notification_channel_stats(user_info=user_info)

    assert result["result"] is True
    assert result["data"] == [{"name": "邮件", "value": 100.0}]
