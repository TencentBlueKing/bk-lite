"""ScheduledTaskService 单测（celery-beat PeriodicTask 集成）

直接使用 django_celery_beat 真实模型（测试库已迁移其表），覆盖
cron / once / 删除 / 切换 / 同步 及各无效分支。
"""

from datetime import timedelta

import pytest
from django.utils import timezone
from django_celery_beat.models import PeriodicTask

from apps.job_mgmt.constants import JobType, ScheduleType
from apps.job_mgmt.models import ScheduledTask
from apps.job_mgmt.services.scheduled_task_service import ScheduledTaskService

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


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

    def test_sync_returns_id(self):
        st = _task()
        pt_id = ScheduledTaskService.sync_periodic_task(st)
        assert isinstance(pt_id, int)

    def test_sync_returns_none_on_invalid(self):
        st = _task(cron_expression="")
        assert ScheduledTaskService.sync_periodic_task(st) is None
