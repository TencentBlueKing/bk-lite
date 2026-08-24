"""apps.core.celery.setup_periodic_tasks 单元测试。

该回调把 CELERY_BEAT_SCHEDULE 同步到 django_celery_beat 表。
以轻量状态双对象覆盖分支，并以真实 django_celery_beat ORM 覆盖差集更新，断言：
- pytest 环境/未开启 celery 时早退，空 schedule 不新增任务；
- crontab 与 interval 两种调度类型分别走不同的 ORM 写入分支，
  且写入参数契约正确（args/kwargs 经 json.dumps）；
- 仅带版本化所有权标记且退出完整配置快照的任务可被 enforce 禁用。
"""

import json
import sys
from contextlib import nullcontext
from datetime import timedelta
from types import SimpleNamespace

import pytest
from celery.schedules import crontab

from apps.core import celery as celery_mod

pytestmark = pytest.mark.unit


def _run(
    mocker,
    beat_schedule,
    is_use_celery=True,
    in_pytest=False,
    schedule_complete=True,
    reconcile_mode="shadow",
    periodic_model=None,
):
    """在受控环境下执行 setup_periodic_tasks，返回 mock 的 ORM 模型。"""
    # 函数内部 `from django.conf import settings`，需直接 patch 真实 settings 属性
    from django.conf import settings as dj_settings

    mocker.patch.object(dj_settings, "IS_USE_CELERY", is_use_celery, create=True)
    mocker.patch.object(dj_settings, "CELERY_BEAT_SCHEDULE", beat_schedule, create=True)
    mocker.patch.object(dj_settings, "CELERY_BEAT_SCHEDULE_COMPLETE", schedule_complete, create=True)
    mocker.patch.object(dj_settings, "CELERY_BEAT_SCHEDULE_RECONCILE_MODE", reconcile_mode, create=True)
    mocker.patch.object(celery_mod.transaction, "atomic", side_effect=lambda: nullcontext())

    # 控制 "pytest" in sys.modules 分支（celery_mod 引用模块级 sys）
    fake_sys = mocker.MagicMock()
    fake_modules = dict(sys.modules)
    if not in_pytest:
        fake_modules.pop("pytest", None)
    fake_sys.modules = fake_modules
    mocker.patch.object(celery_mod, "sys", fake_sys)

    crontab_model = mocker.MagicMock()
    crontab_schedule = mocker.MagicMock(name="cron")
    crontab_schedule.pk = 1
    crontab_model.objects.get_or_create.return_value = (crontab_schedule, True)
    interval_model = mocker.MagicMock()
    interval_schedule = mocker.MagicMock(name="interval")
    interval_schedule.pk = 1
    interval_model.objects.get_or_create.return_value = (interval_schedule, True)
    interval_model.SECONDS = "seconds"
    if periodic_model is None:
        periodic_model = mocker.MagicMock()
        periodic_row = _row("managed-task")
        periodic_row.save = mocker.MagicMock()
        periodic_model.objects.update_or_create.return_value = (periodic_row, True)

    import django_celery_beat.models as beat_models

    mocker.patch.object(beat_models, "CrontabSchedule", crontab_model)
    mocker.patch.object(beat_models, "IntervalSchedule", interval_model)
    mocker.patch.object(beat_models, "PeriodicTask", periodic_model)
    periodic_model.change_tracker = mocker.MagicMock()
    mocker.patch.object(beat_models, "PeriodicTasks", periodic_model.change_tracker)

    celery_mod.setup_periodic_tasks(sender=None)
    return crontab_model, interval_model, periodic_model


class _PeriodicTaskQuery:
    def __init__(self, manager, rows):
        self.manager = manager
        self.rows = rows

    def exclude(self, name__in):
        return _PeriodicTaskQuery(self.manager, [row for row in self.rows if row.name not in name__in])

    def __or__(self, other):
        rows = {row.name: row for row in self.rows}
        rows.update({row.name: row for row in other.rows})
        return _PeriodicTaskQuery(self.manager, list(rows.values()))

    def filter(self, **criteria):
        rows = self.rows
        for lookup, expected in criteria.items():
            if lookup == "description__contains":
                rows = [row for row in rows if expected in row.description]
            elif lookup == "description__endswith":
                rows = [row for row in rows if row.description.endswith(expected)]
            else:
                rows = [row for row in rows if getattr(row, lookup) == expected]
        return _PeriodicTaskQuery(self.manager, rows)

    def select_for_update(self):
        return self

    def select_related(self, *fields):
        return self

    def __getitem__(self, index):
        return self.rows[index]

    def order_by(self, field):
        return _PeriodicTaskQuery(self.manager, sorted(self.rows, key=lambda row: getattr(row, field)))

    def values_list(self, field, flat=False):
        assert flat is True
        return [getattr(row, field) for row in self.rows]

    def update(self, **values):
        for row in self.rows:
            for field, value in values.items():
                setattr(row, field, value)
        return len(self.rows)


