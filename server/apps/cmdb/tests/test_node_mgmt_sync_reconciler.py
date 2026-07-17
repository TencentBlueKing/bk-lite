import json
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone
from django_celery_beat.models import ClockedSchedule, CrontabSchedule, IntervalSchedule, PeriodicTask, SolarSchedule

from apps.cmdb.models.node_mgmt_sync import NodeMgmtSyncConfig
from apps.cmdb.services.node_mgmt_sync_reconciler import NodeMgmtSyncReconciler
from apps.cmdb.services.node_mgmt_sync_service import NodeMgmtSyncService
from apps.cmdb.views.node_mgmt_sync import NodeMgmtSyncViewSet

pytestmark = pytest.mark.django_db


def _task_names():
    return set(PeriodicTask.objects.values_list("name", flat=True))


def _get_task_from_view():
    request = SimpleNamespace(
        method="GET",
        user=SimpleNamespace(
            permission={"auto_collection-View"},
            is_superuser=False,
            locale="zh",
        ),
    )
    response = NodeMgmtSyncViewSet().task(request)
    assert response.status_code == 200
    return json.loads(response.content)["data"]


def test_product_get_reconciles_first_open_disabled_refresh_and_deleted_drift():
    payload = _get_task_from_view()
    assert payload["schedule_status"] == "healthy"
    assert _task_names() == {
        NodeMgmtSyncService.SYNC_PERIODIC_TASK_NAME,
        NodeMgmtSyncService.COLLECT_PERIODIC_TASK_NAME,
    }

    NodeMgmtSyncService.update_task({"auto_sync_enabled": False, "auto_collect_enabled": False})
    payload = _get_task_from_view()
    assert payload["auto_sync_enabled"] is False
    assert payload["auto_collect_enabled"] is False
    assert _task_names() == set()

    NodeMgmtSyncService.update_task({"auto_sync_enabled": True})
    PeriodicTask.objects.filter(name=NodeMgmtSyncService.SYNC_PERIODIC_TASK_NAME).delete()
    _get_task_from_view()
    assert NodeMgmtSyncService.SYNC_PERIODIC_TASK_NAME in _task_names()


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
    wrong_crontab = CrontabSchedule.objects.create(
        minute="*/1",
        hour="*",
        day_of_week="*",
        day_of_month="*",
        month_of_year="*",
    )
    collect_task.task = "wrong.task"
    collect_task.crontab = wrong_crontab
    collect_task.interval = None
    collect_task.enabled = False
    collect_task.save()

    NodeMgmtSyncService.get_task_payload(reconcile=True)

    sync_task = PeriodicTask.objects.get(name=NodeMgmtSyncService.SYNC_PERIODIC_TASK_NAME)
    collect_task.refresh_from_db()
    assert sync_task.task == NodeMgmtSyncService.SYNC_TASK
    assert sync_task.crontab_id is None
    assert sync_task.interval.every == 5 * 60
    assert sync_task.interval.period == IntervalSchedule.SECONDS
    assert collect_task.task == NodeMgmtSyncService.COLLECT_TASK
    assert collect_task.crontab_id is None
    assert collect_task.interval.every == 30 * 60
    assert collect_task.interval.period == IntervalSchedule.SECONDS
    assert collect_task.enabled is True


def test_reconcile_migrates_legacy_crontab_to_real_interval():
    NodeMgmtSyncService.get_task_payload(reconcile=True)
    sync_task = PeriodicTask.objects.get(name=NodeMgmtSyncService.SYNC_PERIODIC_TASK_NAME)
    expected_timezone = timezone.get_default_timezone()
    wrong_timezone = ZoneInfo("Asia/Shanghai") if str(expected_timezone) != "Asia/Shanghai" else ZoneInfo("UTC")
    wrong_crontab = CrontabSchedule.objects.create(
        minute="*/5",
        hour="*",
        day_of_week="*",
        day_of_month="*",
        month_of_year="*",
        timezone=wrong_timezone,
    )
    sync_task.crontab = wrong_crontab
    sync_task.interval = None
    sync_task.save(update_fields=["crontab", "interval"])

    NodeMgmtSyncService.get_task_payload(reconcile=True)

    sync_task.refresh_from_db()
    assert sync_task.crontab_id is None
    assert sync_task.interval.every == 5 * 60
    assert sync_task.interval.period == IntervalSchedule.SECONDS


@pytest.mark.parametrize("minutes", [1, 60, 90, 1440])
def test_reconcile_uses_exact_minute_interval_for_long_cycles(minutes):
    NodeMgmtSyncService.update_task({"sync_interval_minutes": minutes, "collect_interval_minutes": minutes})

    for name in (
        NodeMgmtSyncService.SYNC_PERIODIC_TASK_NAME,
        NodeMgmtSyncService.COLLECT_PERIODIC_TASK_NAME,
    ):
        periodic_task = PeriodicTask.objects.get(name=name)
        assert periodic_task.crontab_id is None
        assert periodic_task.interval.every == minutes * 60
        assert periodic_task.interval.period == IntervalSchedule.SECONDS


