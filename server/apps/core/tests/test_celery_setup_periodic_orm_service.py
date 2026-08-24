import sys
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.db import DatabaseError
from django_celery_beat.models import IntervalSchedule, PeriodicTask, PeriodicTasks

from apps.core import celery as celery_mod

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def _allow_setup(mocker, settings, *, schedule=None, complete=True, mode="enforce"):
    settings.IS_USE_CELERY = True
    settings.CELERY_BEAT_SCHEDULE = schedule or {}
    settings.CELERY_BEAT_SCHEDULE_COMPLETE = complete
    settings.CELERY_BEAT_SCHEDULE_RECONCILE_MODE = mode
    fake_sys = mocker.MagicMock()
    fake_sys.modules = {name: module for name, module in sys.modules.items() if name != "pytest"}
    mocker.patch.object(celery_mod, "sys", fake_sys)


def _create_task(name, *, enabled=True, task=None):
    interval, _ = IntervalSchedule.objects.get_or_create(every=60, period=IntervalSchedule.SECONDS)
    periodic = PeriodicTask.objects.create(
        name=name,
        task=task or f"apps.static.tasks.{name.replace('-', '_')}",
        interval=interval,
        enabled=enabled,
    )
    celery_mod._mark_config_managed(periodic)
    return periodic


def test_enforce_is_atomic_with_scheduler_sentinel(mocker, settings):
    removed = _create_task("atomic-removed")
    _allow_setup(mocker, settings)

    with patch.object(PeriodicTasks, "update_changed", side_effect=DatabaseError("sentinel failed")):
        with pytest.raises(DatabaseError) as exc_info:
            celery_mod.setup_periodic_tasks(sender=None)
    assert "sentinel failed" in str(exc_info.value)

    removed.refresh_from_db()
    assert removed.enabled is True
    assert "disabled-by-reconcile" not in removed.description

    before = PeriodicTasks.last_change()
    celery_mod.setup_periodic_tasks(sender=None)
    removed.refresh_from_db()
    assert removed.enabled is False
    assert "disabled-by-reconcile" in removed.description
    assert PeriodicTasks.last_change() > before


def test_rename_rolls_back_new_task_when_reconcile_sentinel_fails(mocker, settings):
    old = _create_task("rename-old")
    _allow_setup(
        mocker,
        settings,
        schedule={"rename-new": {"task": "apps.static.tasks.rename_new", "schedule": 60}},
    )
    failed_after_reconcile = False

    def fail_final_sentinel():
        nonlocal failed_after_reconcile
        new_task_exists = PeriodicTask.objects.filter(name="rename-new", enabled=True).exists()
        old_task_disabled = PeriodicTask.objects.filter(pk=old.pk, enabled=False).exists()
        if new_task_exists and old_task_disabled:
            failed_after_reconcile = True
            raise DatabaseError("final sentinel failed")

    with patch.object(PeriodicTasks, "update_changed", side_effect=fail_final_sentinel):
        with pytest.raises(DatabaseError, match="final sentinel failed"):
            celery_mod.setup_periodic_tasks(sender=None)

    old.refresh_from_db()
    assert failed_after_reconcile is True
    assert old.enabled is True
    assert PeriodicTask.objects.filter(name="rename-new").exists() is False


def test_restore_uses_provenance_and_bypasses_incomplete_snapshot(mocker, settings):
    enforced = _create_task("enforced-removed")
    manual = _create_task("manual-disabled", enabled=False)
    _allow_setup(mocker, settings, mode="enforce")
    celery_mod.setup_periodic_tasks(sender=None)
    enforced.refresh_from_db()
    manual.refresh_from_db()
    assert enforced.enabled is False
    assert "disabled-by-reconcile" in enforced.description
    assert manual.enabled is False
    assert "disabled-by-reconcile" not in manual.description

    settings.CELERY_BEAT_SCHEDULE_COMPLETE = False
    settings.CELERY_BEAT_SCHEDULE_RECONCILE_MODE = "restore"
    celery_mod.setup_periodic_tasks(sender=None)
    enforced.refresh_from_db()
    manual.refresh_from_db()
    assert enforced.enabled is True
    assert "disabled-by-reconcile" not in enforced.description
    assert manual.enabled is False


