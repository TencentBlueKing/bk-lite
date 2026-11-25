"""显示字段回填离开启动门禁：启动只入队，运行期分页且跳过未变化的值。"""

import json
import logging

import pytest
from celery.exceptions import SoftTimeLimitExceeded
from django.core.cache import cache

from apps.cmdb.models.repair_state import CmdbRepairState
from apps.cmdb.services.instance_shape_repair import STAGE_DISPLAY_BACKFILL
from apps.cmdb.services.unique_write_lock import UniqueWriteLockService
from apps.cmdb.tasks.display_field_backfill import (
    DISPLAY_BACKFILL_COMPLETED_KEY,
    DISPLAY_BACKFILL_CONTINUE_COUNTDOWN,
    DISPLAY_BACKFILL_CURSOR_KEY,
    DISPLAY_BACKFILL_LOCK,
    DISPLAY_BACKFILL_PERIODIC_TASK_NAME,
    DISPLAY_BACKFILL_RETRY_COUNTDOWN,
    DISPLAY_BACKFILL_TASK,
    backfill_cmdb_display_fields,
    disable_display_field_backfill_periodic_task,
    display_backfill_pending,
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
        "apps.cmdb.tasks.display_field_backfill.disable_display_field_backfill_periodic_task",
        lambda: None,
    )


def test_disable_display_backfill_periodic_task_is_idempotent():
    from apps.core.utils.celery_utils import CeleryUtils

    created = CeleryUtils.create_or_update_periodic_task(
        name=DISPLAY_BACKFILL_PERIODIC_TASK_NAME,
        crontab="*/5 * * * *",
        task=DISPLAY_BACKFILL_TASK,
        enabled=True,
    )
    first = disable_display_field_backfill_periodic_task()
    second = disable_display_field_backfill_periodic_task()

    assert first.pk == created.pk
    assert second.pk == created.pk
    assert second.enabled is False


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
    assert queued == [{"countdown": DISPLAY_BACKFILL_CONTINUE_COUNTDOWN}]
    row = CmdbRepairState.objects.get(stage=STAGE_DISPLAY_BACKFILL)
    assert json.loads(row.cursor) == {"model_id": "host", "last_id": 9}
    assert row.completed is False


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
    row = CmdbRepairState.objects.get(stage=STAGE_DISPLAY_BACKFILL)
    assert row.cursor == ""
    assert row.completed is True


def test_query_failure_keeps_cursor_and_retries_later(monkeypatch, locmem_cache):
    _patch_schedule(monkeypatch)
    queued = []

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
    monkeypatch.setattr(backfill_cmdb_display_fields, "apply_async", lambda **kwargs: queued.append(kwargs))

    result = backfill_cmdb_display_fields(force=True)

    assert result["status"] == "retry"
    assert result["reason"] == "query_failed"
    assert queued == [{"countdown": DISPLAY_BACKFILL_RETRY_COUNTDOWN}]
    row = CmdbRepairState.objects.get(stage=STAGE_DISPLAY_BACKFILL)
    assert json.loads(row.cursor) == {"model_id": "host", "last_id": 4}
    assert row.completed is False


def test_locked_backfill_does_not_scan(monkeypatch):
    _patch_schedule(monkeypatch)
    queued = []
    monkeypatch.setattr(
        "apps.cmdb.tasks.display_field_backfill.DisplayFieldInitializer",
        lambda: (_ for _ in ()).throw(AssertionError("锁被占用时不应扫描")),
    )
    monkeypatch.setattr(backfill_cmdb_display_fields, "apply_async", lambda **kwargs: queued.append(kwargs))

    with UniqueWriteLockService.serialize(DISPLAY_BACKFILL_LOCK, lease_seconds=30):
        result = backfill_cmdb_display_fields()

    assert result == {"status": "locked"}
    assert queued == [{"countdown": DISPLAY_BACKFILL_RETRY_COUNTDOWN}]
    with UniqueWriteLockService.serialize(DISPLAY_BACKFILL_LOCK, lease_seconds=5):
        pass