def test_reconcile_deterministically_repairs_duplicate_interval_and_all_schedule_fks():
    NodeMgmtSyncService.get_task_payload(reconcile=True)
    periodic_task = PeriodicTask.objects.get(name=NodeMgmtSyncService.SYNC_PERIODIC_TASK_NAME)
    duplicate = IntervalSchedule.objects.create(every=5 * 60, period=IntervalSchedule.SECONDS)
    winner_id = min(periodic_task.interval_id, duplicate.pk)
    crontab = CrontabSchedule.objects.create(
        minute="*/5",
        hour="*",
        day_of_week="*",
        day_of_month="*",
        month_of_year="*",
    )
    solar = SolarSchedule.objects.create(event="sunrise", latitude=0, longitude=0)
    clocked = ClockedSchedule.objects.create(clocked_time=timezone.now())
    PeriodicTask.objects.filter(pk=periodic_task.pk).update(
        task=NodeMgmtSyncService.SYNC_TASK,
        interval=duplicate,
        crontab=crontab,
        solar=solar,
        clocked=clocked,
    )

    NodeMgmtSyncService.get_task_payload(reconcile=True)

    periodic_task.refresh_from_db()
    assert periodic_task.task == NodeMgmtSyncService.SYNC_TASK
    assert periodic_task.interval_id == winner_id
    assert periodic_task.crontab_id is None
    assert periodic_task.solar_id is None
    assert periodic_task.clocked_id is None


def test_update_returns_health_from_reconciled_current_database_row(mocker):
    config = NodeMgmtSyncService.get_task()

    def persist_new_health(stale, **kwargs):
        NodeMgmtSyncConfig.objects.filter(pk=stale.pk).update(
            schedule_status="degraded",
            reconcile_error_code="RECONCILE_FAILED",
        )

    mocker.patch.object(NodeMgmtSyncReconciler, "reconcile", side_effect=persist_new_health)

    returned = NodeMgmtSyncService.update_task({"sync_interval_minutes": 10})

    assert returned.version == config.version + 1
    assert returned.schedule_status == "degraded"
    assert returned.reconcile_error_code == "RECONCILE_FAILED"


def test_update_retries_version_cas_after_interleaved_winner(mocker):
    config = NodeMgmtSyncService.get_task()
    initial_version = config.version
    original_filter = NodeMgmtSyncConfig.objects.filter
    winner_injected = False

    def inject_winner_before_first_cas(*args, **kwargs):
        nonlocal winner_injected
        if kwargs.get("version") == initial_version and not winner_injected:
            winner_injected = True
            original_filter(pk=config.pk).update(
                version=initial_version + 1,
                auto_sync_enabled=False,
                auto_collect_enabled=False,
            )
        return original_filter(*args, **kwargs)

    mocker.patch.object(
        NodeMgmtSyncConfig.objects,
        "filter",
        side_effect=inject_winner_before_first_cas,
    )

    returned = NodeMgmtSyncService.update_task({"auto_sync_enabled": True, "auto_collect_enabled": True})

    returned.refresh_from_db()
    assert winner_injected is True
    assert returned.version == initial_version + 2
    assert returned.auto_sync_enabled is True
    assert returned.auto_collect_enabled is True


def test_stale_config_reconcile_cannot_reverse_newer_schedule():
    original = NodeMgmtSyncService.get_task()
    disabled = NodeMgmtSyncService.update_task({"auto_sync_enabled": False, "auto_collect_enabled": False})
    disabled_snapshot = NodeMgmtSyncConfig.objects.get(pk=disabled.pk)
    enabled = NodeMgmtSyncService.update_task({"auto_sync_enabled": True, "auto_collect_enabled": True})

    NodeMgmtSyncReconciler.reconcile(disabled_snapshot)

    current = NodeMgmtSyncConfig.objects.get(pk=enabled.pk)
    assert disabled.version == original.version + 1
    assert enabled.version == disabled.version + 1
    assert current.version == enabled.version
    assert current.auto_sync_enabled is True
    assert current.auto_collect_enabled is True
    assert _task_names() == {
        NodeMgmtSyncService.SYNC_PERIODIC_TASK_NAME,
        NodeMgmtSyncService.COLLECT_PERIODIC_TASK_NAME,
    }


def test_reconcile_does_not_rewrite_already_matching_schedules():
    NodeMgmtSyncService.get_task_payload(reconcile=True)

    with patch("apps.core.utils.celery_utils.CeleryUtils.create_or_update_periodic_task") as create_task:
        with patch("apps.core.utils.celery_utils.CeleryUtils.delete_periodic_task") as delete_task:
            payload = NodeMgmtSyncService.get_task_payload(reconcile=True)

    assert payload["schedule_status"] == "healthy"
    create_task.assert_not_called()
    delete_task.assert_not_called()


def test_update_increments_version_and_persists_degraded_health_on_beat_failure(
    caplog,
):
    config = NodeMgmtSyncService.get_task()
    original_version = config.version

    with patch(
        "apps.core.utils.celery_utils.CeleryUtils.create_or_update_periodic_task",
        side_effect=RuntimeError("secret-detail"),
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


def test_disabled_schedule_delete_failure_does_not_log_raw_exception(caplog):
    NodeMgmtSyncService.get_task_payload(reconcile=True)
    config = NodeMgmtSyncService.get_task()
    config.auto_sync_enabled = False
    config.save(update_fields=["auto_sync_enabled", "updated_at"])

    with patch.object(PeriodicTask.objects, "filter") as filter_tasks:
        filter_tasks.return_value.delete.side_effect = RuntimeError("secret-delete")
        payload = NodeMgmtSyncService.get_task_payload(reconcile=True)

    assert payload["schedule_status"] == "degraded"
    assert payload["reconcile_error_code"] == "RECONCILE_FAILED"
    assert "secret-delete" not in payload["reconcile_error_message"]
    assert "secret-delete" not in caplog.text


def test_get_task_is_pure_and_does_not_reconcile_schedules():
    config = NodeMgmtSyncService.get_task()

    assert config.auto_sync_enabled is True
    assert config.auto_collect_enabled is True
    assert _task_names() == set()
