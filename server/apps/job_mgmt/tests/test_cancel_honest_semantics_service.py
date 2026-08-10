"""作业取消语义诚实化测试 (Issue #2964 方案 C)

覆盖：
1. CANCELLING 状态机定义（非终态）
2. is_cancelled / prepare_execution 对 CANCELLING 生效
3. 取消接口 CAS 分流：PENDING→CANCELLED、RUNNING→CANCELLING、终态/取消中 400
"""

from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.job_mgmt.constants import CallbackType, ExecutionStatus, JobType, TargetSource
from apps.job_mgmt.models import JobCompletionOutbox, JobExecution
from apps.job_mgmt.nats_api import ansible_task_callback, job_task_terminate
from apps.job_mgmt.services.execution_base_service import ExecutionTaskBaseService
from apps.job_mgmt.services.execution_cancellation_service import (
    ExecutionCancellationAuthorizationError,
    ExecutionCancellationError,
    request_execution_cancel,
)
from apps.job_mgmt.services.file_distribution_runner import FileDistributionRunner
from apps.job_mgmt.services.script_execution_runner import ScriptExecutionRunner
from apps.job_mgmt.tasks import dispatch_pending_job_completion_outbox, finalize_cancelling_execution
from apps.job_mgmt.tests.callback_helpers import authorize_execution, callback_context

pytestmark = pytest.mark.integration


def _make_execution(status, **kwargs):
    defaults = dict(
        name="t",
        job_type=JobType.SCRIPT,
        status=status,
        target_source=TargetSource.MANUAL,
        target_list=[{"target_id": 5, "name": "h1", "ip": "1.1.1.1"}],
        timeout=60,
        team=[1],
        created_by="testuser",
        updated_by="testuser",
    )
    defaults.update(kwargs)
    return authorize_execution(JobExecution.objects.create(**defaults))


class TestCancellingStatusDefinition:
    """CANCELLING 状态机定义"""

    def test_cancelling_value(self):
        assert ExecutionStatus.CANCELLING == "cancelling"

    def test_cancelling_is_not_terminal(self):
        assert ExecutionStatus.CANCELLING not in ExecutionStatus.TERMINAL_STATES

    def test_cancelling_in_choices(self):
        assert (ExecutionStatus.CANCELLING, "取消中") in ExecutionStatus.CHOICES


@pytest.mark.django_db
class TestIsCancelledWithCancelling:
    """is_cancelled 对 CANCELLING 生效，使 Runner 现有检查点自动响应取消请求"""

    def test_cancelling_is_treated_as_cancelled(self):
        execution = _make_execution(ExecutionStatus.CANCELLING)
        assert ExecutionTaskBaseService.is_cancelled(execution.id) is True

    def test_cancelled_still_treated_as_cancelled(self):
        execution = _make_execution(ExecutionStatus.CANCELLED)
        assert ExecutionTaskBaseService.is_cancelled(execution.id) is True

    def test_running_is_not_cancelled(self):
        execution = _make_execution(ExecutionStatus.RUNNING)
        assert ExecutionTaskBaseService.is_cancelled(execution.id) is False


@pytest.mark.django_db
class TestPrepareExecutionWithCancelling:
    """prepare_execution 拦截 CANCELLING/CANCELLED 的任务，不再进入执行"""

    def test_cancelling_execution_is_skipped(self):
        execution = _make_execution(ExecutionStatus.CANCELLING)
        service = ExecutionTaskBaseService(execution.id, "test_task")
        result, target_list = service.prepare_execution()
        assert result is None
        assert target_list == []
        execution.refresh_from_db()
        assert execution.status == ExecutionStatus.CANCELLING  # 不被改写为 RUNNING

    def test_cancelled_execution_is_skipped(self):
        execution = _make_execution(ExecutionStatus.CANCELLED)
        service = ExecutionTaskBaseService(execution.id, "test_task")
        result, target_list = service.prepare_execution()
        assert result is None
        assert target_list == []


