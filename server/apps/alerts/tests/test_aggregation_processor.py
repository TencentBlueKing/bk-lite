"""聚合处理器辅助方法覆盖测试。

对照 spec/prd/告警中心·配置：相关性规则按时间窗口取事件、缺失检查参数归一与心跳上下文。
"""

import datetime
from types import SimpleNamespace

import pytest
from django.utils import timezone

from apps.alerts.aggregation.processor.aggregation_processor import AggregationProcessor
from apps.alerts.constants.constants import EventAction, HeartbeatCheckMode
from apps.alerts.models.alert_operator import AlarmStrategy
from apps.alerts.models.alert_source import AlertSource
from apps.alerts.models.models import Event


# --------------------------------------------------------------------------
# _load_params
# --------------------------------------------------------------------------


def test_load_params_fills_defaults():
    strategy = SimpleNamespace(params={})
    params = AggregationProcessor._load_params(strategy)
    assert params["check_mode"] == HeartbeatCheckMode.CRON
    assert params["grace_period"] == 0
    assert params["auto_recovery"] is True
    assert params["alert_template"] == {}


def test_load_params_preserves_existing():
    strategy = SimpleNamespace(params={"grace_period": 5, "cron_expr": "* * * * *"})
    params = AggregationProcessor._load_params(strategy)
    assert params["grace_period"] == 5
    assert params["cron_expr"] == "* * * * *"


# --------------------------------------------------------------------------
# _build_heartbeat_context
# --------------------------------------------------------------------------


def test_build_heartbeat_context():
    event = SimpleNamespace(
        service="svc", location="loc", resource_name="rn", resource_id="rid",
        resource_type="rt", item="cpu", title="t", level="0",
    )
    ctx = AggregationProcessor._build_heartbeat_context(event)
    assert ctx["service"] == "svc"
    assert ctx["item"] == "cpu"
    assert ctx["level"] == "0"


# --------------------------------------------------------------------------
# _parse_runtime_datetime / normalize
# --------------------------------------------------------------------------


def test_parse_runtime_datetime_none():
    assert AggregationProcessor._parse_runtime_datetime(None) is None
    assert AggregationProcessor._parse_runtime_datetime("") is None


def test_parse_runtime_datetime_iso():
    result = AggregationProcessor._parse_runtime_datetime("2026-01-01T10:00:00")
    assert isinstance(result, datetime.datetime)
    assert timezone.is_aware(result)


def test_normalize_to_project_timezone_none():
    assert AggregationProcessor._normalize_to_project_timezone(None) is None


def test_normalize_to_project_timezone_naive_made_aware():
    naive = datetime.datetime(2026, 1, 1, 10, 0, 0)
    result = AggregationProcessor._normalize_to_project_timezone(naive)
    assert timezone.is_aware(result)


def test_normalize_to_timezone_none():
    assert AggregationProcessor._normalize_to_timezone(None, timezone.get_current_timezone()) is None


# --------------------------------------------------------------------------
# get_events_for_strategy / _query_candidate_events（DB）
# --------------------------------------------------------------------------


@pytest.fixture
def source(db):
    return AlertSource.objects.create(name="源1", source_id="s1", source_type="restful", secret="x")


@pytest.mark.django_db
def test_get_events_for_strategy_within_window(source):
    now = timezone.now()
    Event.objects.create(source=source, raw_data={}, title="t", level="0", start_time=now,
                         event_id="E1", action=EventAction.CREATED)
    strategy = AlarmStrategy.objects.create(name="s", strategy_type="smart_denoise", params={"window_size": 60})
    events = AggregationProcessor.get_events_for_strategy(strategy, now)
    assert events.filter(event_id="E1").exists()


@pytest.mark.django_db
def test_query_candidate_events_after_last_execute(source):
    now = timezone.now()
    strategy = AlarmStrategy.objects.create(name="s", strategy_type="missing_detection", params={})
    # last_execute_time 为 None → 用 created_at 起始
    proc = AggregationProcessor()
    Event.objects.create(source=source, raw_data={}, title="t", level="0", start_time=now,
                         event_id="E1", action=EventAction.CREATED)
    qs = proc._query_candidate_events(strategy, now)
    # 不报错并返回 queryset
    assert qs is not None