def test_soft_timeout_releases_lock(monkeypatch, caplog):
    _patch_schedule(monkeypatch)

    def _boom():
        secret = BROKER_SECRET
        raise SoftTimeLimitExceeded(secret)

    queued = []
    monkeypatch.setattr("apps.cmdb.tasks.display_field_backfill._backfill_under_lock", _boom)
    monkeypatch.setattr(backfill_cmdb_display_fields, "apply_async", lambda **kwargs: queued.append(kwargs))

    with caplog.at_level(logging.WARNING, logger="cmdb"):
        result = backfill_cmdb_display_fields()

    assert result == {"status": "retry", "reason": "soft_timeout"}
    assert queued == [{"countdown": DISPLAY_BACKFILL_RETRY_COUNTDOWN}]
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
    seen = {}

    def _call(name, *args, **kwargs):
        calls.append((name, kwargs))

    monkeypatch.setattr("apps.core.management.commands.batch_init.call_command", _call)
    monkeypatch.setattr("apps.cmdb.tasks.display_field_backfill.disable_display_field_backfill_periodic_task", lambda: None)
    monkeypatch.setattr("apps.cmdb.tasks.uuid_migration.ensure_uuid_migration_periodic_task", lambda: None)
    monkeypatch.setattr("apps.cmdb.tasks.uuid_migration.migrate_cmdb_instance_uuid_runtime.delay", lambda: None)
    monkeypatch.setattr("apps.cmdb.tasks.instance_shape_repair.repair_cmdb_instance_shape.delay", lambda: None)
    monkeypatch.setattr("apps.cmdb.tasks.ci_context.ensure_ci_context_rebuild_periodic_task", lambda: None)
    monkeypatch.setattr("apps.cmdb.tasks.ci_context.rebuild_ci_context_runtime.delay", lambda: None)

    def _delay(**kwargs):
        seen.update(kwargs)
        secret = BROKER_SECRET
        raise ConnectionError(f"redis://:{secret}@broker/0")

    monkeypatch.setattr("apps.cmdb.tasks.display_field_backfill.backfill_cmdb_display_fields.delay", _delay)

    from apps.core.management.commands.batch_init import Command

    with caplog.at_level(logging.WARNING, logger="app"):
        Command()._init_cmdb()

    assert ("init_display_fields", {"models_only": True}) in calls
    assert all(kwargs.get("models_only") for name, kwargs in calls if name == "init_display_fields")
    assert seen == {"force": False}
    records = [record for record in caplog.records if record.getMessage().startswith("event=display_backfill_enqueue_failed")]
    assert len(records) == 1
    assert cache.get(DISPLAY_BACKFILL_COMPLETED_KEY) == "done"
    assert cache.get(DISPLAY_BACKFILL_CURSOR_KEY) == {"model_id": "host", "last_id": 1}
    assert records[0].getMessage() == "event=display_backfill_enqueue_failed failed_stage=enqueue error_type=ConnectionError"
    assert BROKER_SECRET not in records[0].getMessage()
    formatted = logging.Formatter().format(records[0])
    assert BROKER_SECRET not in formatted
    assert records[0].exc_info[2] is not None