@pytest.mark.django_db
class TestCancelViewCAS:
    """取消接口按当前状态 CAS 分流，消除竞态与假取消"""

    @pytest.fixture(autouse=True)
    def _grant_permission(self, authenticated_user):
        authenticated_user.is_superuser = True
        return authenticated_user

    def _cancel(self, api_client, execution):
        return api_client.post(f"/api/v1/job_mgmt/api/execution/{execution.id}/cancel/")

    def test_pending_execution_cancelled_directly(self, api_client):
        execution = _make_execution(ExecutionStatus.PENDING)
        resp = self._cancel(api_client, execution)
        assert resp.status_code == 200
        assert resp.data["status"] == ExecutionStatus.CANCELLED
        execution.refresh_from_db()
        assert execution.status == ExecutionStatus.CANCELLED
        assert execution.finished_at is not None

    def test_running_execution_enters_cancelling(self, api_client, django_capture_on_commit_callbacks):
        execution = _make_execution(ExecutionStatus.RUNNING)
        with patch("apps.job_mgmt.tasks.finalize_cancelling_execution") as mock_task:
            with django_capture_on_commit_callbacks(execute=True):
                resp = self._cancel(api_client, execution)
        assert resp.status_code == 200
        assert resp.data["status"] == ExecutionStatus.CANCELLING
        execution.refresh_from_db()
        assert execution.status == ExecutionStatus.CANCELLING
        assert execution.finished_at is None  # 非终态，等待真实结果回写

        # 兜底收敛任务以 execution.timeout + 缓冲调度
        mock_task.apply_async.assert_called_once()
        _, kwargs = mock_task.apply_async.call_args
        assert kwargs["args"] == [execution.id]
        assert kwargs["countdown"] > execution.timeout

    def test_broker_failure_keeps_persistent_cancel_deadline(self, api_client, django_capture_on_commit_callbacks):
        execution = _make_execution(ExecutionStatus.RUNNING)

        with patch(
            "apps.job_mgmt.tasks.finalize_cancelling_execution.apply_async",
            side_effect=RuntimeError("broker down"),
        ):
            with django_capture_on_commit_callbacks(execute=True):
                resp = self._cancel(api_client, execution)

        assert resp.status_code == 200
        execution.refresh_from_db()
        assert execution.status == ExecutionStatus.CANCELLING
        assert execution.cancel_finalize_at is not None
        assert execution.cancel_finalize_at > timezone.now() + timedelta(seconds=execution.timeout)

    def test_running_cancel_revokes_celery_task(self, api_client, django_capture_on_commit_callbacks):
        execution = _make_execution(ExecutionStatus.RUNNING, celery_task_id="ct-1")
        with patch("apps.job_mgmt.tasks.finalize_cancelling_execution"):
            with patch("apps.job_mgmt.services.execution_cancellation_service.current_app.control.revoke") as mock_revoke:
                with django_capture_on_commit_callbacks(execute=True):
                    resp = self._cancel(api_client, execution)
        assert resp.status_code == 200
        mock_revoke.assert_called_once_with("ct-1")

    def test_terminal_execution_cannot_cancel(self, api_client):
        execution = _make_execution(ExecutionStatus.SUCCESS)
        resp = self._cancel(api_client, execution)
        assert resp.status_code == 400
        execution.refresh_from_db()
        assert execution.status == ExecutionStatus.SUCCESS

    def test_cancelling_execution_cannot_cancel_again(self, api_client):
        execution = _make_execution(ExecutionStatus.CANCELLING)
        resp = self._cancel(api_client, execution)
        assert resp.status_code == 400
        execution.refresh_from_db()
        assert execution.status == ExecutionStatus.CANCELLING

    def test_revoke_failure_does_not_block_cancel(self, api_client, django_capture_on_commit_callbacks):
        """revoke 是尽力而为：失败不阻断取消流程"""
        execution = _make_execution(ExecutionStatus.PENDING, celery_task_id="ct-2")
        with patch("apps.job_mgmt.services.execution_cancellation_service.current_app.control.revoke", side_effect=Exception("broker down")):
            with django_capture_on_commit_callbacks(execute=True):
                resp = self._cancel(api_client, execution)
        assert resp.status_code == 200
        execution.refresh_from_db()
        assert execution.status == ExecutionStatus.CANCELLED

    def test_concurrent_state_change_returns_400(self, api_client):
        """检查后状态被并发改变（两次 CAS 都未命中）时按最新状态拒绝"""
        execution = _make_execution(ExecutionStatus.RUNNING)
        with patch(
            "apps.job_mgmt.views.execution.request_execution_cancel",
            side_effect=ExecutionCancellationError("状态已变更，请刷新后重试"),
        ):
            resp = self._cancel(api_client, execution)
        assert resp.status_code == 400
        assert "状态已变更" in resp.data["error"]


