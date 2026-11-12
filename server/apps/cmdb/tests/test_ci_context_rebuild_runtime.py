"""ci_context 全量重摊离开启动门禁：启动只入队，运行期分页重算。"""

import logging
from types import SimpleNamespace

import pytest
from celery.exceptions import SoftTimeLimitExceeded
from django.core.cache import cache
from django_celery_beat.models import PeriodicTask

from apps.cmdb.tasks.ci_context import (
    REBUILD_BUDGET,
    REBUILD_CURSOR_KEY,
    REBUILD_LOCK_KEY,
    REBUILD_PERIODIC_TASK_NAME,
    REBUILD_TASK,
    ensure_ci_context_rebuild_periodic_task,
    rebuild_ci_context_runtime,
)
from apps.core.celery_runtime.manifest import TASK_ROUTES

pytestmark = pytest.mark.django_db

BROKER_SECRET = "ci-context-rebuild-broker-secret"


@pytest.fixture
def locmem_cache(settings):
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "ci-context-rebuild",
        }
    }
    cache.clear()
    yield
    cache.clear()


def _patch_ensure(monkeypatch, enabled=True):
    monkeypatch.setattr(
        "apps.cmdb.tasks.ci_context.ensure_ci_context_rebuild_periodic_task",
        lambda: SimpleNamespace(enabled=enabled),
    )


def test_rebuild_task_is_background_and_periodic_is_idempotent():
    assert TASK_ROUTES[REBUILD_TASK] == "background"
    first = ensure_ci_context_rebuild_periodic_task()
    second = ensure_ci_context_rebuild_periodic_task()

    assert first.pk == second.pk
    assert PeriodicTask.objects.filter(name=REBUILD_PERIODIC_TASK_NAME).count() == 1
    task = PeriodicTask.objects.get(name=REBUILD_PERIODIC_TASK_NAME)
    assert task.task == REBUILD_TASK
    assert task.enabled is True
    assert task.crontab.minute == "*/5"


def test_ensure_does_not_reenable_completed_periodic_task():
    ensure_ci_context_rebuild_periodic_task()
    PeriodicTask.objects.filter(name=REBUILD_PERIODIC_TASK_NAME).update(enabled=False)

    task = ensure_ci_context_rebuild_periodic_task()

    assert task.enabled is False
    assert PeriodicTask.objects.get(name=REBUILD_PERIODIC_TASK_NAME).enabled is False


def test_rebuild_continues_from_cursor(monkeypatch, locmem_cache):
    _patch_ensure(monkeypatch)
    queued = []
    calls = []

    def _bounded(**kwargs):
        calls.append(kwargs)
        assert kwargs["limit"] == REBUILD_BUDGET
        return {
            "ok_count": 50,
            "fail_count": 0,
            "seen": 50,
            "done": False,
            "next_skip": 50,
        }

    monkeypatch.setattr("apps.cmdb.services.ci_context.rebuild_ci_context_bounded", _bounded)
    monkeypatch.setattr(rebuild_ci_context_runtime, "apply_async", lambda **kwargs: queued.append(kwargs))

    result = rebuild_ci_context_runtime()

    assert result["status"] == "continue"
    assert result["skip"] == 50
    assert queued == [{"countdown": 1}]
    assert cache.get(REBUILD_CURSOR_KEY) == {"skip": 50, "ok": 50, "fail": 0}
    assert calls == [{"skip": 0, "limit": REBUILD_BUDGET}]


def test_rebuild_done_disables_periodic_and_idles(monkeypatch, locmem_cache):
    ensure_ci_context_rebuild_periodic_task()
    monkeypatch.setattr(
        "apps.cmdb.services.ci_context.rebuild_ci_context_bounded",
        lambda **kwargs: {"ok_count": 3, "fail_count": 0, "seen": 3, "done": True, "next_skip": 3},
    )
    monkeypatch.setattr(
        rebuild_ci_context_runtime,
        "apply_async",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("done 后不应继续入队")),
    )

    done = rebuild_ci_context_runtime()
    idle = rebuild_ci_context_runtime()

    assert done == {"status": "done", "recomputed": 3, "failed": 0}
    assert idle == {"status": "idle"}
    assert cache.get(REBUILD_CURSOR_KEY) is None
    assert PeriodicTask.objects.get(name=REBUILD_PERIODIC_TASK_NAME).enabled is False


def test_rebuild_locked_skips(monkeypatch, locmem_cache):
    _patch_ensure(monkeypatch)
    cache.add(REBUILD_LOCK_KEY, "1", timeout=60)
    monkeypatch.setattr(
        "apps.cmdb.services.ci_context.rebuild_ci_context_bounded",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("持锁时不应重算")),
    )

    assert rebuild_ci_context_runtime() == {"status": "locked"}