def test_restore_progresses_in_bounded_batches(mocker, settings):
    mocker.patch.object(celery_mod, "RECONCILE_TASK_LIMIT", 2)
    removed_tasks = [_create_task(f"restore-batch-{index}") for index in range(3)]
    for task in removed_tasks:
        task.enabled = False
        task.description = f"{task.description}\n{celery_mod.RECONCILE_DISABLED_MARKER}"
        task.save()
    _allow_setup(mocker, settings, mode="restore")

    celery_mod.setup_periodic_tasks(sender=None)
    assert PeriodicTask.objects.filter(name__startswith="restore-batch-", enabled=True).count() == 2

    celery_mod.setup_periodic_tasks(sender=None)
    assert PeriodicTask.objects.filter(name__startswith="restore-batch-", enabled=True).count() == 3


def test_restore_requires_exact_provenance_line(mocker, settings):
    manual = _create_task("manual-note-token", enabled=False)
    manual.description = f"{manual.description}\n管理员备注包含 {celery_mod.RECONCILE_DISABLED_MARKER} 但不是机器标记"
    manual.save()
    _allow_setup(mocker, settings, mode="restore")

    celery_mod.setup_periodic_tasks(sender=None)

    manual.refresh_from_db()
    assert manual.enabled is False


def test_invalid_provenance_does_not_starve_batched_restore(mocker, settings):
    mocker.patch.object(celery_mod, "RECONCILE_TASK_LIMIT", 2)
    invalid_tasks = [_create_task(f"aaa-invalid-{index}", enabled=False) for index in range(2)]
    for task in invalid_tasks:
        task.description = f"{task.description}\n{celery_mod.RECONCILE_DISABLED_MARKER} 不是独立行"
        task.save()
    valid_tasks = [_create_task(f"zzz-valid-{index}", enabled=False) for index in range(3)]
    for task in valid_tasks:
        task.description = f"{task.description}\n{celery_mod.RECONCILE_DISABLED_MARKER}"
        task.save()
    _allow_setup(mocker, settings, mode="restore")

    celery_mod.setup_periodic_tasks(sender=None)
    assert PeriodicTask.objects.filter(name__startswith="zzz-valid-", enabled=True).count() == 2

    celery_mod.setup_periodic_tasks(sender=None)
    assert PeriodicTask.objects.filter(name__startswith="zzz-valid-", enabled=True).count() == 3
    assert PeriodicTask.objects.filter(name__startswith="aaa-invalid-", enabled=False).count() == 2


def test_enforce_skips_owned_row_taken_over_by_dynamic_writer(mocker, settings, caplog):
    collided = _create_task("shared-name")
    PeriodicTask.objects.filter(pk=collided.pk).update(task="apps.job_mgmt.tasks.execute_scheduled_task")
    _allow_setup(mocker, settings, mode="enforce")

    celery_mod.setup_periodic_tasks(sender=None)

    collided.refresh_from_db()
    assert collided.enabled is True
    assert "所有权指纹不匹配" in caplog.text


def test_enforce_refuses_more_than_bounded_candidate_limit(mocker, settings, caplog):
    for index in range(celery_mod.RECONCILE_TASK_LIMIT + 1):
        _create_task(f"bounded-{index:03d}")
    _allow_setup(mocker, settings, mode="enforce")

    celery_mod.setup_periodic_tasks(sender=None)

    assert PeriodicTask.objects.filter(enabled=True).count() == celery_mod.RECONCILE_TASK_LIMIT + 1
    assert "超过单次上限" in caplog.text


def test_timedelta_schedule_is_owned_and_reconciled(mocker, settings):
    _allow_setup(
        mocker,
        settings,
        schedule={
            "timedelta-static": {
                "task": "apps.patch_mgmt.tasks.watch_governance_timeouts",
                "schedule": timedelta(seconds=60),
            }
        },
        mode="shadow",
    )

    celery_mod.setup_periodic_tasks(sender=None)

    periodic = PeriodicTask.objects.get(name="timedelta-static")
    assert periodic.interval.every == 60
    assert periodic.description.startswith(celery_mod.MANAGED_TASK_DESCRIPTION_PREFIX)