@pytest.mark.django_db
class TestTerminateTaskNatsAPI:
    @pytest.fixture(autouse=True)
    def _authenticated_caller(self):
        with patch("apps.job_mgmt.nats_api._verify_token", return_value=SimpleNamespace(group_list=[1])):
            yield

    def test_pending_execution_is_cancelled_directly(self):
        execution = _make_execution(ExecutionStatus.PENDING)

        result = job_task_terminate({"task_id": execution.id, "caller_token": "valid-token"})

        assert result["result"] is True
        assert result["data"]["status"] == ExecutionStatus.CANCELLED
        execution.refresh_from_db()
        assert execution.status == ExecutionStatus.CANCELLED
        assert execution.finished_at is not None

    def test_pending_cancel_persists_nats_notification_outbox(self):
        execution = _make_execution(
            ExecutionStatus.PENDING,
            callback_type=CallbackType.NATS,
            callback_subject="bklite.job.cancelled",
        )

        with patch("apps.job_mgmt.services.completion_outbox_service._schedule_deliveries"):
            result = job_task_terminate({"task_id": execution.id, "caller_token": "valid-token"})

        assert result["result"] is True
        record = JobCompletionOutbox.objects.get(
            execution_id=execution.id,
            kind=JobCompletionOutbox.Kind.NATS_CALLBACK,
        )
        assert record.payload["callback_payload"]["status"] == ExecutionStatus.CANCELLED
        assert record.payload["delivery_id"]

    def test_running_execution_enters_cancelling(self, django_capture_on_commit_callbacks):
        execution = _make_execution(ExecutionStatus.RUNNING)

        with patch("apps.job_mgmt.tasks.finalize_cancelling_execution") as mock_task:
            with django_capture_on_commit_callbacks(execute=True):
                result = job_task_terminate({"task_id": execution.id, "caller_token": "valid-token"})

        assert result["result"] is True
        assert result["data"]["status"] == ExecutionStatus.CANCELLING
        execution.refresh_from_db()
        assert execution.status == ExecutionStatus.CANCELLING
        assert execution.finished_at is None
        mock_task.apply_async.assert_called_once()
        _, kwargs = mock_task.apply_async.call_args
        assert kwargs["args"] == [execution.id]
        assert kwargs["countdown"] > execution.timeout

    def test_broker_failure_keeps_persistent_cancel_deadline(self, django_capture_on_commit_callbacks):
        execution = _make_execution(ExecutionStatus.RUNNING)

        with patch(
            "apps.job_mgmt.tasks.finalize_cancelling_execution.apply_async",
            side_effect=RuntimeError("broker down"),
        ):
            with django_capture_on_commit_callbacks(execute=True):
                result = job_task_terminate({"task_id": execution.id, "caller_token": "valid-token"})

        assert result["result"] is True
        execution.refresh_from_db()
        assert execution.status == ExecutionStatus.CANCELLING
        assert execution.cancel_finalize_at is not None

    def test_missing_caller_token_rejected(self):
        """不传 caller_token 时拒绝取消，防止伪造团队身份。"""
        execution = _make_execution(ExecutionStatus.PENDING)

        result = job_task_terminate({"task_id": execution.id})

        assert result["result"] is False
        assert "caller_token" in result["message"]
        execution.refresh_from_db()
        assert execution.status == ExecutionStatus.PENDING  # 状态未变

    @pytest.mark.parametrize(
        "task_id",
        [True, {}, [], "abc", "", "0", -1, 2**63, str(2**63), "9" * 5000],
    )
    def test_invalid_task_id_rejected_without_querying_orm(self, task_id):
        result = job_task_terminate({"task_id": task_id, "caller_token": "valid-token"})

        assert result["result"] is False
        assert "task_id 必须为正整数" in result["message"]

    def test_invalid_caller_token_rejected(self):
        execution = _make_execution(ExecutionStatus.PENDING)

        with patch("apps.job_mgmt.nats_api._verify_token", side_effect=ValueError("expired")):
            result = job_task_terminate({"task_id": execution.id, "caller_token": "invalid"})

        assert result == {"result": False, "message": "Unauthorized: invalid caller_token"}
        execution.refresh_from_db()
        assert execution.status == ExecutionStatus.PENDING

    def test_wrong_team_cannot_cancel(self):
        """调用方 team 与执行记录 team 无交集时，返回无权操作"""
        execution = _make_execution(ExecutionStatus.PENDING, team=[1])

        with patch("apps.job_mgmt.nats_api._verify_token", return_value=SimpleNamespace(group_list=[999])):
            result = job_task_terminate({"task_id": execution.id, "caller_token": "valid-token"})

        assert result["result"] is False
        assert "无权取消" in result["message"]
        execution.refresh_from_db()
        assert execution.status == ExecutionStatus.PENDING  # 状态未变

    def test_overlapping_team_can_cancel(self):
        """调用方 team 与执行记录 team 有交集时，正常取消"""
        execution = _make_execution(ExecutionStatus.PENDING, team=[1, 2])

        with patch("apps.job_mgmt.nats_api._verify_token", return_value=SimpleNamespace(group_list=[2, 3])):
            result = job_task_terminate({"task_id": execution.id, "caller_token": "valid-token"})

        assert result["result"] is True
        assert result["data"]["status"] == ExecutionStatus.CANCELLED
        execution.refresh_from_db()
        assert execution.status == ExecutionStatus.CANCELLED

    def test_kwargs_caller_token_can_cancel(self):
        """NATS request(..., task_id=..., caller_token=...) 的 kwargs 调用路径也必须可用。"""
        execution = _make_execution(ExecutionStatus.PENDING, team=[1])

        result = job_task_terminate(task_id=execution.id, caller_token="valid-token")

        assert result["result"] is True
        execution.refresh_from_db()
        assert execution.status == ExecutionStatus.CANCELLED


