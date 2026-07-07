"""告警构建器辅助方法覆盖测试。

对照 spec/prd/告警中心·告警：事件聚合为告警时统一标准字段、维度、级别映射。
"""

from types import SimpleNamespace

import pytest
from django.utils import timezone

from apps.alerts.aggregation.builder.alert_builder import AlertBuilder
from apps.alerts.constants.constants import LevelType
from apps.alerts.models.alert_source import AlertSource
from apps.alerts.models.models import Event, Level


# --------------------------------------------------------------------------
# _get_unique_scalar_value / _get_consistent_labels（纯函数）
# --------------------------------------------------------------------------


def test_get_unique_scalar_value_single():
    assert AlertBuilder._get_unique_scalar_value(["a", "a", "a"]) == "a"


def test_get_unique_scalar_value_mixed_returns_none():
    assert AlertBuilder._get_unique_scalar_value(["a", "b"]) is None


def test_get_consistent_labels_empty():
    assert AlertBuilder._get_consistent_labels([]) == {}


def test_get_consistent_labels_same():
    events = [SimpleNamespace(labels={"k": "v"}), SimpleNamespace(labels={"k": "v"})]
    assert AlertBuilder._get_consistent_labels(events) == {"k": "v"}


def test_get_consistent_labels_differ_returns_empty():
    events = [SimpleNamespace(labels={"k": "v"}), SimpleNamespace(labels={"k": "x"})]
    assert AlertBuilder._get_consistent_labels(events) == {}


# --------------------------------------------------------------------------
# _get_safe_strategy_team
# --------------------------------------------------------------------------


def test_get_safe_strategy_team_valid():
    strategy = SimpleNamespace(id=1, dispatch_team=[1, 2])
    assert AlertBuilder._get_safe_strategy_team(strategy) == [1, 2]


def test_get_safe_strategy_team_empty():
    strategy = SimpleNamespace(id=1, dispatch_team=[])
    assert AlertBuilder._get_safe_strategy_team(strategy) == []


def test_get_safe_strategy_team_invalid_returns_empty():
    strategy = SimpleNamespace(id=1, dispatch_team="notalist")
    assert AlertBuilder._get_safe_strategy_team(strategy) == []


# --------------------------------------------------------------------------
# _map_event_level_to_alert（依赖 ALERT 级别配置）
# --------------------------------------------------------------------------


@pytest.fixture
def alert_levels(db):
    AlertBuilder._valid_alert_levels = None  # 清理类缓存
    for lid in (0, 1, 2):
        Level.objects.create(level_id=lid, level_name=f"L{lid}", level_display_name=f"等级{lid}", level_type=LevelType.ALERT)
    yield
    AlertBuilder._valid_alert_levels = None


@pytest.mark.django_db
def test_map_event_level_in_range(alert_levels):
    assert AlertBuilder._map_event_level_to_alert("1") == "1"


@pytest.mark.django_db
def test_map_event_level_too_severe(alert_levels):
    # event level -1 比最严重(0)还严重 → 映射到 0
    assert AlertBuilder._map_event_level_to_alert(-1) == "0"


@pytest.mark.django_db
def test_map_event_level_too_mild(alert_levels):
    # event level 99 比最轻微(2)还轻微 → 映射到 2
    assert AlertBuilder._map_event_level_to_alert(99) == "2"


@pytest.mark.django_db
def test_map_event_level_invalid_defaults_zero(alert_levels):
    assert AlertBuilder._map_event_level_to_alert("notnum") == "0"


# --------------------------------------------------------------------------
# _resolve_standard_fields / _resolve_dimensions（DB）
# --------------------------------------------------------------------------


@pytest.fixture
def source(db):
    return AlertSource.objects.create(name="源1", source_id="s1", source_type="restful", secret="x")


