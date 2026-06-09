"""告警中心 NATS RPC 统计处理器与辅助函数覆盖测试。

对照 spec/prd/告警中心：运营统计（趋势/分布/TOP）按组织与权限范围聚合。
"""

import datetime

import pytest
from django.utils import timezone

from apps.alerts import nats as nats_pkg
from apps.alerts.nats import nats as N
from apps.alerts.constants.constants import AlertStatus
from apps.alerts.models.alert_operator import AlarmStrategy
from apps.alerts.models.models import Alert, Level


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


# --------------------------------------------------------------------------
# RPC 统计处理器
# --------------------------------------------------------------------------


@pytest.fixture
def user_info():
    return {"team": 1, "is_superuser": True}


@pytest.fixture
def strategy_user_info():
    return {
        "team": 1,
        "user": "alice",
        "domain": "domain.com",
        "is_superuser": False,
        "permission": {"alarm": ["correlation_rules-View"]},
    }


@pytest.fixture
def strategy_add_user_info(strategy_user_info):
    data = dict(strategy_user_info)
    data["permission"] = {"alarm": ["correlation_rules-Add", "correlation_rules-View"]}
    return data


@pytest.fixture
def strategy_edit_delete_user_info(strategy_user_info):
    data = dict(strategy_user_info)
    data["permission"] = {"alarm": ["correlation_rules-View", "correlation_rules-Edit", "correlation_rules-Delete"]}
    return data


def _smart_strategy_payload(name="created-by-nats", team=None, dispatch_team=None):
    team = [1] if team is None else team
    dispatch_team = [1] if dispatch_team is None else dispatch_team
    return {
        "name": name,
        "strategy_type": "smart_denoise",
        "team": team,
        "dispatch_team": dispatch_team,
        "match_rules": [[{"key": "service", "operator": "eq", "value": "api"}]],
        "params": {"group_by": ["service"], "window_size": 5, "time_out": False},
        "auto_close": False,
        "close_minutes": 120,
    }


@pytest.mark.django_db
def test_list_alarm_strategies_requires_view_permission():
    result = N.list_alarm_strategies(user_info={"team": 1, "permission": {"alarm": []}})

    assert result["result"] is False
    assert "permission" in result["message"].lower()


@pytest.mark.django_db
def test_list_alarm_strategies_filters_to_authorized_team(strategy_user_info):
    AlarmStrategy.objects.create(
        name="team-one",
        strategy_type="smart_denoise",
        team=[1],
        dispatch_team=[1],
    )
    AlarmStrategy.objects.create(
        name="team-two",
        strategy_type="smart_denoise",
        team=[2],
        dispatch_team=[2],
    )

    result = N.list_alarm_strategies(user_info=strategy_user_info)

    assert result["result"] is True
    names = [item["name"] for item in result["data"]["items"]]
    assert names == ["team-one"]


@pytest.mark.django_db
def test_get_alarm_strategy_rejects_cross_team_access(strategy_user_info):
    strategy = AlarmStrategy.objects.create(
        name="team-two",
        strategy_type="smart_denoise",
        team=[2],
        dispatch_team=[2],
    )

    result = N.get_alarm_strategy(strategy.id, user_info=strategy_user_info)

    assert result["result"] is False
    assert "not found" in result["message"].lower()


@pytest.mark.django_db
def test_create_alarm_strategy_uses_serializer_and_actor(strategy_add_user_info):
    result = N.create_alarm_strategy(_smart_strategy_payload(), user_info=strategy_add_user_info)

    assert result["result"] is True
    strategy = AlarmStrategy.objects.get(name="created-by-nats")
    assert strategy.params["window_size"] == 5
    assert result["data"]["id"] == strategy.id


@pytest.mark.django_db
def test_create_alarm_strategy_rejects_unauthorized_target_team(strategy_add_user_info):
    result = N.create_alarm_strategy(
        _smart_strategy_payload(team=[2], dispatch_team=[2]),
        user_info=strategy_add_user_info,
    )

    assert result["result"] is False
    assert "authorized" in result["message"].lower()
    assert not AlarmStrategy.objects.filter(name="created-by-nats").exists()