@pytest.mark.django_db
def test_cancel_service_rechecks_team_on_locked_row():
    execution = _make_execution(ExecutionStatus.PENDING, team=[2])

    with pytest.raises(ExecutionCancellationAuthorizationError, match="无权取消"):
        request_execution_cancel(execution.id, authorized_team_ids={1})

    execution.refresh_from_db()
    assert execution.status == ExecutionStatus.PENDING


@pytest.mark.django_db(transaction=True)
def test_cancel_commit_fences_late_worker_start():
    """取消先锁住 PENDING 行时，晚到 worker 只能看到 CANCELLED，不能覆盖为 RUNNING。"""
    execution = _make_execution(ExecutionStatus.PENDING)
    cancel_has_lock = Event()
    release_cancel = Event()

    def pause_after_cancel_lock(obj_team, authorized_team_ids):
        cancel_has_lock.set()
        assert release_cancel.wait(timeout=5)
        return True

    def cancel():
        with patch(
            "apps.job_mgmt.services.execution_cancellation_service.is_team_authorized",
            side_effect=pause_after_cancel_lock,
        ):
            return request_execution_cancel(execution.id, authorized_team_ids={1})

    def start():
        return ExecutionTaskBaseService(execution.id, "race-test").prepare_execution()

    with ThreadPoolExecutor(max_workers=2) as pool:
        cancel_future = pool.submit(cancel)
        assert cancel_has_lock.wait(timeout=5)
        start_future = pool.submit(start)
        release_cancel.set()
        cancelled, _ = cancel_future.result(timeout=5)
        started, targets = start_future.result(timeout=5)

    assert cancelled.status == ExecutionStatus.CANCELLED
    assert started is None
    assert targets == []
    execution.refresh_from_db()
    assert execution.status == ExecutionStatus.CANCELLED


