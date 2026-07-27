"""即时告警旁路调度器测试。

覆盖：策略缓存、命中分桶、bulk_create、指纹幂等、同步/异步阈值降级、
异常吞噬、Celery 任务路径。
"""

import hashlib
from unittest import mock

import pytest
from django.utils import timezone

from apps.alerts.aggregation.processor import instant_dispatcher as id_mod
from apps.alerts.aggregation.processor.instant_dispatcher import (
    InstantAlertDispatcher,
    InstantHit,
    InstantStrategyCache,
    _build_fingerprint,
    _bulk_build_instant_alerts,
    _trigger_dispatch_async,
)
from apps.alerts.constants import INSTANT_SYNC_THRESHOLD
from apps.alerts.constants.constants import AlarmStrategyType, EventAction
from apps.alerts.models.alert_operator import AlarmStrategy
from apps.alerts.models.alert_source import AlertSource
from apps.alerts.models.models import Alert, Event


# --------------------------------------------------------------------------
# fingerprint
# --------------------------------------------------------------------------

def test_fingerprint_format_and_stability():
    fp = _build_fingerprint(7, "EVENT-AB")
    expected = hashlib.md5(b"instant:7:EVENT-AB").hexdigest()
    assert fp == expected
    # 同输入幂等
    assert _build_fingerprint(7, "EVENT-AB") == fp


def test_fingerprint_namespace_isolation():
    """指纹包含 'instant:' 前缀 → 与裸 md5 聚合指纹永不撞车。"""
    fp = _build_fingerprint(1, "EVENT-1")
    raw_md5 = hashlib.md5(b"EVENT-1").hexdigest()
    assert fp != raw_md5


# --------------------------------------------------------------------------
# 缓存
# --------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_cache(settings):
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "instant-strategy-cache-test",
        }
    }
    from django.core.cache import cache as django_cache

    django_cache.close()
    InstantStrategyCache.cache_clear()
    yield
    InstantStrategyCache.cache_clear()
    django_cache.clear()
    django_cache.close()


@pytest.fixture
def source(db):
    return AlertSource.objects.create(name="src1", source_id="s-dispatcher", source_type="restful", secret="x")


@pytest.fixture
def instant_strategy(db):
    return AlarmStrategy.objects.create(
        name="即时-A",
        strategy_type=AlarmStrategyType.INSTANT,
        is_active=True,
        team=[1],
        dispatch_team=[1],
        match_rules=[[{"key": "title", "operator": "contains", "value": "fail"}]],
        params={"alert_template": {"title": "T", "description": "D"}},
    )


@pytest.fixture
def second_instant_strategy(db):
    return AlarmStrategy.objects.create(
        name="即时-B",
        strategy_type=AlarmStrategyType.INSTANT,
        is_active=True,
        team=[1],
        dispatch_team=[1],
        match_rules=[[{"key": "service", "operator": "eq", "value": "api"}]],
        params={"alert_template": {"title": "T", "description": "D"}},
    )


@pytest.fixture
def smart_strategy(db):
    return AlarmStrategy.objects.create(
        name="降噪",
        strategy_type=AlarmStrategyType.SMART_DENOISE,
        is_active=True,
        team=[1],
        dispatch_team=[1],
        match_rules=[[]],
        params={"window_size": 10},
    )


@pytest.mark.django_db
def test_cache_only_returns_instant_active(instant_strategy, smart_strategy):
    strategies = InstantStrategyCache.get()
    sids = [s.id for s in strategies]
    assert instant_strategy.id in sids
    assert smart_strategy.id not in sids


@pytest.mark.django_db
def test_cache_clear_refreshes(instant_strategy):
    assert len(InstantStrategyCache.get()) == 1
    instant_strategy.is_active = False
    instant_strategy.save()
    # save 钩子已通过 signal 清缓存
    assert len(InstantStrategyCache.get()) == 0