def _make_event(source, event_id, **over):
    defaults = dict(
        source=source, raw_data={}, title="t", level="0", start_time=timezone.now(),
        event_id=event_id, item="cpu", resource_id="1", resource_name="host1",
        resource_type="host", service="svc", labels={},
    )
    defaults.update(over)
    return Event.objects.create(**defaults)


def test_resolve_standard_fields_empty():
    result = AlertBuilder._resolve_standard_fields([])
    assert result["item"] is None
    assert result["labels"] == {}


@pytest.mark.django_db
def test_resolve_standard_fields_consistent(source):
    e1 = _make_event(source, "E1")
    e2 = _make_event(source, "E2")
    result = AlertBuilder._resolve_standard_fields([e1, e2])
    assert result["item"] == "cpu"
    assert result["resource_name"] == "host1"
    assert result["source_name"] == "源1"


@pytest.mark.django_db
def test_resolve_dimensions_single_value(source):
    e1 = _make_event(source, "E1", service="svc")
    e2 = _make_event(source, "E2", service="svc")
    dims = AlertBuilder._resolve_dimensions([e1, e2], "service")
    assert dims == {"service": "svc"}


@pytest.mark.django_db
def test_resolve_dimensions_mixed_dropped(source):
    e1 = _make_event(source, "E1", service="svc1")
    e2 = _make_event(source, "E2", service="svc2")
    dims = AlertBuilder._resolve_dimensions([e1, e2], "service")
    assert dims == {}


def test_resolve_dimensions_no_group_field():
    assert AlertBuilder._resolve_dimensions([], "") == {}


# --------------------------------------------------------------------------
# WindowFactory
# --------------------------------------------------------------------------


def test_window_factory_sliding_default():
    from apps.alerts.aggregation.window.factory import WindowFactory, WindowType

    strategy = SimpleNamespace(params={"window_size": 15})
    cfg = WindowFactory.create_from_strategy(strategy)
    assert cfg.window_type == WindowType.SLIDING
    assert cfg.window_size_minutes == 15
    assert cfg.is_session_window is False


def test_window_factory_session():
    from apps.alerts.aggregation.window.factory import WindowFactory, WindowType

    strategy = SimpleNamespace(params={"window_size": 10, "time_out": True, "time_minutes": 30})
    cfg = WindowFactory.create_from_strategy(strategy)
    assert cfg.window_type == WindowType.SESSION
    assert cfg.is_session_window is True
    assert cfg.session_timeout_minutes == 30


def test_window_config_session_end_time():
    from apps.alerts.aggregation.window.factory import WindowConfig, WindowType

    cfg = WindowConfig(WindowType.SESSION, 10, session_timeout_minutes=20)
    assert cfg.get_session_end_time() > timezone.now()


# --------------------------------------------------------------------------
# create_or_update_alert（DB，需要在事务中调用 select_for_update）
# --------------------------------------------------------------------------


@pytest.fixture
def strategy(db):
    from apps.alerts.models.alert_operator import AlarmStrategy

    return AlarmStrategy.objects.create(
        name="策略", strategy_type="smart_denoise", team=[1], dispatch_team=[1],
        params={"window_size": 10},
    )


@pytest.mark.django_db
def test_create_or_update_alert_creates_new(alert_levels, source, strategy):
    from django.db import transaction

    e1 = _make_event(source, "E1")
    result = {
        "fingerprint": "fp-new",
        "event_ids": ["E1"],
        "alert_level": "1",
        "alert_title": "聚合告警A",
        "alert_description": "desc",
        "first_event_time": timezone.now(),
        "last_event_time": timezone.now(),
    }
    with transaction.atomic():
        alert = AlertBuilder.create_or_update_alert(result, strategy, group_by_field="service")
    assert alert.fingerprint == "fp-new"
    assert alert.title == "聚合告警A"
    assert alert.events.filter(event_id="E1").exists()


