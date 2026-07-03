"""apps.core.celery.setup_periodic_tasks 单元测试。

该回调把 CELERY_BEAT_SCHEDULE 同步到 django_celery_beat 表。
仅 mock 真实外部边界（django_celery_beat ORM 模型、settings），断言：
- pytest 环境/未开启 celery/空 schedule 时早退；
- crontab 与 interval 两种调度类型分别走不同的 ORM 写入分支，
  且写入参数契约正确（args/kwargs 经 json.dumps）。
"""

import json
import sys

import pytest
from celery.schedules import crontab

from apps.core import celery as celery_mod

pytestmark = pytest.mark.unit


def _run(mocker, beat_schedule, is_use_celery=True, in_pytest=False):
    """在受控环境下执行 setup_periodic_tasks，返回 mock 的 ORM 模型。"""
    # 函数内部 `from django.conf import settings`，需直接 patch 真实 settings 属性
    from django.conf import settings as dj_settings

    mocker.patch.object(dj_settings, "IS_USE_CELERY", is_use_celery, create=True)
    mocker.patch.object(dj_settings, "CELERY_BEAT_SCHEDULE", beat_schedule, create=True)

    # 控制 "pytest" in sys.modules 分支（celery_mod 引用模块级 sys）
    fake_sys = mocker.MagicMock()
    fake_modules = dict(sys.modules)
    if not in_pytest:
        fake_modules.pop("pytest", None)
    fake_sys.modules = fake_modules
    mocker.patch.object(celery_mod, "sys", fake_sys)

    crontab_model = mocker.MagicMock()
    crontab_model.objects.get_or_create.return_value = (mocker.MagicMock(name="cron"), True)
    interval_model = mocker.MagicMock()
    interval_model.objects.get_or_create.return_value = (mocker.MagicMock(name="interval"), True)
    interval_model.SECONDS = "seconds"
    periodic_model = mocker.MagicMock()

    import django_celery_beat.models as beat_models

    mocker.patch.object(beat_models, "CrontabSchedule", crontab_model)
    mocker.patch.object(beat_models, "IntervalSchedule", interval_model)
    mocker.patch.object(beat_models, "PeriodicTask", periodic_model)

    celery_mod.setup_periodic_tasks(sender=None)
    return crontab_model, interval_model, periodic_model


class TestEarlyReturns:
    def test_pytest_env_returns_without_orm(self, mocker):
        cron, interval, periodic = _run(mocker, {"t": {}}, in_pytest=True)
        periodic.objects.update_or_create.assert_not_called()

    def test_celery_disabled_returns(self, mocker):
        cron, interval, periodic = _run(mocker, {"t": {}}, is_use_celery=False)
        periodic.objects.update_or_create.assert_not_called()

    def test_empty_schedule_returns(self, mocker):
        cron, interval, periodic = _run(mocker, {})
        periodic.objects.update_or_create.assert_not_called()


class TestScheduleSync:
    def test_crontab_schedule_branch(self, mocker):
        schedule = {
            "daily-job": {
                "task": "apps.x.tasks.do_it",
                "schedule": crontab(minute=30, hour=2),
                "args": [1, 2],
                "kwargs": {"k": "v"},
            }
        }
        cron, interval, periodic = _run(mocker, schedule)

        cron.objects.get_or_create.assert_called_once()
        gkwargs = cron.objects.get_or_create.call_args.kwargs
        assert gkwargs["minute"] == 30
        assert gkwargs["hour"] == 2

        interval.objects.get_or_create.assert_not_called()
        periodic.objects.update_or_create.assert_called_once()
        pkwargs = periodic.objects.update_or_create.call_args.kwargs
        assert periodic.objects.update_or_create.call_args.kwargs["name"] == "daily-job"
        assert pkwargs["defaults"]["task"] == "apps.x.tasks.do_it"
        assert pkwargs["defaults"]["args"] == json.dumps([1, 2])
        assert pkwargs["defaults"]["kwargs"] == json.dumps({"k": "v"})
        assert pkwargs["defaults"]["interval"] is None

    def test_interval_schedule_branch(self, mocker):
        schedule = {"every-60s": {"task": "apps.y.tasks.poll", "schedule": 60}}
        cron, interval, periodic = _run(mocker, schedule)

        interval.objects.get_or_create.assert_called_once_with(every=60, period="seconds")
        cron.objects.get_or_create.assert_not_called()
        pkwargs = periodic.objects.update_or_create.call_args.kwargs
        assert pkwargs["defaults"]["crontab"] is None
        # 缺省 args/kwargs 走默认空
        assert pkwargs["defaults"]["args"] == json.dumps([])
        assert pkwargs["defaults"]["kwargs"] == json.dumps({})
