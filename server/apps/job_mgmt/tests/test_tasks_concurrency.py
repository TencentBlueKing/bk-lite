"""execute_scheduled_task 并发竞态测试（GitHub issue #3421）

根因:
  - ``server/apps/job_mgmt/tasks.py`` 中 ``run_count += 1; save()`` 是应用层
    read-modify-write,两 Celery worker 并发触发同一 ``scheduled_task_id`` 时
    各自读到旧值,各自写入 ``N+1``,最终数据库只 +1。
  - SKIP/QUEUE 并发策略检查(``JobExecution.objects.filter(...).count()``)
    与 ``run_count`` 自增写入之间无事务/无锁,两个 worker 同时通过检查,
    SKIP 策略失效,作业被重复触发。

修复契约(本测试守护):
  1. ``run_count`` 累加必须走 ``F()`` 表达式原子 SQL。
  2. 策略检查 + 自增 + 创建 PENDING execution 必须包在 ``transaction.atomic()`` 内。
  3. ``ScheduledTask`` 行必须用 ``select_for_update()`` 加锁。
"""

import threading
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.db import connection, transaction
from django.utils import timezone

from apps.job_mgmt import tasks
from apps.job_mgmt.constants import ConcurrencyPolicy, JobType
from apps.job_mgmt.models import JobExecution, ScheduledTask

# 多线程必须 transaction=True,否则 pytest-django 默认一个事务包测试,
# 跨线程互相看不到对方写入,无法真实复现竞态
pytestmark = [pytest.mark.unit, pytest.mark.django_db(transaction=True)]


def _task(**over):
    defaults = {
        "name": "st",
        "job_type": JobType.SCRIPT,
        "schedule_type": "cron",
        "cron_expression": "* * * * *",
        "script_content": "echo hi",
        "script_type": "shell",
        "target_source": "node_mgmt",
        "target_list": [{"node_id": "n1"}],
        "team": [1],
        "is_enabled": True,
        "concurrency_policy": ConcurrencyPolicy.RUN,
    }
    defaults.update(over)
    return ScheduledTask.objects.create(**defaults)


def _call_in_thread(task_id, results: list, idx: int):
    """在线程中调用 execute_scheduled_task;通过 results 列表收集异常。

    每个线程必须 ``connection.close()`` 关闭 Django 的 thread-local 连接,
    避免测试结束时连接残留。
    """

    def runner():
        try:
            with patch("apps.job_mgmt.tasks._dispatch_execution_job", return_value=True), patch.object(
                tasks.DangerousChecker,
                "check_command",
                return_value=_safe_check_result(),
            ), patch.object(
                tasks.DangerousChecker,
                "check_path",
                return_value=_safe_check_result(),
            ):
                tasks.execute_scheduled_task(task_id)
        except Exception as exc:  # noqa: BLE001 — 收集到主线程再断言
            results.append((idx, exc))
        finally:
            connection.close()

    t = threading.Thread(target=runner)
    t.start()
    return t


def _safe_check_result():
    """构造 DangerousChecker.check_command 返回的安全结果对象。"""
    from types import SimpleNamespace

    return SimpleNamespace(can_execute=True, forbidden=[], warnings=[])


class TestRunCountAtomicity:
    def test_concurrent_run_count_increments_correctly(self):
        """两个 worker 并发触发同一任务,run_count 必须累加到 2,不能因 read-modify-write 漏算。"""
        st = _task()
        results: list = []
        t1 = _call_in_thread(st.id, results, 0)
        t2 = _call_in_thread(st.id, results, 1)
        t1.join(timeout=15)
        t2.join(timeout=15)
        assert not t1.is_alive() and not t2.is_alive(), "线程未在 15s 内结束,疑似死锁"
        assert results == [], f"线程内异常: {results}"
        st.refresh_from_db()
        assert st.run_count == 2, f"预期 run_count=2,实际={st.run_count}"

    def test_sequential_runs_increment_one_each(self):
        """修复后单线程 happy path 仍按 1 递增(回归保护)。"""
        st = _task()
        for _ in range(3):
            with patch("apps.job_mgmt.tasks._dispatch_execution_job", return_value=True), patch.object(
                tasks.DangerousChecker,
                "check_command",
                return_value=_safe_check_result(),
            ):
                tasks.execute_scheduled_task(st.id)
        st.refresh_from_db()
        assert st.run_count == 3


