from unittest.mock import patch

import pytest
from django_celery_beat.models import CrontabSchedule, PeriodicTask

from apps.cmdb.services.node_mgmt_sync_service import NodeMgmtSyncService

pytestmark = pytest.mark.django_db


def _task_names():
    return set(PeriodicTask.objects.values_list("name", flat=True))


def test_first_open_reconciles_default_enabled_switches_to_beat():
    payload = NodeMgmtSyncService.get_task_payload(reconcile=True)

    assert payload["auto_sync_enabled"] is True
    assert payload["auto_collect_enabled"] is True
    assert NodeMgmtSyncService.SYNC_PERIODIC_TASK_NAME in _task_names()
    assert NodeMgmtSyncService.COLLECT_PERIODIC_TASK_NAME in _task_names()
    assert payload["schedule_status"] == "healthy"


def test_disable_then_refresh_keeps_both_schedules_absent():
    NodeMgmtSyncService.get_task_payload(reconcile=True)
    NodeMgmtSyncService.update_task({"auto_sync_enabled": False, "auto_collect_enabled": False})
    assert NodeMgmtSyncService.SYNC_PERIODIC_TASK_NAME not in _task_names()
    assert NodeMgmtSyncService.COLLECT_PERIODIC_TASK_NAME not in _task_names()

    payload = NodeMgmtSyncService.get_task_payload(reconcile=True)

    assert payload["auto_sync_enabled"] is False
    assert payload["auto_collect_enabled"] is False
    assert NodeMgmtSyncService.SYNC_PERIODIC_TASK_NAME not in _task_names()
    assert NodeMgmtSyncService.COLLECT_PERIODIC_TASK_NAME not in _task_names()


def test_disable_then_enable_recreates_both_schedules():
    NodeMgmtSyncService.update_task({"auto_sync_enabled": False, "auto_collect_enabled": False})
    NodeMgmtSyncService.update_task({"auto_sync_enabled": True, "auto_collect_enabled": True})

    assert NodeMgmtSyncService.SYNC_PERIODIC_TASK_NAME in _task_names()
    assert NodeMgmtSyncService.COLLECT_PERIODIC_TASK_NAME in _task_names()


def test_reconcile_repairs_deleted_or_wrong_schedule():
    NodeMgmtSyncService.get_task_payload(reconcile=True)
    PeriodicTask.objects.filter(name=NodeMgmtSyncService.SYNC_PERIODIC_TASK_NAME).delete()

    collect_task = PeriodicTask.objects.get(name=NodeMgmtSyncService.COLLECT_PERIODIC_TASK_NAME)
    wrong_crontab = CrontabSchedule.objects.create(minute="*/1", hour="*", day_of_week="*", day_of_month="*", month_of_year="*",)
    collect_task.task = "wrong.task"
    collect_task.crontab = wrong_crontab
    collect_task.enabled = False
    collect_task.save()

    NodeMgmtSyncService.get_task_payload(reconcile=True)

    sync_task = PeriodicTask.objects.get(name=NodeMgmtSyncService.SYNC_PERIODIC_TASK_NAME)
    collect_task.refresh_from_db()
    assert sync_task.task == NodeMgmtSyncService.SYNC_TASK
    assert sync_task.crontab.minute == "*/5"
    assert collect_task.task == NodeMgmtSyncService.COLLECT_TASK
    assert collect_task.crontab.minute == "*/30"
    assert collect_task.enabled is True


def test_reconcile_does_not_rewrite_already_matching_schedules():
    NodeMgmtSyncService.get_task_payload(reconcile=True)

    with patch("apps.core.utils.celery_utils.CeleryUtils.create_or_update_periodic_task") as create_task:
        with patch("apps.core.utils.celery_utils.CeleryUtils.delete_periodic_task") as delete_task:
            payload = NodeMgmtSyncService.get_task_payload(reconcile=True)

    assert payload["schedule_status"] == "healthy"
    create_task.assert_not_called()
    delete_task.assert_not_called()


def test_update_increments_version_and_persists_degraded_health_on_beat_failure(caplog,):
    config = NodeMgmtSyncService.get_task()
    original_version = config.version

    with patch(
        "apps.core.utils.celery_utils.CeleryUtils.create_or_update_periodic_task", side_effect=RuntimeError("secret-detail"),
    ):
        result = NodeMgmtSyncService.update_task({"sync_interval_minutes": 10})

    result.refresh_from_db()
    assert result.version == original_version + 1
    assert result.sync_interval_minutes == 10
    assert result.schedule_status == "degraded"
    assert result.reconcile_error_code == "RECONCILE_FAILED"
    assert result.reconcile_error_message
    assert "secret-detail" not in result.reconcile_error_message
    assert "secret-detail" not in caplog.text


def test_get_task_is_pure_and_does_not_reconcile_schedules():
    config = NodeMgmtSyncService.get_task()

    assert config.auto_sync_enabled is True
    assert config.auto_collect_enabled is True
    assert _task_names() == set()
