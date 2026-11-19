"""ScheduledTaskService 单测（celery-beat PeriodicTask 集成）

直接使用 django_celery_beat 真实模型（测试库已迁移其表），覆盖
cron / once / 删除 / 切换 / 同步 及各无效分支。
"""

from datetime import timedelta
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
from django.db import DatabaseError
from django.utils import timezone
from django_celery_beat.models import CrontabSchedule, PeriodicTask
from rest_framework import serializers as drf_serializers

from apps.job_mgmt.constants import JobType, ScheduleType
from apps.job_mgmt.models import ScheduledTask
from apps.job_mgmt.serializers.scheduled_task import ScheduledTaskCreateSerializer, ScheduledTaskUpdateSerializer
from apps.job_mgmt.services.scheduled_task_service import ScheduledTaskService

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def _task(**over):
    defaults = {
        "name": "t",
        "job_type": JobType.SCRIPT,
        "schedule_type": ScheduleType.CRON,
        "cron_expression": "*/5 * * * *",
        "script_content": "echo",
        "script_type": "shell",
        "target_source": "node_mgmt",
        "target_list": [{"node_id": "n1"}],
        "team": [1],
        "is_enabled": True,
    }
    defaults.update(over)
    return ScheduledTask.objects.create(**defaults)


class TestCreatePeriodicTask:
    def test_cron_creates_periodic_task(self):
        st = _task()
        pt = ScheduledTaskService.create_periodic_task(st)
        assert pt is not None
        assert pt.name == ScheduledTaskService.get_periodic_task_name(st.id)
        assert pt.crontab is not None and pt.one_off is False
        assert pt.queue == "job"

    def test_once_creates_clocked_task(self):
        st = _task(schedule_type=ScheduleType.ONCE, cron_expression="", scheduled_time=timezone.now() + timedelta(hours=1))
        pt = ScheduledTaskService.create_periodic_task(st)
        assert pt is not None
        assert pt.clocked is not None and pt.one_off is True

    def test_cron_empty_expression_returns_none(self):
        st = _task(cron_expression="")
        assert ScheduledTaskService.create_periodic_task(st) is None

    def test_cron_invalid_expression_returns_none(self):
        st = _task(cron_expression="* * *")  # 非 5 段
        assert ScheduledTaskService.create_periodic_task(st) is None

    def test_once_without_time_returns_none(self):
        st = _task(schedule_type=ScheduleType.ONCE, cron_expression="", scheduled_time=None)
        assert ScheduledTaskService.create_periodic_task(st) is None

    def test_unknown_schedule_type_returns_none(self):
        st = _task(schedule_type="weird", cron_expression="")
        assert ScheduledTaskService.create_periodic_task(st) is None


class TestUpdateDeleteToggleSync:
    def test_update_recreates(self):
        st = _task()
        ScheduledTaskService.create_periodic_task(st)
        pt = ScheduledTaskService.update_periodic_task(st)
        assert pt is not None

    def test_delete_existing_returns_true(self):
        st = _task()
        ScheduledTaskService.create_periodic_task(st)
        assert ScheduledTaskService.delete_periodic_task(st.id) is True
        assert not PeriodicTask.objects.filter(name=ScheduledTaskService.get_periodic_task_name(st.id)).exists()

    def test_delete_missing_returns_false(self):
        assert ScheduledTaskService.delete_periodic_task(999999) is False

    def test_toggle_existing_returns_true(self):
        st = _task()
        ScheduledTaskService.create_periodic_task(st)
        assert ScheduledTaskService.toggle_periodic_task(st.id, False) is True
        pt = PeriodicTask.objects.get(name=ScheduledTaskService.get_periodic_task_name(st.id))
        assert pt.enabled is False

    def test_toggle_missing_returns_false(self):
        assert ScheduledTaskService.toggle_periodic_task(999999, True) is False

    def test_disable_missing_is_idempotent_success(self):
        assert ScheduledTaskService.toggle_periodic_task(999999, False) is True

    def test_toggle_or_raise_preserves_database_error(self):
        with patch(
            "apps.job_mgmt.services.scheduled_task_service.PeriodicTask.objects.filter",
            side_effect=DatabaseError("beat unavailable"),
        ), pytest.raises(DatabaseError, match="beat unavailable"):
            ScheduledTaskService.toggle_periodic_task_or_raise(1, False)

    def test_sync_returns_id(self):
        st = _task()
        pt_id = ScheduledTaskService.sync_periodic_task(st)
        assert isinstance(pt_id, int)

    def test_sync_returns_none_on_invalid(self):
        st = _task(cron_expression="")
        assert ScheduledTaskService.sync_periodic_task(st) is None


def _duplicate_every_five_minutes():
    """同一五段表达式各留一条 UTC 与 Asia/Shanghai，模拟客户环境里的系统调度行。"""
    fields = {
        "minute": "*/5",
        "hour": "*",
        "day_of_week": "*",
        "day_of_month": "*",
        "month_of_year": "*",
    }
    utc = CrontabSchedule.objects.create(**fields, timezone="UTC")
    shanghai = CrontabSchedule.objects.create(**fields, timezone="Asia/Shanghai")
    return utc, shanghai


