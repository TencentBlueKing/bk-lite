"""D1 回归:聚合 beat 任务必须串行化(单例锁),防并发聚合产生重复告警。

根因:create_or_update_alert 的 select_for_update 在"建新"路径下命中零行、锁不住,
且 Alert.fingerprint 无唯一约束 → 并发聚合可对同一 fingerprint 建出两条活跃告警。
修法:给 event_aggregation_alert 加 cache 单例锁,运行期间第二次调用直接跳过。

注:conftest 默认把 cache 换成 DummyCache(add 恒为 True、不存任何东西),
无法验证 NX 锁语义,故本文件用 LocMemCache 覆盖以真正行使锁。
"""

import pytest
from unittest import mock

# 必须与 tasks.py 中的锁键一致
LOCK_KEY = "alerts:aggregation:beat:lock"

_PROC = "apps.alerts.aggregation.processor.aggregation_processor.AggregationProcessor.process_aggregation"
_TIMEOUT = "apps.alerts.aggregation.recovery.timeout_checker.TimeoutChecker.check_session_timeouts"


@pytest.fixture
def real_cache(settings):
    """覆盖 conftest 的 DummyCache:用 LocMemCache 真正验证锁的 NX 语义。"""
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "agg-lock-test",
        }
    }
    from django.core.cache import cache

    cache.clear()
    yield cache
    cache.clear()


@pytest.mark.django_db
def test_aggregation_runs_when_lock_free(real_cache):
    """无人持锁时,聚合正常执行。"""
    from apps.alerts.tasks.tasks import event_aggregation_alert

    with mock.patch(_PROC) as m_proc, mock.patch(_TIMEOUT, return_value=0):
        event_aggregation_alert()
        assert m_proc.called


@pytest.mark.django_db
def test_aggregation_skips_when_lock_held(real_cache):
    """已有聚合运行持锁时,第二次调用必须跳过(绝不并发聚合)。"""
    from apps.alerts.tasks.tasks import event_aggregation_alert

    # 模拟另一个聚合运行正持有锁
    assert real_cache.add(LOCK_KEY, "held", 300) is True

    with mock.patch(_PROC) as m_proc, mock.patch(_TIMEOUT, return_value=0) as m_timeout:
        event_aggregation_alert()
        assert not m_proc.called, "锁被持有时不应再次执行聚合"
        assert not m_timeout.called


@pytest.mark.django_db
def test_aggregation_releases_lock_after_run(real_cache):
    """运行结束后锁必须释放,下个周期可再次获取。"""
    from apps.alerts.tasks.tasks import event_aggregation_alert

    with mock.patch(_PROC), mock.patch(_TIMEOUT, return_value=0):
        event_aggregation_alert()

    # 锁已释放 → 能重新 add
    assert real_cache.add(LOCK_KEY, "x", 300) is True
