"""显示字段回填离开启动门禁：启动只入队，运行期分页且跳过未变化的值。"""

import logging

import pytest
from celery.exceptions import SoftTimeLimitExceeded
from django.core.cache import cache

from apps.cmdb.services.unique_write_lock import UniqueWriteLockService
from apps.cmdb.tasks.display_field_backfill import (
    DISPLAY_BACKFILL_COMPLETED_KEY,
    DISPLAY_BACKFILL_CURSOR_KEY,
    DISPLAY_BACKFILL_LOCK,
    DISPLAY_BACKFILL_PERIODIC_TASK_NAME,
    DISPLAY_BACKFILL_TASK,
    backfill_cmdb_display_fields,
    ensure_display_field_backfill_periodic_task,
)

pytestmark = pytest.mark.django_db

BROKER_SECRET = "display-backfill-broker-secret"


@pytest.fixture
def locmem_cache(settings):
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "display-field-backfill",
        }
    }
    cache.clear()
    yield
    cache.clear()


def _patch_schedule(monkeypatch):
    monkeypatch.setattr(
        "apps.cmdb.tasks.display_field_backfill.ensure_display_field_backfill_periodic_task",
        lambda: None,
    )


def test_ensure_display_backfill_periodic_task_is_idempotent():
    first = ensure_display_field_backfill_periodic_task()
    second = ensure_display_field_backfill_periodic_task()

    assert first.pk == second.pk
    from django_celery_beat.models import PeriodicTask

    assert PeriodicTask.objects.filter(name=DISPLAY_BACKFILL_PERIODIC_TASK_NAME).count() == 1
    task = PeriodicTask.objects.get(name=DISPLAY_BACKFILL_PERIODIC_TASK_NAME)
    assert task.task == DISPLAY_BACKFILL_TASK
    assert task.enabled is True
    assert task.crontab.minute == "*/5"


def test_backfill_continues_from_cursor(monkeypatch, locmem_cache):
    _patch_schedule(monkeypatch)
    queued = []

    class _Initializer:
        def initialize_all(self, **kwargs):
            assert kwargs["instances"] is False
            return {"success": True, "errors": []}

        def backfill_bounded(self, **kwargs):
            assert kwargs["max_instances"] == 2000
            assert kwargs["cursor"] is None
            return {
                "done": False,
                "query_failed": False,
                "next_cursor": {"model_id": "host", "last_id": 9},
                "instances_seen": 2000,
                "instances_updated": 3,
                "errors": [],
            }

    monkeypatch.setattr("apps.cmdb.tasks.display_field_backfill.DisplayFieldInitializer", _Initializer)
    monkeypatch.setattr(backfill_cmdb_display_fields, "apply_async", lambda **kwargs: queued.append(kwargs))

    result = backfill_cmdb_display_fields(force=True)

    assert result["status"] == "continue"
    assert result["instances_updated"] == 3
    assert queued == [{"countdown": 1}]
    assert cache.get(DISPLAY_BACKFILL_CURSOR_KEY) == {"model_id": "host", "last_id": 9}
    assert cache.get(DISPLAY_BACKFILL_COMPLETED_KEY) is None


def test_backfill_done_idles_until_forced(monkeypatch, locmem_cache):
    _patch_schedule(monkeypatch)
    calls = []

    class _Initializer:
        def initialize_all(self, **kwargs):
            return {"success": True, "errors": []}

        def backfill_bounded(self, **kwargs):
            calls.append(kwargs["cursor"])
            return {
                "done": True,
                "query_failed": False,
                "next_cursor": None,
                "instances_seen": 4,
                "instances_updated": 0,
                "errors": [],
            }

    monkeypatch.setattr("apps.cmdb.tasks.display_field_backfill.DisplayFieldInitializer", _Initializer)
    monkeypatch.setattr(backfill_cmdb_display_fields, "apply_async", lambda **kwargs: (_ for _ in ()).throw(AssertionError("done 后不应继续入队")))

    done = backfill_cmdb_display_fields(force=True)
    idle = backfill_cmdb_display_fields()

    assert done["status"] == "done"
    assert done["instances_updated"] == 0
    assert idle == {"status": "idle"}
    assert calls == [None]
    assert cache.get(DISPLAY_BACKFILL_CURSOR_KEY) is None
    assert cache.get(DISPLAY_BACKFILL_COMPLETED_KEY)