@pytest.mark.django_db
def test_create_or_update_alert_updates_existing(alert_levels, source, strategy):
    from django.db import transaction

    from apps.alerts.constants.constants import AlertStatus
    from apps.alerts.models.models import Alert

    AlertBuilder.clear_event_cache()
    existing = Alert.objects.create(
        alert_id="ALERT-EXIST", fingerprint="fp-x", level="2", title="旧",
        content="c", status=AlertStatus.UNASSIGNED,
    )
    e1 = _make_event(source, "E1")
    result = {
        "fingerprint": "fp-x",
        "event_ids": ["E1"],
        "alert_level": "1",
        "alert_title": "新标题",
        "alert_description": "desc",
        "first_event_time": timezone.now(),
        "last_event_time": timezone.now(),
    }
    with transaction.atomic():
        alert = AlertBuilder.create_or_update_alert(result, strategy)
    assert alert.pk == existing.pk
    assert alert.level == "1"
    assert alert.events.filter(event_id="E1").exists()


# --------------------------------------------------------------------------
# Level 信号驱动的缓存失效（Issue #3674）
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_level_post_save_invalidates_cache():
    """Level 保存后，_valid_alert_levels 应被清除为 None（重置为 None 就是缓存失效）。"""
    from django.db.models.signals import post_save, post_delete
    from apps.alerts.apps import _register_level_cache_signals
    from apps.alerts.models.models import Level

    # 确保信号已注册
    _register_level_cache_signals()

    # 预热缓存
    AlertBuilder._valid_alert_levels = None
    level = Level.objects.create(
        level_id=10, level_name="测试级别", level_display_name="测试", level_type=LevelType.ALERT
    )
    _ = AlertBuilder._get_valid_alert_levels()
    assert AlertBuilder._valid_alert_levels is not None, "缓存应已预热"

    # 触发 post_save（模拟运维人员修改 Level）
    level.level_name = "修改后"
    level.save()

    # 缓存应已被清除
    assert AlertBuilder._valid_alert_levels is None, "post_save 后缓存应失效为 None"

    # 清理
    level.delete()
    AlertBuilder._valid_alert_levels = None


@pytest.mark.django_db
def test_level_post_delete_invalidates_cache():
    """删除 Level 后，_valid_alert_levels 应被清除为 None。"""
    from apps.alerts.apps import _register_level_cache_signals
    from apps.alerts.models.models import Level

    _register_level_cache_signals()

    # 预热缓存
    AlertBuilder._valid_alert_levels = None
    level = Level.objects.create(
        level_id=11, level_name="待删除级别", level_display_name="待删除", level_type=LevelType.ALERT
    )
    _ = AlertBuilder._get_valid_alert_levels()
    assert AlertBuilder._valid_alert_levels is not None, "缓存应已预热"

    # 触发 post_delete
    level.delete()

    # 缓存应已被清除
    assert AlertBuilder._valid_alert_levels is None, "post_delete 后缓存应失效为 None"
    AlertBuilder._valid_alert_levels = None


@pytest.mark.django_db
def test_level_cache_refreshes_after_invalidation():
    """缓存失效后，下次调用 _get_valid_alert_levels 应从 DB 重新加载最新数据。"""
    from apps.alerts.apps import _register_level_cache_signals
    from apps.alerts.models.models import Level

    _register_level_cache_signals()

    AlertBuilder._valid_alert_levels = None
    # 初始：只有 level_id=0
    Level.objects.create(
        level_id=0, level_name="致命", level_display_name="致命", level_type=LevelType.ALERT
    )
    initial = AlertBuilder._get_valid_alert_levels()
    assert initial == {0}

    # 新增一个级别，触发信号使缓存失效
    Level.objects.create(
        level_id=1, level_name="错误", level_display_name="错误", level_type=LevelType.ALERT
    )
    # 缓存应已失效
    assert AlertBuilder._valid_alert_levels is None

    # 重新加载，应包含新级别
    refreshed = AlertBuilder._get_valid_alert_levels()
    assert refreshed == {0, 1}

    AlertBuilder._valid_alert_levels = None