@pytest.mark.django_db
def test_update_alarm_strategy_updates_authorized_strategy(strategy_edit_delete_user_info):
    strategy = AlarmStrategy.objects.create(
        name="before",
        strategy_type="smart_denoise",
        team=[1],
        dispatch_team=[1],
        match_rules=[[{"key": "service", "operator": "eq", "value": "api"}]],
        params={"group_by": ["service"], "window_size": 5, "time_out": False},
    )

    result = N.update_alarm_strategy(
        strategy.id,
        {"name": "after"},
        user_info=strategy_edit_delete_user_info,
    )

    assert result["result"] is True
    strategy.refresh_from_db()
    assert strategy.name == "after"


@pytest.mark.django_db
def test_update_alarm_strategy_rejects_cross_team_access(strategy_edit_delete_user_info):
    strategy = AlarmStrategy.objects.create(
        name="team-two",
        strategy_type="smart_denoise",
        team=[2],
        dispatch_team=[2],
    )

    result = N.update_alarm_strategy(
        strategy.id,
        {"name": "after"},
        user_info=strategy_edit_delete_user_info,
    )

    assert result["result"] is False
    strategy.refresh_from_db()
    assert strategy.name == "team-two"


@pytest.mark.django_db
def test_delete_alarm_strategy_removes_authorized_strategy(strategy_edit_delete_user_info):
    strategy = AlarmStrategy.objects.create(
        name="delete-me",
        strategy_type="smart_denoise",
        team=[1],
        dispatch_team=[1],
    )

    result = N.delete_alarm_strategy(strategy.id, user_info=strategy_edit_delete_user_info)

    assert result["result"] is True
    assert result["data"]["deleted_id"] == strategy.id
    assert not AlarmStrategy.objects.filter(id=strategy.id).exists()


@pytest.mark.django_db
def test_delete_alarm_strategy_rejects_cross_team_access(strategy_edit_delete_user_info):
    strategy = AlarmStrategy.objects.create(
        name="keep-me",
        strategy_type="smart_denoise",
        team=[2],
        dispatch_team=[2],
    )

    result = N.delete_alarm_strategy(strategy.id, user_info=strategy_edit_delete_user_info)

    assert result["result"] is False
    assert AlarmStrategy.objects.filter(id=strategy.id).exists()


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
    assert result["data"][0][0] == "Zabbix"


@pytest.mark.django_db
def test_get_alert_source_statistics(user_info):
    from apps.alerts.models.alert_source import AlertSource

    AlertSource.objects.create(name="s1", source_id="s1", source_type="restful", secret="x", is_active=True)
    AlertSource.objects.create(name="s2", source_id="s2", source_type="restful", secret="x", is_active=False)
    result = N.get_alert_source_statistics(user_info=user_info)
    assert result["result"] is True
    assert result["data"]["total_count"] == 2
    assert result["data"]["enabled_count"] == 1


@pytest.mark.django_db
def test_get_alert_source_statistics_permission_error():
    result = N.get_alert_source_statistics(user_info={"is_superuser": False, "permission": {}})
    assert result["result"] is False


@pytest.mark.django_db
def test_get_notification_statistics(user_info):
    from apps.alerts.constants.constants import NotifyResultStatus
    from apps.alerts.models import NotifyResult

    NotifyResult.objects.create(notify_type="alert", notify_object="A1", notify_result=NotifyResultStatus.SUCCESS)
    NotifyResult.objects.create(notify_type="alert", notify_object="A2", notify_result=NotifyResultStatus.FAILED)
    result = N.get_notification_statistics(user_info=user_info)
    assert result["result"] is True
    assert result["data"]["total_count"] == 2
    assert result["data"]["success_count"] == 1
    assert result["data"]["failed_count"] == 1


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
        name="nats源", source_id="nats", source_type="nats", secret="x",
        is_active=True, is_effective=True,
        config={"event_fields_mapping": {"title": "title", "level": "level", "item": "item", "start_time": "start_time"}},
    )
    events = [{"title": "事件A", "level": "0", "item": "cpu", "start_time": "1700000000"}]
    result = N.receive_alert_events(source_id="nats", events=events, pusher="lite-monitor")
    assert result["result"] is True
    assert result["data"]["processed_events"] == 1
    assert Event.objects.filter(title="事件A").exists()


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