def _expr_schedule_ids():
    return set(
        CrontabSchedule.objects.filter(
            minute="*/5",
            hour="*",
            day_of_week="*",
            day_of_month="*",
            month_of_year="*",
        ).values_list("id", flat=True)
    )


def _request(locale="zh-Hans"):
    request = MagicMock()
    request.user.username = "tester"
    request.user.locale = locale
    return request


def _create_payload(**over):
    payload = {
        "name": "every-five",
        "job_type": JobType.SCRIPT,
        "schedule_type": ScheduleType.CRON,
        "cron_expression": "*/5 * * * *",
        "script_content": "echo",
        "script_type": "shell",
        "target_source": "node_mgmt",
        "target_list": [{"node_id": "n1"}],
        "team": [1],
        "is_enabled": True,
    }
    payload.update(over)
    return payload


class TestDirtyCrontabTimezone:
    """同一 Cron 已有 UTC 与 Asia/Shanghai 两行时，保存必须命中当前时区那一行。"""

    def test_create_and_update_bind_current_timezone_and_keep_both_rows(self):
        utc, shanghai = _duplicate_every_five_minutes()
        preserved = {utc.id, shanghai.id}
        assert _expr_schedule_ids() == preserved

        created = ScheduledTaskCreateSerializer(context={"request": _request()}).create(_create_payload())
        created.refresh_from_db()
        periodic = PeriodicTask.objects.get(pk=created.periodic_task_id)
        assert periodic.crontab_id == utc.id
        assert str(periodic.crontab.timezone) == "UTC"
        assert _expr_schedule_ids() == preserved

        updated = ScheduledTaskUpdateSerializer(instance=created, context={"request": _request()}).update(
            created,
            {"name": "every-five-renamed", "cron_expression": "*/5 * * * *"},
        )
        updated.refresh_from_db()
        rebound = PeriodicTask.objects.get(pk=updated.periodic_task_id)
        assert updated.name == "every-five-renamed"
        assert rebound.crontab_id == utc.id
        assert str(rebound.crontab.timezone) == "UTC"
        assert CrontabSchedule.objects.filter(pk=utc.id).exists()
        assert CrontabSchedule.objects.filter(pk=shanghai.id).exists()
        assert _expr_schedule_ids() == preserved

        timezone.activate(ZoneInfo("Asia/Shanghai"))
        try:
            shanghai_task = ScheduledTaskCreateSerializer(context={"request": _request()}).create(_create_payload(name="every-five-shanghai"))
        finally:
            timezone.deactivate()

        shanghai_task.refresh_from_db()
        shanghai_periodic = PeriodicTask.objects.get(pk=shanghai_task.periodic_task_id)
        assert shanghai_periodic.crontab_id == shanghai.id
        assert str(shanghai_periodic.crontab.timezone) == "Asia/Shanghai"
        assert _expr_schedule_ids() == preserved

    def test_create_surfaces_underlying_exception(self):
        with patch(
            "apps.job_mgmt.serializers.scheduled_task.ScheduledTaskService.create_periodic_task",
            side_effect=RuntimeError("beat-duplicate-sentinel"),
        ), pytest.raises(drf_serializers.ValidationError) as exc_info:
            ScheduledTaskCreateSerializer(context={"request": _request()}).create(_create_payload(name="create-boom"))

        message = str(exc_info.value)
        assert "beat-duplicate-sentinel" in message
        assert "创建定时调度任务失败" in message
        assert "请检查 Cron 表达式或计划执行时间" not in message
        assert not ScheduledTask.objects.filter(name="create-boom").exists()

    def test_create_english_message_includes_exception(self):
        with patch(
            "apps.job_mgmt.serializers.scheduled_task.ScheduledTaskService.create_periodic_task",
            side_effect=RuntimeError("beat-duplicate-sentinel"),
        ), pytest.raises(drf_serializers.ValidationError) as exc_info:
            ScheduledTaskCreateSerializer(context={"request": _request("en")}).create(_create_payload(name="create-boom-en"))

        message = str(exc_info.value)
        assert "Failed to create the schedule: beat-duplicate-sentinel" in message
        assert not ScheduledTask.objects.filter(name="create-boom-en").exists()

    def test_update_surfaces_underlying_exception_and_rolls_back(self):
        task = _task(name="before-update", cron_expression="0 1 * * *")
        with patch(
            "apps.job_mgmt.serializers.scheduled_task.ScheduledTaskService.update_periodic_task",
            side_effect=RuntimeError("beat-update-sentinel"),
        ), pytest.raises(drf_serializers.ValidationError) as exc_info:
            ScheduledTaskUpdateSerializer(instance=task, context={"request": _request()}).update(
                task,
                {"name": "must-not-stick", "cron_expression": "*/5 * * * *"},
            )

        message = str(exc_info.value)
        assert "beat-update-sentinel" in message
        assert "更新定时调度任务失败" in message
        assert "请检查配置" not in message
        task.refresh_from_db()
        assert task.name == "before-update"
        assert task.cron_expression == "0 1 * * *"
