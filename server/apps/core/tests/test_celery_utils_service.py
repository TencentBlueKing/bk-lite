import pydantic.root_model  # noqa

import json

import pytest
from django_celery_beat.models import CrontabSchedule, IntervalSchedule, PeriodicTask

from apps.core.utils.celery_utils import CeleryUtils, crontab_format

pytestmark = pytest.mark.django_db


class TestCrontabFormat:
    def test_cycle(self):
        assert crontab_format("cycle", "5") == (True, "*/5 * * * *")

    def test_timing(self):
        assert crontab_format("timing", "08:30") == (True, "30 8 * * *")

    def test_close(self):
        assert crontab_format("close", "") == (False, "")

    def test_timing_bad_format_raises(self):
        with pytest.raises(Exception):
            crontab_format("timing", "0830")

    def test_unknown_type_raises(self):
        with pytest.raises(Exception):
            crontab_format("nope", "1")


class TestGetOrCreateCrontabSchedule:
    def test_creates_and_reuses(self):
        s1 = CeleryUtils.get_or_create_crontab_schedule("0", "1", "*", "*", "*")
        s2 = CeleryUtils.get_or_create_crontab_schedule("0", "1", "*", "*", "*")
        assert s1.id == s2.id

    def test_reuses_first_when_duplicates_exist(self, mocker):
        # 模拟历史重复数据：get_or_create 抛 MultipleObjectsReturned，回退取首条
        from django.core.exceptions import MultipleObjectsReturned

        sched = CrontabSchedule.objects.create(minute="9", hour="9", day_of_month="*", month_of_year="*", day_of_week="*")
        mocker.patch.object(CrontabSchedule.objects, "get_or_create", side_effect=MultipleObjectsReturned)
        result = CeleryUtils.get_or_create_crontab_schedule("9", "9", "*", "*", "*")
        assert result.id == sched.id


class TestPeriodicTaskCRUD:
    def test_create_with_crontab(self):
        task = CeleryUtils.create_or_update_periodic_task(
            name="t_cron", crontab="*/10 * * * *", task="apps.x.task", args=[1], kwargs={"a": 1}
        )
        assert task.crontab is not None
        assert task.interval is None
        assert json.loads(task.args) == [1]
        assert json.loads(task.kwargs) == {"a": 1}

    def test_create_with_interval(self):
        task = CeleryUtils.create_or_update_periodic_task(name="t_int", interval=30, task="apps.x.task")
        assert task.interval is not None
        assert task.crontab is None
        assert task.args == "[]"
        assert task.kwargs == "{}"

    def test_update_existing_switches_schedule(self):
        CeleryUtils.create_or_update_periodic_task(name="t_switch", interval=15, task="apps.x.t")
        updated = CeleryUtils.create_or_update_periodic_task(name="t_switch", crontab="0 0 * * *", task="apps.x.t")
        assert updated.crontab is not None
        assert updated.interval is None
        assert PeriodicTask.objects.filter(name="t_switch").count() == 1

    def test_neither_crontab_nor_interval_raises(self):
        with pytest.raises(ValueError):
            CeleryUtils.create_or_update_periodic_task(name="bad", task="apps.x.t")

    def test_delete_existing(self):
        CeleryUtils.create_or_update_periodic_task(name="t_del", interval=5, task="apps.x.t")
        assert CeleryUtils.delete_periodic_task("t_del") == 1

    def test_delete_missing_returns_zero(self):
        assert CeleryUtils.delete_periodic_task("does-not-exist") == 0

    def test_get_periodic_task(self):
        CeleryUtils.create_or_update_periodic_task(name="t_get", interval=5, task="apps.x.t")
        assert CeleryUtils.get_periodic_task("t_get").name == "t_get"
        assert CeleryUtils.get_periodic_task("nope") is None

    def test_get_all_periodic_tasks(self):
        CeleryUtils.create_or_update_periodic_task(name="t_all", interval=5, task="apps.x.t")
        names = set(CeleryUtils.get_all_periodic_tasks().values_list("name", flat=True))
        assert "t_all" in names

    def test_enable_disable_and_is_enabled(self):
        CeleryUtils.create_or_update_periodic_task(name="t_en", interval=5, task="apps.x.t", enabled=False)
        assert CeleryUtils.is_task_enabled("t_en") is False
        assert CeleryUtils.enable_periodic_task("t_en") is True
        assert CeleryUtils.is_task_enabled("t_en") is True
        assert CeleryUtils.disable_periodic_task("t_en") is True
        assert CeleryUtils.is_task_enabled("t_en") is False

    def test_enable_missing_returns_false(self):
        assert CeleryUtils.enable_periodic_task("missing") is False

    def test_disable_missing_returns_false(self):
        assert CeleryUtils.disable_periodic_task("missing") is False

    def test_is_enabled_missing_returns_none(self):
        assert CeleryUtils.is_task_enabled("missing") is None

    def test_interval_schedule_reused(self):
        CeleryUtils.create_or_update_periodic_task(name="t_i1", interval=42, task="apps.x.t")
        CeleryUtils.create_or_update_periodic_task(name="t_i2", interval=42, task="apps.x.t")
        assert IntervalSchedule.objects.filter(every=42, period="seconds").count() == 1
