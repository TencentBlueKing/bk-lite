"""Celery 内置周期任务与当前安装 App 的运行期对账。"""

import sys

import pytest
from django_celery_beat.models import IntervalSchedule, PeriodicTask

from apps.core import celery as celery_mod


pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def _run_setup(mocker, settings, *, installed_apps: tuple[str, ...]) -> None:
    settings.IS_USE_CELERY = True
    settings.INSTALLED_APPS = installed_apps
    settings.CELERY_BEAT_SCHEDULE = {}

    fake_sys = mocker.MagicMock()
    fake_modules = dict(sys.modules)
    fake_modules.pop("pytest", None)
    fake_sys.modules = fake_modules
    mocker.patch.object(celery_mod, "sys", fake_sys)

    celery_mod.setup_periodic_tasks(sender=None)


def test_excluded_app_tasks_are_suspended_without_touching_runnable_schedules(mocker, settings):
    interval, _ = IntervalSchedule.objects.get_or_create(every=60, period=IntervalSchedule.SECONDS)
    excluded = PeriodicTask.objects.create(
        name="test-excluded-alerts-task",
        task="apps.alerts.tasks.tasks.event_aggregation_alert",
        interval=interval,
        enabled=True,
    )
    installed = PeriodicTask.objects.create(
        name="test-installed-apm-task",
        task="apps.apm.tasks.reconcile_telemetry_catalog",
        interval=interval,
        enabled=True,
    )
    external = PeriodicTask.objects.create(
        name="test-external-task",
        task="company_tasks.hourly_report",
        interval=interval,
        enabled=True,
    )

    _run_setup(mocker, settings, installed_apps=("apps.core", "apps.apm"))

    excluded.refresh_from_db()
    installed.refresh_from_db()
    external.refresh_from_db()
    assert excluded.enabled is False
    assert installed.enabled is True
    assert external.enabled is True


def test_auto_suspended_task_is_restored_when_its_app_returns(mocker, settings):
    interval, _ = IntervalSchedule.objects.get_or_create(every=60, period=IntervalSchedule.SECONDS)
    task = PeriodicTask.objects.create(
        name="test-restored-alerts-task",
        task="apps.alerts.tasks.tasks.event_aggregation_alert",
        interval=interval,
        enabled=True,
        description="用户保留说明",
    )
    manually_disabled = PeriodicTask.objects.create(
        name="test-manually-disabled-alerts-task",
        task="apps.alerts.tasks.user_defined",
        interval=interval,
        enabled=False,
        description="用户主动停用",
    )

    _run_setup(mocker, settings, installed_apps=("apps.core", "apps.apm"))
    task.refresh_from_db()
    assert task.enabled is False

    _run_setup(mocker, settings, installed_apps=("apps.core", "apps.apm", "apps.alerts"))
    task.refresh_from_db()
    manually_disabled.refresh_from_db()
    assert task.enabled is True
    assert task.description == "用户保留说明"
    assert manually_disabled.enabled is False
    assert manually_disabled.description == "用户主动停用"