class _PeriodicTaskManager:
    def __init__(self, rows=()):
        self.rows = {row.name: row for row in rows}

    def update_or_create(self, name, defaults):
        created = name not in self.rows
        row = self.rows.setdefault(
            name,
            SimpleNamespace(
                name=name,
                description="",
                enabled=True,
                last_run_at=None,
                crontab_id=None,
                interval_id=None,
                clocked_id=None,
                solar_id=None,
            ),
        )
        for field, value in defaults.items():
            setattr(row, field, value)
            if field in {"crontab", "interval"}:
                setattr(row, f"{field}_id", None if value is None else value.pk)
        row.save = lambda **kwargs: None
        return row, created

    def filter(self, **criteria):
        rows = list(self.rows.values())
        for lookup, expected in criteria.items():
            if lookup == "description__startswith":
                rows = [row for row in rows if row.description.startswith(expected)]
            else:
                rows = [row for row in rows if getattr(row, lookup) == expected]
        return _PeriodicTaskQuery(self, rows)


class _PeriodicTaskModel:
    def __init__(self, rows=()):
        self.objects = _PeriodicTaskManager(rows)


def _row(name, *, description="", enabled=True):
    return SimpleNamespace(
        name=name,
        task=f"apps.static.tasks.{name.replace('-', '_')}",
        args="[]",
        kwargs="{}",
        interval_id=1,
        crontab_id=None,
        solar_id=None,
        clocked_id=None,
        description=description,
        enabled=enabled,
        last_run_at="previous",
        save=lambda **kwargs: None,
    )


def _owned_row(name, *, enabled=True, disabled_by_reconcile=False, human_description=""):
    row = _row(name, enabled=enabled)
    lines = [celery_mod._managed_task_marker(row)]
    if disabled_by_reconcile:
        lines.append(celery_mod.RECONCILE_DISABLED_MARKER)
    if human_description:
        lines.append(human_description)
    row.description = "\n".join(lines)
    return row


class TestEarlyReturns:
    def test_pytest_env_returns_without_orm(self, mocker):
        cron, interval, periodic = _run(mocker, {"t": {}}, in_pytest=True)
        periodic.objects.update_or_create.assert_not_called()

    def test_celery_disabled_returns(self, mocker):
        cron, interval, periodic = _run(mocker, {"t": {}}, is_use_celery=False)
        periodic.objects.update_or_create.assert_not_called()

    def test_empty_schedule_does_not_create_task(self, mocker):
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

    def test_timedelta_schedule_branch(self, mocker):
        schedule = {"every-minute": {"task": "apps.patch_mgmt.tasks.watch", "schedule": timedelta(seconds=60)}}

        cron, interval, periodic = _run(mocker, schedule)

        interval.objects.get_or_create.assert_called_once_with(every=60, period="seconds")
        cron.objects.get_or_create.assert_not_called()
        assert periodic.objects.update_or_create.call_args.kwargs["name"] == "every-minute"

    def test_unsupported_schedule_marks_snapshot_incomplete(self, mocker, caplog):
        existing = _owned_row("unsupported-static")
        periodic = _PeriodicTaskModel([existing])

        _run(
            mocker,
            {"unsupported-static": {"task": existing.task, "schedule": object()}},
            periodic_model=periodic,
            reconcile_mode="enforce",
        )

        assert existing.enabled is True
        assert "不支持" in caplog.text
        assert "不完整" in caplog.text