class TestSkipPolicyConcurrency:
    def test_concurrent_skip_blocks_second_execution(self):
        """SKIP 策略下并发触发只允许产生 1 条 JobExecution,run_count 只 +1(SKIP 命中 return 不自增)。"""
        st = _task(concurrency_policy=ConcurrencyPolicy.SKIP)
        results: list = []
        t1 = _call_in_thread(st.id, results, 0)
        t2 = _call_in_thread(st.id, results, 1)
        t1.join(timeout=15)
        t2.join(timeout=15)
        assert results == [], f"线程内异常: {results}"
        ex_count = JobExecution.objects.filter(scheduled_task=st).count()
        assert ex_count == 1, f"预期 SKIP 后只有 1 条 execution,实际={ex_count}"
        st.refresh_from_db()
        assert st.run_count == 1, f"SKIP 命中时只第一个 worker ++,预期 run_count=1,实际={st.run_count}"


class TestAtomicContract:
    def test_skip_check_runs_inside_atomic_block(self, mocker):
        """契约:策略检查 + run_count 自增 + 创建 execution 必须在 transaction.atomic 内。"""
        atomic_spy = mocker.spy(transaction, "atomic")
        st = _task()
        with patch("apps.job_mgmt.tasks._dispatch_execution_job", return_value=True), patch.object(
            tasks.DangerousChecker,
            "check_command",
            return_value=_safe_check_result(),
        ):
            tasks.execute_scheduled_task(st.id)
        assert atomic_spy.called, "execute_scheduled_task 必须包裹在 transaction.atomic 内"

    def test_select_for_update_locks_scheduled_task_row(self, mocker):
        """契约:必须用 select_for_update() 锁 ScheduledTask 行,否则 SKIP 竞态窗口未闭合。"""
        from apps.job_mgmt.models import ScheduledTask as ScheduledTaskModel

        sfu_spy = mocker.spy(ScheduledTaskModel.objects, "select_for_update")
        st = _task()
        with patch("apps.job_mgmt.tasks._dispatch_execution_job", return_value=True), patch.object(
            tasks.DangerousChecker,
            "check_command",
            return_value=_safe_check_result(),
        ):
            tasks.execute_scheduled_task(st.id)
        assert sfu_spy.called, "execute_scheduled_task 必须 select_for_update ScheduledTask 行"


class TestUpdatedAtRefresh:
    """守护 updated_at 不因 QuerySet.update() 不触发 auto_now 而静默失真。

    原代码 ``save(update_fields=[\"last_run_at\", \"run_count\", \"updated_at\"])`` 会刷新
    updated_at;改为 ``QuerySet.update(...)`` 后 Django 框架的 auto_now 不再生效,
    必须显式带 ``updated_at=now``,否则列表排序、同步、审计会悄悄失真。
    """

    def test_updated_at_refreshed_after_trigger(self):
        st = _task()
        old_updated_at = timezone.now() - timedelta(days=1)
        # 直接 UPDATE 绕过 auto_now,模拟一个"陈旧"的 updated_at
        ScheduledTask.objects.filter(id=st.id).update(updated_at=old_updated_at)
        st.refresh_from_db()
        assert st.updated_at == old_updated_at

        before = timezone.now()
        with patch("apps.job_mgmt.tasks._dispatch_execution_job", return_value=True), patch.object(
            tasks.DangerousChecker,
            "check_command",
            return_value=_safe_check_result(),
        ):
            tasks.execute_scheduled_task(st.id)

        st.refresh_from_db()
        # updated_at 必须被刷新到触发时刻附近(>= before),且显著晚于 old_updated_at
        assert st.updated_at >= before, f"updated_at 未刷新: {st.updated_at} < {before}"
        assert st.updated_at > old_updated_at, f"updated_at 未推进: {st.updated_at} <= {old_updated_at}"
        # 同时验证 last_run_at 与 run_count 都被正确更新
        assert st.last_run_at is not None
        assert st.last_run_at >= before
        assert st.run_count == 1