def test_init_cmdb_skips_backfill_after_completion(monkeypatch):
    from apps.cmdb.models.repair_state import mark_display_backfill_complete
    from apps.core.management.commands.batch_init import Command

    mark_display_backfill_complete()
    delays = []
    disabled = []
    monkeypatch.setattr("apps.core.management.commands.batch_init.call_command", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "apps.cmdb.tasks.display_field_backfill.disable_display_field_backfill_periodic_task",
        lambda: disabled.append(True),
    )
    monkeypatch.setattr(
        "apps.cmdb.tasks.display_field_backfill.backfill_cmdb_display_fields.delay",
        lambda **kwargs: delays.append(kwargs),
    )
    monkeypatch.setattr("apps.cmdb.tasks.uuid_migration.ensure_uuid_migration_periodic_task", lambda: None)
    monkeypatch.setattr("apps.cmdb.tasks.uuid_migration.migrate_cmdb_instance_uuid_runtime.delay", lambda: None)
    monkeypatch.setattr("apps.cmdb.tasks.instance_shape_repair.repair_cmdb_instance_shape.delay", lambda: None)
    monkeypatch.setattr("apps.cmdb.tasks.ci_context.ensure_ci_context_rebuild_periodic_task", lambda: None)
    monkeypatch.setattr("apps.cmdb.tasks.ci_context.rebuild_ci_context_runtime.delay", lambda: None)

    Command()._init_cmdb()

    assert disabled == [True]
    assert delays == []
    assert display_backfill_pending() is False


def test_backfill_discards_cursor_when_definition_changes(monkeypatch, locmem_cache, caplog):
    _patch_schedule(monkeypatch)
    from apps.cmdb.models.repair_state import mark_display_backfill_dirty

    class _Initializer:
        def initialize_all(self, **kwargs):
            return {"success": True, "errors": []}

        def backfill_bounded(self, **kwargs):
            mark_display_backfill_dirty()
            return {
                "done": True,
                "query_failed": False,
                "next_cursor": None,
                "instances_seen": 1,
                "instances_updated": 0,
                "errors": [],
            }

    monkeypatch.setattr("apps.cmdb.tasks.display_field_backfill.DisplayFieldInitializer", _Initializer)
    monkeypatch.setattr(backfill_cmdb_display_fields, "apply_async", lambda **kwargs: (_ for _ in ()).throw(AssertionError("代数变化后不应沿旧游标续跑")))

    with caplog.at_level(logging.INFO, logger="cmdb"):
        result = backfill_cmdb_display_fields(force=True)

    assert result["status"] == "reset"
    row = CmdbRepairState.objects.get(stage=STAGE_DISPLAY_BACKFILL)
    assert row.completed is False
    assert row.cursor == ""
    records = [record for record in caplog.records if record.getMessage() == "event=display_backfill_reset"]
    assert len(records) == 1


def test_new_display_field_reopens_backfill(monkeypatch):
    from apps.cmdb.models.repair_state import mark_display_backfill_complete
    from apps.cmdb.services.model import ModelManage

    mark_display_backfill_complete()
    queued = []
    monkeypatch.setattr(backfill_cmdb_display_fields, "delay", lambda **kwargs: queued.append(kwargs))

    ModelManage._request_display_instance_backfill()

    assert queued == [{"force": False}]
    assert display_backfill_pending() is True
    row = CmdbRepairState.objects.get(stage=STAGE_DISPLAY_BACKFILL)
    assert row.cursor == ""
    assert row.completed is False


def test_completion_does_not_cover_a_newer_generation(monkeypatch, locmem_cache):
    from django.db.models.query import QuerySet

    class _Initializer:
        def initialize_all(self, **kwargs):
            return {"success": True, "errors": []}

        def backfill_bounded(self, **kwargs):
            return {
                "done": True,
                "query_failed": False,
                "next_cursor": None,
                "instances_seen": 1,
                "instances_updated": 0,
                "errors": [],
            }

    original_update = QuerySet.update

    def _update(self, **kwargs):
        if kwargs.get("completed") is True:
            original_update(CmdbRepairState.objects.filter(stage=STAGE_DISPLAY_BACKFILL), fingerprint="99", completed=False, cursor="")
        return original_update(self, **kwargs)

    monkeypatch.setattr("apps.cmdb.tasks.display_field_backfill.DisplayFieldInitializer", _Initializer)
    monkeypatch.setattr(QuerySet, "update", _update)
    monkeypatch.setattr(
        backfill_cmdb_display_fields,
        "apply_async",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("代数已变，不应续跑")),
    )

    result = backfill_cmdb_display_fields(force=True)

    assert result["status"] == "reset"
    row = CmdbRepairState.objects.get(stage=STAGE_DISPLAY_BACKFILL)
    assert row.completed is False
    assert row.fingerprint == "99"
    assert row.cursor == ""


