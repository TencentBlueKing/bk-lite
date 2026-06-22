"""作业取消语义诚实化测试 (Issue #2964 方案 C)

覆盖：
1. CANCELLING 状态机定义（非终态）
2. is_cancelled / prepare_execution 对 CANCELLING 生效
3. 取消接口 CAS 分流：PENDING→CANCELLED、RUNNING→CANCELLING、终态/取消中 400
"""

from unittest.mock import MagicMock, patch

import pytest

from apps.job_mgmt.constants import ExecutionStatus, JobType, TargetSource
from apps.job_mgmt.models import JobExecution
from apps.job_mgmt.nats_api import ansible_task_callback, job_task_terminate
from apps.job_mgmt.services.execution_base_service import ExecutionTaskBaseService
from apps.job_mgmt.services.file_distribution_runner import FileDistributionRunner
from apps.job_mgmt.services.script_execution_runner import ScriptExecutionRunner
from apps.job_mgmt.tasks import finalize_cancelling_execution

pytestmark = pytest.mark.unit


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
    return JobExecution.objects.create(**defaults)


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

    def test_running_execution_enters_cancelling(self, api_client):
        execution = _make_execution(ExecutionStatus.RUNNING)
        with patch("apps.job_mgmt.views.execution.finalize_cancelling_execution") as mock_task:
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

    def test_running_cancel_revokes_celery_task(self, api_client):
        execution = _make_execution(ExecutionStatus.RUNNING, celery_task_id="ct-1")
        with (
            patch("apps.job_mgmt.views.execution.finalize_cancelling_execution"),
            patch("apps.job_mgmt.views.execution.current_app.control.revoke") as mock_revoke,
        ):
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

    def test_revoke_failure_does_not_block_cancel(self, api_client):
        """revoke 是尽力而为：失败不阻断取消流程"""
        execution = _make_execution(ExecutionStatus.PENDING, celery_task_id="ct-2")
        with patch("apps.job_mgmt.views.execution.current_app.control.revoke", side_effect=Exception("broker down")):
            resp = self._cancel(api_client, execution)
        assert resp.status_code == 200
        execution.refresh_from_db()
        assert execution.status == ExecutionStatus.CANCELLED

    def test_concurrent_state_change_returns_400(self, api_client):
        """检查后状态被并发改变（两次 CAS 都未命中）时按最新状态拒绝"""
        execution = _make_execution(ExecutionStatus.RUNNING)
        miss_qs = MagicMock()
        miss_qs.update.return_value = 0
        with patch("apps.job_mgmt.views.execution.JobExecution.objects.filter", return_value=miss_qs):
            resp = self._cancel(api_client, execution)
        assert resp.status_code == 400
        assert "状态已变更" in resp.data["error"]


@pytest.mark.django_db
class TestTerminateTaskNatsAPI:
    def test_pending_execution_is_cancelled_directly(self):
        execution = _make_execution(ExecutionStatus.PENDING)

        result = job_task_terminate({"task_id": execution.id})

        assert result["result"] is True
        assert result["data"]["status"] == ExecutionStatus.CANCELLED
        execution.refresh_from_db()
        assert execution.status == ExecutionStatus.CANCELLED
        assert execution.finished_at is not None

    def test_running_execution_enters_cancelling(self):
        execution = _make_execution(ExecutionStatus.RUNNING)

        with patch("apps.job_mgmt.nats_api.finalize_cancelling_execution") as mock_task:
            result = job_task_terminate({"task_id": execution.id})

        assert result["result"] is True
        assert result["data"]["status"] == ExecutionStatus.CANCELLING
        execution.refresh_from_db()
        assert execution.status == ExecutionStatus.CANCELLING
        assert execution.finished_at is None
        mock_task.apply_async.assert_called_once()
        _, kwargs = mock_task.apply_async.call_args
        assert kwargs["args"] == [execution.id]
        assert kwargs["countdown"] > execution.timeout


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
        with patch("apps.job_mgmt.tasks.publish_done_sentinel") as mock_sentinel:
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
        # 只为补结果的目标发 done 哨兵（已有结果的目标此前已发过）
        mock_sentinel.assert_called_once_with(execution.id, "6", ExecutionStatus.CANCELLED)

    def test_already_converged_is_noop(self):
        execution = _make_execution(
            ExecutionStatus.CANCELLED,
            execution_results=[{"target_key": "5", "name": "h1", "ip": "1.1.1.1", "status": ExecutionStatus.SUCCESS}],
        )
        with patch("apps.job_mgmt.tasks.publish_done_sentinel") as mock_sentinel:
            finalize_cancelling_execution(execution.id)

        execution.refresh_from_db()
        assert execution.status == ExecutionStatus.CANCELLED
        assert len(execution.execution_results) == 1  # 不补结果
        mock_sentinel.assert_not_called()

    def test_missing_execution_does_not_raise(self):
        finalize_cancelling_execution(999999)  # 不抛异常即可

    def test_execution_deleted_after_cas_returns_silently(self):
        """CAS 命中后记录被删除（防御分支）：静默返回不抛异常"""
        cas_qs = MagicMock()
        cas_qs.update.return_value = 1
        gone_qs = MagicMock()
        gone_qs.first.return_value = None
        with patch("apps.job_mgmt.tasks.JobExecution.objects.filter", side_effect=[cas_qs, gone_qs]):
            finalize_cancelling_execution(1)


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

        with patch("apps.job_mgmt.nats_api.send_callback") as mock_callback, patch("apps.job_mgmt.nats_api.publish_done_sentinel"):
            result = ansible_task_callback(data)

        assert result["success"] is True
        execution.refresh_from_db()
        assert execution.status == ExecutionStatus.CANCELLED  # 不按结果写 SUCCESS
        assert execution.finished_at is not None
        assert len(execution.execution_results) == 1
        assert execution.execution_results[0]["stdout"] == "ok"  # 真实结果保留
        assert execution.success_count == 1
        assert mock_callback.called

    def test_cancelled_terminal_callback_still_rejected(self):
        """已是 CANCELLED 终态时回调仍幂等拒绝（防重复处理，回归守护）"""
        execution = _make_execution(ExecutionStatus.CANCELLED)
        data = self._callback_data()
        data["task_id"] = execution.id

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