def test_query_failure_keeps_cursor_without_chaining(monkeypatch, locmem_cache):
    _patch_schedule(monkeypatch)

    class _Initializer:
        def initialize_all(self, **kwargs):
            return {"success": True, "errors": []}

        def backfill_bounded(self, **kwargs):
            return {
                "done": False,
                "query_failed": True,
                "next_cursor": {"model_id": "host", "last_id": 4},
                "instances_seen": 4,
                "instances_updated": 1,
                "errors": ["查询实例失败，model_id=host"],
            }

    monkeypatch.setattr("apps.cmdb.tasks.display_field_backfill.DisplayFieldInitializer", _Initializer)
    monkeypatch.setattr(backfill_cmdb_display_fields, "apply_async", lambda **kwargs: (_ for _ in ()).throw(AssertionError("查询失败不应立刻重入队")))

    result = backfill_cmdb_display_fields(force=True)

    assert result["status"] == "retry"
    assert result["reason"] == "query_failed"
    assert cache.get(DISPLAY_BACKFILL_CURSOR_KEY) == {"model_id": "host", "last_id": 4}


def test_locked_backfill_does_not_scan(monkeypatch):
    _patch_schedule(monkeypatch)
    monkeypatch.setattr(
        "apps.cmdb.tasks.display_field_backfill.DisplayFieldInitializer",
        lambda: (_ for _ in ()).throw(AssertionError("锁被占用时不应扫描")),
    )

    with UniqueWriteLockService.serialize(DISPLAY_BACKFILL_LOCK, lease_seconds=30):
        result = backfill_cmdb_display_fields()

    assert result == {"status": "locked"}
    with UniqueWriteLockService.serialize(DISPLAY_BACKFILL_LOCK, lease_seconds=5):
        pass


def test_soft_timeout_releases_lock(monkeypatch, caplog):
    _patch_schedule(monkeypatch)

    def _boom():
        secret = BROKER_SECRET
        raise SoftTimeLimitExceeded(secret)

    monkeypatch.setattr("apps.cmdb.tasks.display_field_backfill._backfill_under_lock", _boom)

    with caplog.at_level(logging.WARNING, logger="cmdb"):
        result = backfill_cmdb_display_fields()

    assert result == {"status": "retry", "reason": "soft_timeout"}
    records = [record for record in caplog.records if record.getMessage().startswith("event=display_backfill_soft_timeout")]
    assert len(records) == 1
    assert records[0].getMessage() == "event=display_backfill_soft_timeout failed_stage=backfill error_type=SoftTimeLimitExceeded"
    assert BROKER_SECRET not in records[0].getMessage()
    assert records[0].exc_info[0].__name__ == "SafeLogException"
    formatted = logging.Formatter().format(records[0])
    assert BROKER_SECRET not in formatted
    with UniqueWriteLockService.serialize(DISPLAY_BACKFILL_LOCK, lease_seconds=5):
        pass


def test_init_cmdb_enqueues_backfill_and_survives_broker_outage(monkeypatch, caplog, locmem_cache):
    calls = []
    cache.set(DISPLAY_BACKFILL_COMPLETED_KEY, "done")
    cache.set(DISPLAY_BACKFILL_CURSOR_KEY, {"model_id": "host", "last_id": 1})

    def _call(name, *args, **kwargs):
        calls.append((name, kwargs))

    monkeypatch.setattr("apps.core.management.commands.batch_init.call_command", _call)
    monkeypatch.setattr("apps.cmdb.tasks.display_field_backfill.ensure_display_field_backfill_periodic_task", lambda: None)
    monkeypatch.setattr("apps.cmdb.tasks.uuid_migration.ensure_uuid_migration_periodic_task", lambda: None)
    monkeypatch.setattr("apps.cmdb.tasks.uuid_migration.migrate_cmdb_instance_uuid_runtime.delay", lambda: None)

    def _delay(**kwargs):
        secret = BROKER_SECRET
        raise ConnectionError(f"redis://:{secret}@broker/0")

    monkeypatch.setattr("apps.cmdb.tasks.display_field_backfill.backfill_cmdb_display_fields.delay", _delay)

    from apps.core.management.commands.batch_init import Command

    with caplog.at_level(logging.WARNING, logger="app"):
        Command()._init_cmdb()

    assert ("init_display_fields", {"models_only": True}) in calls
    assert all(kwargs.get("models_only") for name, kwargs in calls if name == "init_display_fields")
    records = [record for record in caplog.records if record.getMessage().startswith("event=display_backfill_enqueue_failed")]
    assert len(records) == 1
    assert cache.get(DISPLAY_BACKFILL_COMPLETED_KEY) is None
    assert cache.get(DISPLAY_BACKFILL_CURSOR_KEY) is None
    assert records[0].getMessage() == "event=display_backfill_enqueue_failed failed_stage=enqueue error_type=ConnectionError"
    assert BROKER_SECRET not in records[0].getMessage()
    formatted = logging.Formatter().format(records[0])
    assert BROKER_SECRET not in formatted
    assert records[0].exc_info[2] is not None