@pytest.mark.django_db
class TestFinalizeExecutionConvergesCancelling:
    """Runner 收尾时把 CANCELLING 收敛为 CANCELLED 终态，保留真实结果"""

    def test_cancelling_converges_to_cancelled_with_results(self):
        execution = _make_execution(ExecutionStatus.CANCELLING)
        results = [
            {"target_key": "5", "name": "h1", "ip": "1.1.1.1", "status": ExecutionStatus.SUCCESS},
            {"target_key": "6", "name": "h2", "ip": "2.2.2.2", "status": ExecutionStatus.CANCELLED},
        ]
        with patch("apps.job_mgmt.services.execution_base_service.send_callback") as mock_callback:
            ExecutionTaskBaseService.finalize_execution(execution, "test_task", results)

        execution.refresh_from_db()
        assert execution.status == ExecutionStatus.CANCELLED
        assert execution.finished_at is not None
        assert execution.execution_results == results  # 真实结果保留
        assert execution.success_count == 1
        assert mock_callback.called

    def test_cancelled_terminal_still_converges(self):
        """已是 CANCELLED 终态时收尾行为不变（回归守护）"""
        execution = _make_execution(ExecutionStatus.CANCELLED)
        results = [{"target_key": "5", "name": "h1", "ip": "1.1.1.1", "status": ExecutionStatus.SUCCESS}]
        with patch("apps.job_mgmt.services.execution_base_service.send_callback"):
            ExecutionTaskBaseService.finalize_execution(execution, "test_task", results)

        execution.refresh_from_db()
        assert execution.status == ExecutionStatus.CANCELLED
        assert execution.execution_results == results

    def test_normal_finish_unaffected(self):
        """未取消的任务收尾仍按结果写 SUCCESS/FAILED（回归守护）"""
        execution = _make_execution(ExecutionStatus.RUNNING)
        results = [{"target_key": "5", "name": "h1", "ip": "1.1.1.1", "status": ExecutionStatus.SUCCESS}]
        with patch("apps.job_mgmt.services.execution_base_service.send_callback"):
            ExecutionTaskBaseService.finalize_execution(execution, "test_task", results)

        execution.refresh_from_db()
        assert execution.status == ExecutionStatus.SUCCESS


@pytest.mark.django_db
class TestFinalizeCancellingExecutionTask:
    """兜底收敛任务：CANCELLING 滞留超时后强制收敛为 CANCELLED"""

    def test_stuck_cancelling_is_forced_to_cancelled(self):
        execution = _make_execution(
            ExecutionStatus.CANCELLING,
            target_list=[
                {"target_id": 5, "name": "h1", "ip": "1.1.1.1"},
                {"target_id": 6, "name": "h2", "ip": "2.2.2.2"},
            ],
            execution_results=[
                {"target_key": "5", "name": "h1", "ip": "1.1.1.1", "status": ExecutionStatus.SUCCESS},
            ],
        )
        finalize_cancelling_execution(execution.id)

        execution.refresh_from_db()
        assert execution.status == ExecutionStatus.CANCELLED
        assert execution.finished_at is not None
        # 已有结果保留，缺失目标补"远端结果未知"的 CANCELLED 结果
        assert len(execution.execution_results) == 2
        supplemented = [r for r in execution.execution_results if r["target_key"] == "6"][0]
        assert supplemented["status"] == ExecutionStatus.CANCELLED
        assert "远端结果未知" in supplemented["error_message"]
        assert execution.success_count == 1
        done_records = JobCompletionOutbox.objects.filter(
            execution_id=execution.id,
            kind=JobCompletionOutbox.Kind.DONE_SENTINEL,
        )
        assert {record.payload["target_key"] for record in done_records} == {"5", "6"}

    def test_already_converged_is_noop(self):
        execution = _make_execution(
            ExecutionStatus.CANCELLED,
            execution_results=[{"target_key": "5", "name": "h1", "ip": "1.1.1.1", "status": ExecutionStatus.SUCCESS}],
        )
        finalize_cancelling_execution(execution.id)

        execution.refresh_from_db()
        assert execution.status == ExecutionStatus.CANCELLED
        assert len(execution.execution_results) == 1  # 不补结果
        assert not JobCompletionOutbox.objects.filter(execution_id=execution.id).exists()

    def test_missing_execution_does_not_raise(self):
        finalize_cancelling_execution(999999)  # 不抛异常即可

    def test_periodic_dispatch_recovers_due_cancelling_execution(self):
        due = _make_execution(
            ExecutionStatus.CANCELLING,
            cancel_finalize_at=timezone.now() - timedelta(seconds=1),
        )
        _make_execution(
            ExecutionStatus.CANCELLING,
            cancel_finalize_at=timezone.now() + timedelta(minutes=5),
        )

        with patch("apps.job_mgmt.tasks.finalize_cancelling_execution.delay") as enqueue:
            result = dispatch_pending_job_completion_outbox()

        enqueue.assert_called_once_with(due.id)
        assert result["cancel_scheduled"] == 1