class TestManagedScheduleReconciliation:
    def test_current_static_task_gets_versioned_owner_marker_without_losing_description(self, mocker):
        existing = _row("daily-job", description="管理员备注")
        periodic = _PeriodicTaskModel([existing])

        _run(
            mocker,
            {"daily-job": {"task": "apps.x.tasks.do_it", "schedule": 60}},
            periodic_model=periodic,
        )

        description = periodic.objects.rows["daily-job"].description
        assert description.startswith(celery_mod.MANAGED_TASK_DESCRIPTION_PREFIX)
        assert description.endswith("\n管理员备注")

    def test_repeated_sync_keeps_single_owner_marker_and_description(self, mocker):
        existing = _row("daily-job", description="管理员备注")
        periodic = _PeriodicTaskModel([existing])
        schedule = {"daily-job": {"task": "apps.x.tasks.do_it", "schedule": 60}}

        _run(mocker, schedule, periodic_model=periodic)
        _run(mocker, schedule, periodic_model=periodic)

        description = periodic.objects.rows["daily-job"].description
        assert description.count(celery_mod.MANAGED_TASK_DESCRIPTION_PREFIX) == 1
        assert description.endswith("\n管理员备注")

    def test_shadow_mode_reports_but_does_not_disable_removed_owned_task(self, mocker, caplog):
        removed = _owned_row("removed-static")
        periodic = _PeriodicTaskModel([removed])

        _run(mocker, {}, periodic_model=periodic, reconcile_mode="shadow")

        assert removed.enabled is True
        assert "removed-static" in caplog.text

    def test_enforce_mode_disables_only_removed_owned_task(self, mocker):
        removed = _owned_row("removed-static")
        dynamic = _row("job_mgmt_scheduled_task_42", description="管理员创建")
        periodic = _PeriodicTaskModel([removed, dynamic])

        _run(mocker, {}, periodic_model=periodic, reconcile_mode="enforce")

        assert removed.enabled is False
        assert removed.last_run_at is None
        assert celery_mod.RECONCILE_DISABLED_MARKER in removed.description
        assert dynamic.enabled is True
        periodic.change_tracker.update_changed.assert_called_once_with()

    def test_rename_disables_owned_old_name_and_creates_new_name(self, mocker):
        old = _owned_row("old-static")
        periodic = _PeriodicTaskModel([old])

        _run(
            mocker,
            {"new-static": {"task": "apps.x.tasks.renamed", "schedule": 60}},
            periodic_model=periodic,
            reconcile_mode="enforce",
        )

        assert old.enabled is False
        assert periodic.objects.rows["new-static"].enabled is True

    def test_incomplete_snapshot_never_disables_removed_owned_task(self, mocker, caplog):
        removed = _owned_row("removed-static")
        periodic = _PeriodicTaskModel([removed])

        _run(
            mocker,
            {},
            periodic_model=periodic,
            reconcile_mode="enforce",
            schedule_complete=False,
        )

        assert removed.enabled is True
        assert "不完整" in caplog.text

    def test_reappearing_owned_task_is_enabled_again(self, mocker):
        restored = _owned_row("restored-static", enabled=False, disabled_by_reconcile=True)
        periodic = _PeriodicTaskModel([restored])

        _run(
            mocker,
            {"restored-static": {"task": "apps.x.tasks.do_it", "schedule": 60}},
            periodic_model=periodic,
            reconcile_mode="enforce",
        )

        assert restored.enabled is True

    def test_restore_mode_rolls_back_only_prior_enforcement(self, mocker):
        removed = _owned_row("removed-static", enabled=False, disabled_by_reconcile=True)
        dynamic = _row("job_mgmt_scheduled_task_42", description="管理员创建", enabled=False)
        periodic = _PeriodicTaskModel([removed, dynamic])

        _run(mocker, {}, periodic_model=periodic, reconcile_mode="restore")

        assert removed.enabled is True
        assert removed.last_run_at is None
        assert "disabled-by-reconcile" not in removed.description
        assert dynamic.enabled is False
        periodic.change_tracker.update_changed.assert_called_once_with()

    def test_restore_mode_keeps_manually_disabled_owned_task(self, mocker):
        manual = _owned_row("manual-disabled-static", enabled=False)
        periodic = _PeriodicTaskModel([manual])

        _run(
            mocker,
            {},
            periodic_model=periodic,
            reconcile_mode="restore",
            schedule_complete=False,
        )

        assert manual.enabled is False
        periodic.change_tracker.update_changed.assert_not_called()

    def test_repeated_enforcement_has_no_extra_scheduler_write(self, mocker):
        removed = _owned_row("removed-static")
        periodic = _PeriodicTaskModel([removed])

        _run(mocker, {}, periodic_model=periodic, reconcile_mode="enforce")
        first_tracker = periodic.change_tracker
        _run(mocker, {}, periodic_model=periodic, reconcile_mode="enforce")

        first_tracker.update_changed.assert_called_once_with()
        periodic.change_tracker.update_changed.assert_not_called()

    def test_unknown_mode_warns_and_keeps_task_enabled(self, mocker, caplog):
        removed = _owned_row("removed-static")
        periodic = _PeriodicTaskModel([removed])

        _run(mocker, {}, periodic_model=periodic, reconcile_mode="enfoce")

        assert removed.enabled is True
        assert "enfoce" in caplog.text


class TestBeatScheduleLoading:
    def test_internal_import_failure_marks_snapshot_incomplete(self):
        from config.components.celery import _load_beat_schedule

        def importer(module_name):
            if module_name == "apps.healthy.config":
                return SimpleNamespace(CELERY_BEAT_SCHEDULE={"healthy": {"schedule": 60}})
            error = ModuleNotFoundError("missing optional dependency")
            error.name = "optional_dependency"
            raise error

        schedule, complete = _load_beat_schedule(["apps.healthy", "apps.broken"], importer=importer)

        assert schedule == {"healthy": {"schedule": 60}}
        assert complete is False

    def test_app_without_config_is_not_an_incomplete_snapshot(self):
        from config.components.celery import _load_beat_schedule

        def importer(module_name):
            error = ModuleNotFoundError(f"No module named {module_name}")
            error.name = module_name
            raise error

        schedule, complete = _load_beat_schedule(["apps.without_config"], importer=importer)

        assert schedule == {}
        assert complete is True