def test_continue_logs_enqueue_failure_without_secret(monkeypatch, locmem_cache, caplog):
    _patch_schedule(monkeypatch)

    class _Initializer:
        def initialize_all(self, **kwargs):
            return {"success": True, "errors": []}

        def backfill_bounded(self, **kwargs):
            return {
                "done": False,
                "query_failed": False,
                "next_cursor": {"last_id": 9},
                "instances_seen": 2000,
                "instances_updated": 1,
                "errors": [],
            }

    def _fail(**kwargs):
        raise ConnectionError(BROKER_SECRET)

    monkeypatch.setattr("apps.cmdb.tasks.display_field_backfill.DisplayFieldInitializer", _Initializer)
    monkeypatch.setattr(backfill_cmdb_display_fields, "apply_async", _fail)

    with caplog.at_level(logging.WARNING, logger="cmdb"):
        result = backfill_cmdb_display_fields(force=True)

    assert result["status"] == "continue"
    row = CmdbRepairState.objects.get(stage=STAGE_DISPLAY_BACKFILL)
    assert json.loads(row.cursor) == {"last_id": 9}
    records = [record for record in caplog.records if record.getMessage().startswith("event=display_backfill_enqueue_failed")]
    assert len(records) == 1
    assert records[0].getMessage() == "event=display_backfill_enqueue_failed failed_stage=enqueue error_type=ConnectionError countdown=1"
    assert records[0].args[-1] == DISPLAY_BACKFILL_CONTINUE_COUNTDOWN
    formatted = logging.Formatter().format(records[0])
    assert BROKER_SECRET not in records[0].getMessage()
    assert BROKER_SECRET not in formatted
    assert records[0].exc_info[0].__name__ == "SafeLogException"


def test_reopen_logs_enqueue_failure_without_secret(monkeypatch, caplog):
    from apps.cmdb.tasks.display_field_backfill import request_display_instance_backfill

    def _fail(**kwargs):
        raise ConnectionError(BROKER_SECRET)

    monkeypatch.setattr(backfill_cmdb_display_fields, "delay", _fail)

    with caplog.at_level(logging.WARNING, logger="cmdb"):
        request_display_instance_backfill()

    assert display_backfill_pending() is True
    records = [record for record in caplog.records if record.getMessage().startswith("event=display_backfill_enqueue_failed")]
    assert len(records) == 1
    assert records[0].getMessage() == "event=display_backfill_enqueue_failed failed_stage=enqueue error_type=ConnectionError"
    formatted = logging.Formatter().format(records[0])
    assert BROKER_SECRET not in records[0].getMessage()
    assert BROKER_SECRET not in formatted
    assert records[0].exc_info[0].__name__ == "SafeLogException"


def test_models_only_enqueues_one_backfill_for_many_definitions(monkeypatch):
    from apps.cmdb.display_field.initializer import DisplayFieldInitializer
    from apps.cmdb.models.repair_state import mark_display_backfill_dirty

    queued = []
    initializer = DisplayFieldInitializer()

    def _add(_model):
        mark_display_backfill_dirty()
        initializer._display_def_written = True
        return []

    monkeypatch.setattr(initializer, "_get_all_models", lambda: [{"model_id": "host"}, {"model_id": "switch"}])
    monkeypatch.setattr(initializer, "_add_display_fields_to_model", _add)
    monkeypatch.setattr("apps.cmdb.tasks.display_field_backfill.backfill_cmdb_display_fields.delay", lambda **kwargs: queued.append(kwargs))

    initializer.initialize_all(instances=False)

    assert queued == [{"force": False}]