@pytest.mark.django_db
class TestAnsibleCallbackWithCancelling:
    """CANCELLING 非终态：Ansible 真实结果正常落库，最终收敛为 CANCELLED（修复结果丢弃）"""

    def _callback_data(self):
        return {
            "task_id": None,  # 由测试填充
            "result": [
                {"host": "1.1.1.1", "status": "success", "stdout": "ok", "stderr": "", "exit_code": 0},
            ],
        }

    def test_cancelling_lands_results_and_converges_to_cancelled(self):
        execution = _make_execution(ExecutionStatus.CANCELLING)
        data = self._callback_data()
        data["task_id"] = execution.id
        data["callback_context"] = callback_context(execution.id)

        with patch("apps.job_mgmt.services.completion_outbox_service._schedule_deliveries"):
            result = ansible_task_callback(data)

        assert result["success"] is True
        execution.refresh_from_db()
        assert execution.status == ExecutionStatus.CANCELLED  # 不按结果写 SUCCESS
        assert execution.finished_at is not None
        assert len(execution.execution_results) == 1
        assert execution.execution_results[0]["stdout"] == "ok"  # 真实结果保留
        assert execution.success_count == 1
        assert JobCompletionOutbox.objects.filter(
            execution_id=execution.id,
            kind=JobCompletionOutbox.Kind.DONE_SENTINEL,
        ).exists()

    def test_cancelled_terminal_callback_still_rejected(self):
        """已是 CANCELLED 终态时回调仍幂等拒绝（防重复处理，回归守护）"""
        execution = _make_execution(ExecutionStatus.CANCELLED)
        data = self._callback_data()
        data["task_id"] = execution.id
        data["callback_context"] = callback_context(execution.id)

        result = ansible_task_callback(data)

        assert result["success"] is True
        assert "任务已处理" in result["message"]
        execution.refresh_from_db()
        assert execution.execution_results == []  # 未落库