@pytest.mark.django_db
def test_cache_survives_local_memory_reset(instant_strategy, monkeypatch):
    strategies = InstantStrategyCache.get()
    assert [strategy.id for strategy in strategies] == [instant_strategy.id]

    AlarmStrategy.objects.filter(pk=instant_strategy.pk).update(is_active=False)
    monkeypatch.setattr(InstantStrategyCache, "_value", None, raising=False)
    monkeypatch.setattr(InstantStrategyCache, "_cached_at", 0, raising=False)

    cached_strategies = InstantStrategyCache.get()

    assert [strategy.id for strategy in cached_strategies] == [instant_strategy.id]


# --------------------------------------------------------------------------
# bulk_build / dispatch 主流程
# --------------------------------------------------------------------------

def _make_event(source, event_id="EVENT-1", title="login fail", level="1", service="api"):
    return Event.objects.create(
        source=source, raw_data={}, title=title, description="d",
        level=level, service=service, location="loc",
        resource_id="r1", resource_name="rn1", resource_type="rt1",
        item="i1", event_id=event_id, push_source_id="p",
        start_time=timezone.now(), labels={}, tags={},
        action=EventAction.CREATED,
    )


@pytest.mark.django_db
def test_no_strategy_no_alert(source):
    InstantAlertDispatcher.dispatch([[_make_event(source)]])
    assert Alert.objects.count() == 0


@pytest.mark.django_db
def test_no_event_no_alert(instant_strategy):
    InstantAlertDispatcher.dispatch([])
    assert Alert.objects.count() == 0


@pytest.mark.django_db
def test_single_hit_creates_one_alert(source, instant_strategy):
    evt = _make_event(source)
    with mock.patch("apps.alerts.tasks.deliver_alert_outbox.delay"):
        InstantAlertDispatcher.dispatch([[evt]])
    from apps.alerts.models import AlertOutbox
    assert set(AlertOutbox.objects.values_list("kind", flat=True)) == {
        "auto_assignment", "action"
    }
    alerts = Alert.objects.all()
    assert alerts.count() == 1
    alert = alerts.first()
    assert alert.fingerprint == _build_fingerprint(instant_strategy.id, evt.event_id)
    assert alert.level == "1"
    assert alert.rule_id == str(instant_strategy.id)
    assert alert.group_by_field == "instant"
    from apps.alerts.models import ActiveAlertFingerprint
    assert ActiveAlertFingerprint.objects.get(fingerprint=alert.fingerprint).alert_id == alert.pk
    # M2M 关联
    assert list(alert.events.values_list("event_id", flat=True)) == [evt.event_id]


@pytest.mark.django_db(transaction=True)
def test_instant_created_persists_assignment_and_action_outbox():
    from apps.alerts.models import AlertOutbox

    with mock.patch("apps.alerts.tasks.deliver_alert_outbox.delay"):
        _trigger_dispatch_async(["ALERT-INSTANT-1"])

    records = {record.kind: record for record in AlertOutbox.objects.all()}
    assert records["auto_assignment"].payload == {"alert_ids": ["ALERT-INSTANT-1"]}
    assert records["action"].payload == {
        "alert_id": "ALERT-INSTANT-1",
        "event_name": "created",
    }


@pytest.mark.django_db
def test_multi_strategy_multi_alert(source, instant_strategy, second_instant_strategy):
    evt = _make_event(source, title="login fail", service="api")  # 双命中
    with mock.patch.object(id_mod, "current_app"):
        InstantAlertDispatcher.dispatch([[evt]])
    assert Alert.objects.count() == 2
    fps = set(Alert.objects.values_list("fingerprint", flat=True))
    assert len(fps) == 2


@pytest.mark.django_db
def test_idempotent_on_repeat(source, instant_strategy):
    evt = _make_event(source)
    with mock.patch.object(id_mod, "current_app"):
        InstantAlertDispatcher.dispatch([[evt]])
        InstantAlertDispatcher.dispatch([[evt]])
    assert Alert.objects.count() == 1  # 指纹相同 → ignore_conflicts


@pytest.mark.django_db
def test_non_created_action_ignored(source, instant_strategy):
    evt = _make_event(source)
    evt.action = EventAction.RECOVERY
    evt.save()
    InstantAlertDispatcher.dispatch([[evt]])
    assert Alert.objects.count() == 0