def test_soft_timeout_keeps_cursor_and_hides_secret(monkeypatch, locmem_cache, caplog):
    _patch_ensure(monkeypatch)
    cache.set(REBUILD_CURSOR_KEY, {"skip": 20, "ok": 20, "fail": 0})

    def _boom():
        secret = BROKER_SECRET
        raise SoftTimeLimitExceeded(secret)

    monkeypatch.setattr("apps.cmdb.tasks.ci_context._rebuild_under_lock", _boom)

    with caplog.at_level(logging.WARNING, logger="cmdb"):
        result = rebuild_ci_context_runtime()

    assert result == {"status": "retry", "reason": "soft_timeout"}
    assert cache.get(REBUILD_CURSOR_KEY) == {"skip": 20, "ok": 20, "fail": 0}
    records = [record for record in caplog.records if record.getMessage().startswith("event=ci_context_rebuild_soft_timeout")]
    assert len(records) == 1
    record = records[0]
    assert record.msg == "event=ci_context_rebuild_soft_timeout failed_stage=rebuild error_type=%s"
    assert record.args == ("SoftTimeLimitExceeded",)
    assert record.getMessage() == "event=ci_context_rebuild_soft_timeout failed_stage=rebuild error_type=SoftTimeLimitExceeded"
    assert BROKER_SECRET not in record.getMessage()
    formatted = logging.Formatter().format(record)
    assert BROKER_SECRET not in formatted
    assert cache.get(REBUILD_LOCK_KEY) is None


def test_init_cmdb_enqueues_rebuild_and_survives_broker_outage(monkeypatch, caplog, locmem_cache):
    calls = []

    def _call(name, *args, **kwargs):
        calls.append((name, kwargs))

    monkeypatch.setattr("apps.core.management.commands.batch_init.call_command", _call)
    monkeypatch.setattr("apps.cmdb.tasks.display_field_backfill.ensure_display_field_backfill_periodic_task", lambda: None)
    monkeypatch.setattr("apps.cmdb.tasks.display_field_backfill.backfill_cmdb_display_fields.delay", lambda *args, **kwargs: None)
    monkeypatch.setattr("apps.cmdb.tasks.uuid_migration.ensure_uuid_migration_periodic_task", lambda: None)
    monkeypatch.setattr("apps.cmdb.tasks.uuid_migration.migrate_cmdb_instance_uuid_runtime.delay", lambda: None)
    monkeypatch.setattr("apps.cmdb.tasks.instance_shape_repair.repair_cmdb_instance_shape.delay", lambda: None)
    monkeypatch.setattr("apps.cmdb.tasks.ci_context.ensure_ci_context_rebuild_periodic_task", lambda: SimpleNamespace(enabled=True))

    def _delay(**kwargs):
        secret = BROKER_SECRET
        raise ConnectionError(f"redis://:{secret}@broker/0")

    monkeypatch.setattr("apps.cmdb.tasks.ci_context.rebuild_ci_context_runtime.delay", _delay)

    from apps.core.management.commands.batch_init import Command

    with caplog.at_level(logging.WARNING, logger="app"):
        Command()._init_cmdb()

    assert ("rebuild_ci_context", {}) not in calls
    records = [record for record in caplog.records if record.getMessage().startswith("event=ci_context_rebuild_enqueue_failed")]
    assert len(records) == 1
    record = records[0]
    assert record.msg == "event=ci_context_rebuild_enqueue_failed failed_stage=enqueue error_type=%s"
    assert record.args == ("ConnectionError",)
    assert record.getMessage() == "event=ci_context_rebuild_enqueue_failed failed_stage=enqueue error_type=ConnectionError"
    assert BROKER_SECRET not in record.getMessage()
    formatted = logging.Formatter().format(record)
    assert BROKER_SECRET not in formatted


def test_init_cmdb_skips_enqueue_when_rebuild_already_done(monkeypatch):
    delayed = []

    monkeypatch.setattr("apps.core.management.commands.batch_init.call_command", lambda *args, **kwargs: None)
    monkeypatch.setattr("apps.cmdb.tasks.display_field_backfill.ensure_display_field_backfill_periodic_task", lambda: None)
    monkeypatch.setattr("apps.cmdb.tasks.display_field_backfill.backfill_cmdb_display_fields.delay", lambda *args, **kwargs: None)
    monkeypatch.setattr("apps.cmdb.tasks.uuid_migration.ensure_uuid_migration_periodic_task", lambda: None)
    monkeypatch.setattr("apps.cmdb.tasks.uuid_migration.migrate_cmdb_instance_uuid_runtime.delay", lambda: None)
    monkeypatch.setattr("apps.cmdb.tasks.instance_shape_repair.repair_cmdb_instance_shape.delay", lambda: None)
    monkeypatch.setattr(
        "apps.cmdb.tasks.ci_context.ensure_ci_context_rebuild_periodic_task",
        lambda: SimpleNamespace(enabled=False),
    )
    monkeypatch.setattr("apps.cmdb.tasks.ci_context.rebuild_ci_context_runtime.delay", lambda: delayed.append(True))

    from apps.core.management.commands.batch_init import Command

    Command()._init_cmdb()

    assert delayed == []