@pytest.mark.django_db
class TestBatchedSubmitStopsOnCancel:
    """分批 submit：取消后不再向线程池提交后续批次（不依赖 future.cancel 竞速）"""

    @staticmethod
    def _targets(n):
        return [{"target_id": i, "name": f"h{i}", "ip": f"1.1.1.{i}"} for i in range(1, n + 1)]

    def test_script_runner_stops_submitting_after_cancel(self, monkeypatch):
        targets = self._targets(4)
        execution = _make_execution(ExecutionStatus.RUNNING, target_list=targets)
        monkeypatch.setattr(ScriptExecutionRunner, "MAX_WORKERS", 2)
        runner = ScriptExecutionRunner(execution.id)

        executed = []
        state = {"cancelled": False}

        def fake_execute(target_info, *args, **kwargs):
            executed.append(target_info["target_id"])
            # 第一批执行期间任务被请求取消（用进程内标志模拟，避免跨线程 DB 事务不可见）
            state["cancelled"] = True
            return {
                "target_key": str(target_info["target_id"]),
                "status": ExecutionStatus.SUCCESS,
            }

        monkeypatch.setattr(runner, "execute_script_on_target", fake_execute)
        monkeypatch.setattr(runner, "is_cancelled", lambda _id: state["cancelled"])
        with patch("apps.job_mgmt.services.script_execution_runner.publish_done_sentinel"):
            results = runner._run_via_sidecar(execution, targets, "echo hi")

        assert sorted(executed) == [1, 2]  # 仅第一批被提交执行
        assert len(results) == 2

    def test_file_runner_stops_submitting_after_cancel(self, monkeypatch):
        targets = self._targets(4)
        execution = _make_execution(
            ExecutionStatus.RUNNING,
            job_type=JobType.FILE_DISTRIBUTION,
            target_list=targets,
            files=[{"name": "a.txt", "file_key": "k1"}],
            target_path="/tmp",
        )
        monkeypatch.setattr(FileDistributionRunner, "MAX_WORKERS", 2)
        runner = FileDistributionRunner(execution.id)

        executed = []
        state = {"cancelled": False}

        def fake_distribute(target_info, *args, **kwargs):
            executed.append(target_info["target_id"])
            state["cancelled"] = True
            return {
                "target_key": str(target_info["target_id"]),
                "status": ExecutionStatus.SUCCESS,
            }

        monkeypatch.setattr(runner, "distribute_file_to_target", fake_distribute)
        monkeypatch.setattr(runner, "is_cancelled", lambda _id: state["cancelled"])
        results = runner.run_distribution_for_targets(execution, targets, execution.files, "/tmp", True, "test_task")

        assert sorted(executed) == [1, 2]
        assert len(results) == 2

    def test_script_runner_target_exception_recorded_as_failed(self, monkeypatch):
        """批内单目标抛异常：补 FAILED 结果并发 FAILED 哨兵，不中断其余目标"""
        targets = self._targets(2)
        execution = _make_execution(ExecutionStatus.RUNNING, target_list=targets)
        runner = ScriptExecutionRunner(execution.id)

        def fake_execute(target_info, *args, **kwargs):
            if target_info["target_id"] == 1:
                raise RuntimeError("node down")
            return {"target_key": str(target_info["target_id"]), "status": ExecutionStatus.SUCCESS}

        monkeypatch.setattr(runner, "execute_script_on_target", fake_execute)
        monkeypatch.setattr(runner, "is_cancelled", lambda _id: False)
        with patch("apps.job_mgmt.services.script_execution_runner.publish_done_sentinel"):
            results = runner._run_via_sidecar(execution, targets, "echo hi")

        assert len(results) == 2
        failed = [r for r in results if r["status"] == ExecutionStatus.FAILED]
        assert len(failed) == 1
        assert "node down" in failed[0]["error_message"]

    def test_file_runner_target_exception_recorded_as_failed(self, monkeypatch):
        targets = self._targets(2)
        execution = _make_execution(
            ExecutionStatus.RUNNING,
            job_type=JobType.FILE_DISTRIBUTION,
            target_list=targets,
            files=[{"name": "a.txt", "file_key": "k1"}],
            target_path="/tmp",
        )
        runner = FileDistributionRunner(execution.id)

        def fake_distribute(target_info, *args, **kwargs):
            if target_info["target_id"] == 1:
                raise RuntimeError("disk full")
            return {"target_key": str(target_info["target_id"]), "status": ExecutionStatus.SUCCESS}

        monkeypatch.setattr(runner, "distribute_file_to_target", fake_distribute)
        monkeypatch.setattr(runner, "is_cancelled", lambda _id: False)
        results = runner.run_distribution_for_targets(execution, targets, execution.files, "/tmp", True, "test_task")

        assert len(results) == 2
        failed = [r for r in results if r["status"] == ExecutionStatus.FAILED]
        assert len(failed) == 1
        assert "disk full" in failed[0]["error_message"]