# --------------------------------------------------------------------------
# DuckDBConnection
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_duckdb_connection_load_and_query(source):
    from apps.alerts.aggregation.engine.connection import DuckDBConnection

    Event.objects.create(source=source, raw_data={}, title="t", level="0", start_time=timezone.now(),
                         event_id="E1", action=EventAction.CREATED, service="svc", labels={"k": "v"})
    conn = DuckDBConnection()
    ok = conn.load_events_to_memory(Event.objects.all())
    assert ok is True
    rows = conn.execute_query("SELECT count(*) AS c FROM events_table")
    assert rows[0]["c"] == 1
    conn.close()


@pytest.mark.django_db
def test_duckdb_load_empty_returns_none(source):
    from apps.alerts.aggregation.engine.connection import DuckDBConnection

    conn = DuckDBConnection()
    result = conn.load_events_to_memory(Event.objects.none())
    assert result is None
    conn.close()


def test_duckdb_load_with_future_infer_string():
    """回归：pandas 3.0 的 future.infer_string=True 会把字符串列建成 'str' dtype，
    而 duckdb 1.1.x 不识别该 dtype，register 会抛 NotImplementedException，
    导致每条聚合策略整链失败、Alert 一条都生不出来。
    load_events_to_memory 必须把扩展 string 列降级为 object，保证聚合正常装载。
    用假 queryset 避免依赖 DB（与本用例无关的迁移状态）。"""
    import pandas as pd
    from apps.alerts.aggregation.engine.connection import DuckDBConnection

    class _FakeQS:
        def __init__(self, rows):
            self._rows = rows

        def values(self, *fields):
            return self._rows

    rows = [{
        "event_id": "E1", "title": "主机 10.36.0.60-weopsx 磁盘使用率过高", "description": None,
        "level": "2", "resource_name": "10.36.0.60-weopsx", "resource_id": "('YTFlY2Y3YWVjZGU5',)",
        "resource_type": None, "item": None, "external_id": "9", "received_at": timezone.now(),
        "action": EventAction.CREATED, "source_id": 1, "push_source_id": "lite-monitor",
        "labels": {"k": "v"}, "service": "svc", "location": None, "event_type": 0, "tags": {},
    }]
    conn = DuckDBConnection()
    with pd.option_context("future.infer_string", True):
        ok = conn.load_events_to_memory(_FakeQS(rows))
    assert ok is True
    assert conn.execute_query("SELECT count(*) AS c FROM events_table")[0]["c"] == 1
    conn.close()


# --------------------------------------------------------------------------
# process_aggregation 端到端
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_process_aggregation_no_strategies():
    AggregationProcessor().process_aggregation()


@pytest.mark.django_db
def test_process_aggregation_smart_denoise_creates_alert(source):
    from apps.alerts.constants.constants import LevelType
    from apps.alerts.models.models import Alert, Level

    for lid in (0, 1, 2):
        Level.objects.create(level_id=lid, level_name=f"L{lid}", level_display_name=f"等级{lid}", level_type=LevelType.ALERT)

    now = timezone.now()
    for i in range(3):
        Event.objects.create(
            source=source, raw_data={}, title="CPU高", level="1", start_time=now,
            event_id=f"E{i}", action=EventAction.CREATED, service="svc-a",
            resource_name="host1", item="cpu", external_id=f"ext{i}",
        )

    AlarmStrategy.objects.create(
        name="降噪", strategy_type="smart_denoise", is_active=True, team=[1], dispatch_team=[1],
        match_rules=[[{"key": "title", "operator": "eq", "value": "CPU高"}]],
        params={"window_size": 60, "group_by": ["service"]},
    )

    AggregationProcessor().process_aggregation()
    assert Alert.objects.exists()


@pytest.mark.django_db
def test_process_aggregation_smart_denoise_updates_last_execute_time_without_events():
    strategy = AlarmStrategy.objects.create(
        name="无事件降噪",
        strategy_type="smart_denoise",
        is_active=True,
        team=[1],
        dispatch_team=[1],
        match_rules=[[{"key": "title", "operator": "eq", "value": "CPU高"}]],
        params={"window_size": 60, "group_by": ["service"]},
    )

    AggregationProcessor().process_aggregation()
    strategy.refresh_from_db()

    assert strategy.last_execute_time is not None


