"""apps.core.mixinx.PeriodicTaskUtils 单元测试（真实 ORM 副作用）。

create_periodic_task / delete_periodic_task 直接操作 django_celery_beat 表。
使用真实测试 DB（django_db），断言真实 DB 副作用：
- 创建后 PeriodicTask 存在且关联 CrontabSchedule，时分正确；
- 重复创建走 update_or_create，不产生重复记录；
- 删除后记录消失。
"""

import pytest

from apps.core.mixinx import PeriodicTaskUtils

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_create_periodic_task_creates_record():
    from django_celery_beat.models import CrontabSchedule, PeriodicTask

    PeriodicTaskUtils.create_periodic_task(
        sync_time="08:30",
        task_name="core-test-job",
        task_args="[]",
        task_path="apps.core.tasks.demo",
    )

    task = PeriodicTask.objects.get(name="core-test-job")
    assert task.task == "apps.core.tasks.demo"
    assert task.enabled is True
    assert task.crontab.hour == "8"
    assert task.crontab.minute == "30"
    assert isinstance(task.crontab, CrontabSchedule)


def test_create_periodic_task_is_idempotent():
    from django_celery_beat.models import PeriodicTask

    PeriodicTaskUtils.create_periodic_task("09:15", "core-idem-job", "[]", "apps.core.tasks.a")
    PeriodicTaskUtils.create_periodic_task("10:45", "core-idem-job", "[1]", "apps.core.tasks.b")

    tasks = PeriodicTask.objects.filter(name="core-idem-job")
    assert tasks.count() == 1
    # 第二次覆盖了 task path 与调度
    task = tasks.first()
    assert task.task == "apps.core.tasks.b"
    assert task.crontab.hour == "10"
    assert task.crontab.minute == "45"


def test_delete_periodic_task_removes_record():
    from django_celery_beat.models import PeriodicTask

    PeriodicTaskUtils.create_periodic_task("06:00", "core-del-job", "[]", "apps.core.tasks.x")
    assert PeriodicTask.objects.filter(name="core-del-job").exists()

    PeriodicTaskUtils.delete_periodic_task("core-del-job")
    assert not PeriodicTask.objects.filter(name="core-del-job").exists()


def test_delete_nonexistent_task_is_noop():
    # 删除不存在的任务不应抛错
    PeriodicTaskUtils.delete_periodic_task("does-not-exist-job")