@pytest.mark.django_db
def test_non_created_action_does_not_read_strategy_cache(source, instant_strategy):
    evt = _make_event(source)
    evt.action = EventAction.RECOVERY
    evt.save()

    with mock.patch.object(InstantStrategyCache, "get", wraps=InstantStrategyCache.get) as cache_get:
        InstantAlertDispatcher.dispatch([[evt]])

    cache_get.assert_not_called()


@pytest.mark.django_db
def test_shielded_filter_queries_once(source, instant_strategy):
    evt = _make_event(source)

    with (
        mock.patch.object(InstantAlertDispatcher, "_collect_hits", return_value=[]),
        mock.patch.object(Event.objects, "filter", wraps=Event.objects.filter) as event_filter,
    ):
        InstantAlertDispatcher.dispatch([[evt]])

    shield_queries = [
        call for call in event_filter.call_args_list
        if call.kwargs.get("status") == id_mod.EventStatus.SHIELD
    ]
    assert len(shield_queries) == 1


@pytest.mark.django_db
def test_shielded_event_produces_no_instant_alert(source, instant_strategy):
    """R3-1: 已被屏蔽的事件不得生成即时告警。"""
    from apps.alerts.constants.constants import EventStatus

    evt = _make_event(source)
    Event.objects.filter(event_id=evt.event_id).update(status=EventStatus.SHIELD)
    evt.refresh_from_db()
    with mock.patch.object(id_mod, "current_app") as mock_app:
        InstantAlertDispatcher.dispatch([[evt]])
        mock_app.send_task.assert_not_called()
    assert Alert.objects.count() == 0


# --------------------------------------------------------------------------
# 同步/异步阈值降级
# --------------------------------------------------------------------------

@pytest.mark.django_db
def test_async_branch_when_hits_exceed_threshold(source, instant_strategy):
    # 构造 INSTANT_SYNC_THRESHOLD + 1 个命中
    events = [_make_event(source, event_id=f"E{i}") for i in range(INSTANT_SYNC_THRESHOLD + 1)]
    with mock.patch.object(id_mod, "current_app") as mock_app:
        InstantAlertDispatcher.dispatch([events])
        # 应路由到 build_instant_alerts 任务，而非同步 + async_auto_assignment
        call = mock_app.send_task.call_args_list[0]
        assert call.args[0].endswith("build_instant_alerts")
    # 同步路径没走 → Alert 不应入库
    assert Alert.objects.count() == 0


@pytest.mark.django_db
def test_sync_branch_at_threshold_boundary(source, instant_strategy):
    events = [_make_event(source, event_id=f"E{i}") for i in range(INSTANT_SYNC_THRESHOLD)]
    with mock.patch.object(id_mod, "current_app"):
        InstantAlertDispatcher.dispatch([events])
    assert Alert.objects.count() == INSTANT_SYNC_THRESHOLD


# --------------------------------------------------------------------------
# 异常吞噬：dispatch 永不抛
# --------------------------------------------------------------------------

@pytest.mark.django_db
def test_dispatch_swallows_internal_exception(source, instant_strategy):
    with mock.patch.object(
        InstantAlertDispatcher, "_collect_hits", side_effect=RuntimeError("boom")
    ):
        # 不应抛出
        InstantAlertDispatcher.dispatch([[_make_event(source)]])


# --------------------------------------------------------------------------
# _bulk_build_instant_alerts 直接调用（Celery 任务路径同样使用）
# --------------------------------------------------------------------------

@pytest.mark.django_db
def test_bulk_build_returns_created_alert_ids(source, instant_strategy):
    evt = _make_event(source)
    hits = [InstantHit(strategy_id=instant_strategy.id, event_id=evt.event_id)]
    created = _bulk_build_instant_alerts(hits)
    assert len(created) == 1
    assert created[0].startswith("ALERT-")


@pytest.mark.django_db
def test_bulk_build_skips_unknown_strategy(source):
    evt = _make_event(source)
    hits = [InstantHit(strategy_id=999999, event_id=evt.event_id)]
    created = _bulk_build_instant_alerts(hits)
    assert created == []