@pytest.mark.django_db
def test_process_aggregation_smart_denoise_updates_last_execute_time_without_matches(source):
    strategy = AlarmStrategy.objects.create(
        name="无匹配降噪",
        strategy_type="smart_denoise",
        is_active=True,
        team=[1],
        dispatch_team=[1],
        match_rules=[[{"key": "title", "operator": "eq", "value": "CPU高"}]],
        params={"window_size": 60, "group_by": ["service"]},
    )
    Event.objects.create(
        source=source, raw_data={}, title="MEM高", level="1", start_time=timezone.now(),
        event_id="E-no-match", action=EventAction.CREATED, service="svc-a",
        resource_name="host1", item="mem", external_id="ext-no-match",
    )

    AggregationProcessor().process_aggregation()
    strategy.refresh_from_db()

    assert strategy.last_execute_time is not None


# --------------------------------------------------------------------------
# missing_detection 路径
# --------------------------------------------------------------------------


def _missing_strategy(**param_over):
    params = {
        "check_mode": "cron",
        "cron_expr": "*/5 * * * *",
        "grace_period": 5,
        "activation_mode": "immediate",
        "auto_recovery": True,
        "alert_template": {"title": "心跳缺失", "level": "1", "description": "服务 {service} 心跳缺失"},
    }
    params.update(param_over)
    return AlarmStrategy.objects.create(
        name="缺失检查", strategy_type="missing_detection", is_active=True,
        team=[1], dispatch_team=[1],
        match_rules=[[{"key": "item", "operator": "eq", "value": "heartbeat"}]],
        params=params,
    )


@pytest.mark.django_db
def test_process_missing_detection_with_heartbeat(source):
    # 有心跳事件 → 保存运行态，不创建告警
    _missing_strategy()
    Event.objects.create(
        source=source, raw_data={}, title="hb", level="1", start_time=timezone.now(),
        event_id="HB1", action=EventAction.CREATED, item="heartbeat", service="svc-a",
    )
    AggregationProcessor().process_aggregation()
    from apps.alerts.models.models import Alert
    # 有心跳，不应触发缺失告警
    assert not Alert.objects.filter(title="心跳缺失").exists()


@pytest.mark.django_db
def test_process_missing_detection_no_event_saves_runtime():
    from datetime import timedelta

    # 无心跳事件，deadline 尚未到（高频 cron 的下一个周期在未来）→ 保存运行态，不创建告警
    strategy = _missing_strategy()
    AlarmStrategy.objects.filter(pk=strategy.pk).update(
        created_at=timezone.now() - timedelta(hours=2)
    )
    AggregationProcessor().process_aggregation()
    strategy.refresh_from_db()
    # 运行态被保存：last_execute_time 被更新
    assert strategy.last_execute_time is not None
    assert strategy.params.get("heartbeat_status") is not None


@pytest.mark.django_db
def test_process_missing_detection_recovers_active_alert(source):
    from apps.alerts.aggregation.builder.synthetic_alert_builder import SyntheticAlertBuilder
    from apps.alerts.constants.constants import AlertStatus

    strategy = _missing_strategy()
    active = SyntheticAlertBuilder.create_alert(strategy, strategy.params, timezone.now())
    assert active.status in AlertStatus.ACTIVATE_STATUS

    Event.objects.create(
        source=source, raw_data={}, title="hb", level="1", start_time=timezone.now(),
        event_id="HB1", action=EventAction.CREATED, item="heartbeat", service="svc-a",
    )
    AggregationProcessor().process_aggregation()
    active.refresh_from_db()
    assert active.status == AlertStatus.AUTO_RECOVERY


# --------------------------------------------------------------------------
# SyntheticAlertBuilder
# --------------------------------------------------------------------------


def test_synthetic_render_template():
    from apps.alerts.aggregation.builder.synthetic_alert_builder import SyntheticAlertBuilder

    out = SyntheticAlertBuilder.render_template("服务 {{ service }} 缺失", {"service": "svc-a"})
    assert out == "服务 svc-a 缺失"


def test_synthetic_build_fingerprint_stable():
    from apps.alerts.aggregation.builder.synthetic_alert_builder import SyntheticAlertBuilder

    assert SyntheticAlertBuilder.build_fingerprint(42) == SyntheticAlertBuilder.build_fingerprint(42)


@pytest.mark.django_db
def test_synthetic_find_active_alert_none():
    from apps.alerts.aggregation.builder.synthetic_alert_builder import SyntheticAlertBuilder

    strategy = _missing_strategy()
    assert SyntheticAlertBuilder.find_active_alert(strategy) is None
