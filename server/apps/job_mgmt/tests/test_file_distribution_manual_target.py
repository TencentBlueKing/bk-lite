"""FileDistributionRunner 手动目标分发 / Windows Ansible 分支单测。

只 mock 真实外部边界（Executor / AnsibleExecutor RPC、NodeMgmt、time.sleep、
凭据解密），返回真实形态假数据，断言真实输出 / 分支 / 异常 / 调用入参契约。
"""

import pydantic.root_model  # noqa
from unittest.mock import MagicMock, patch

import pytest

from apps.job_mgmt.constants import (
    ExecutionStatus,
    ExecutorDriver,
    JobType,
    OSType,
    SSHCredentialType,
    TargetSource,
)
from apps.job_mgmt.models import JobExecution, Target
from apps.job_mgmt.services.file_distribution_runner import FileDistributionRunner as FDR

pytestmark = [pytest.mark.unit, pytest.mark.django_db]

MOD = "apps.job_mgmt.services.file_distribution_runner"


def _execution(**over):
    defaults = {
        "name": "fd",
        "job_type": JobType.FILE_DISTRIBUTION,
        "status": ExecutionStatus.RUNNING,
        "target_source": TargetSource.MANUAL,
        "target_list": [],
        "files": [{"name": "f", "file_key": "k"}],
        "target_path": "/tmp/app",
        "team": [1],
    }
    defaults.update(over)
    return JobExecution.objects.create(**defaults)


def _linux_target(**over):
    defaults = {
        "name": "host-1",
        "ip": "10.0.0.1",
        "os_type": OSType.LINUX,
        "driver": ExecutorDriver.SIDECAR,
        "cloud_region_id": 7,
        "node_id": "region-7",
        "ssh_port": 22,
        "ssh_user": "root",
        "ssh_credential_type": SSHCredentialType.PASSWORD,
        "ssh_password": "secret",
        "team": [1],
    }
    defaults.update(over)
    return Target.objects.create(**defaults)


def _windows_target(**over):
    defaults = {
        "name": "win-1",
        "ip": "10.0.0.2",
        "os_type": OSType.WINDOWS,
        "driver": ExecutorDriver.ANSIBLE,
        "cloud_region_id": 9,
        "winrm_port": 5986,
        "winrm_user": "Administrator",
        "winrm_password": "winpass",
        "team": [1],
    }
    defaults.update(over)
    return Target.objects.create(**defaults)


class TestDistributeFileToTargetCancellation:
    """distribute_file_to_target 取消检查点（覆盖 109-122）。"""

    def test_cancelled_before_start(self):
        ex = _execution(status=ExecutionStatus.CANCELLING)
        runner = FDR(ex.id)
        result = runner.distribute_file_to_target(
            {"node_id": "n1", "name": "h", "ip": "1.1.1.1"},
            TargetSource.NODE_MGMT,
            [{"name": "f", "file_key": "k"}],
            "/tmp",
            60,
            True,
            ex.id,
        )
        assert result["status"] == ExecutionStatus.CANCELLED
        assert result["error_message"] == "任务已取消，跳过分发"
        assert result["file_results"] == []

    def test_cancelled_between_files(self):
        """首次取消检查通过、进入循环后才取消：覆盖 118-122 的循环内取消分支。"""
        ex = _execution()
        runner = FDR(ex.id)
        # is_cancelled 第一次(进入前)False，第二次(循环内)True
        with patch.object(FDR, "is_cancelled", side_effect=[False, True]):
            result = runner.distribute_file_to_target(
                {"node_id": "n1", "name": "h", "ip": "1.1.1.1"},
                TargetSource.NODE_MGMT,
                [{"name": "f", "file_key": "k"}],
                "/tmp",
                60,
                True,
                ex.id,
            )
        assert result["status"] == ExecutionStatus.CANCELLED
        assert result["error_message"] == "任务已取消，跳过剩余文件分发"


class TestDistributeFileToTargetExecutionPaths:
    """覆盖 124-156：本地 / 手动目标分发结果汇总。"""

    def test_local_target_file_failure_marks_failed(self):
        ex = _execution(target_source=TargetSource.NODE_MGMT)
        runner = FDR(ex.id)
        with patch.object(FDR, "download_to_local_target", return_value={"code": 1, "error": "boom"}):
            result = runner.distribute_file_to_target(
                {"node_id": "n1", "name": "h", "ip": "1.1.1.1"},
                TargetSource.NODE_MGMT,
                [{"name": "f", "file_key": "k"}],
                "/tmp",
                60,
                True,
                0,
            )
        assert result["status"] == ExecutionStatus.FAILED
        assert result["file_results"][0]["success"] is False

    def test_local_target_executor_raises_records_error(self):
        """download 抛异常：覆盖 143-146 单文件 except 分支。"""
        ex = _execution(target_source=TargetSource.NODE_MGMT)
        runner = FDR(ex.id)
        with patch.object(FDR, "download_to_local_target", side_effect=RuntimeError("rpc down")):
            result = runner.distribute_file_to_target(
                {"node_id": "n1", "name": "h", "ip": "1.1.1.1"},
                TargetSource.NODE_MGMT,
                [{"name": "f", "file_key": "k"}],
                "/tmp",
                60,
                True,
                0,
            )
        assert result["status"] == ExecutionStatus.FAILED
        assert "rpc down" in result["file_results"][0]["error"]

    def test_manual_target_missing_target_id_raises_caught(self):
        """手动目标缺 target_id：download_to_manual_target 抛 ValueError，进单文件 except。"""
        ex = _execution(target_source=TargetSource.MANUAL)
        runner = FDR(ex.id)
        result = runner.distribute_file_to_target(
            {"name": "h", "ip": "1.1.1.1"},  # 无 target_id
            TargetSource.MANUAL,
            [{"name": "f", "file_key": "k"}],
            "/tmp",
            60,
            True,
            0,
        )
        assert result["status"] == ExecutionStatus.FAILED
        assert "target_id" in result["file_results"][0]["error"]

    def test_manual_target_success_routes_to_manual(self):
        ex = _execution(target_source=TargetSource.MANUAL)
        runner = FDR(ex.id)
        with patch.object(FDR, "download_to_manual_target", return_value={"success": True}) as m:
            result = runner.distribute_file_to_target(
                {"target_id": 123, "name": "h", "ip": "1.1.1.1"},
                TargetSource.MANUAL,
                [{"name": "f", "file_key": "k"}],
                "/data",
                30,
                False,
                0,
            )
        assert result["status"] == ExecutionStatus.SUCCESS
        # 契约：手动路径以 (file_item, target_id, target_path, timeout, overwrite) 调用
        m.assert_called_once_with({"name": "f", "file_key": "k"}, 123, "/data", 30, False)


class TestDownloadToManualTarget:
    """覆盖 192-221：手动目标下载分支路由。"""

    def test_linux_password_routes_remote(self):
        t = _linux_target()
        runner = FDR(_execution().id)
        with patch.object(FDR, "decrypt_password", return_value="plain"), patch.object(
            FDR, "download_to_remote", return_value={"success": True}
        ) as mremote:
            out = runner.download_to_manual_target({"name": "f", "file_key": "k"}, t.id, "/tmp", 60, True)
        assert out == {"success": True}
        args, kwargs = mremote.call_args
        # instance_id 用 ssh_creds["node_id"]（非 Ansible 驱动）
        assert args[0] == t.node_id

    def test_linux_no_credentials_raises(self):
        """get_ssh_credentials 返回空（目标不存在视图）→ ValueError。"""
        runner = FDR(_execution().id)
        with patch.object(FDR, "get_ssh_credentials", return_value={}):
            with pytest.raises(ValueError, match="无法获取目标凭据"):
                runner.download_to_manual_target({"name": "f", "file_key": "k"}, 4242, "/tmp", 60, True)

    def test_ansible_driver_missing_cloud_region_raises(self):
        t = _linux_target(driver=ExecutorDriver.ANSIBLE, cloud_region_id=None)
        runner = FDR(_execution().id)
        with patch.object(FDR, "decrypt_password", return_value="plain"):
            with pytest.raises(ValueError, match="云区域"):
                runner.download_to_manual_target({"name": "f", "file_key": "k"}, t.id, "/tmp", 60, True)

    def test_ansible_driver_uses_ansible_node(self):
        t = _linux_target(driver=ExecutorDriver.ANSIBLE, cloud_region_id=11)
        runner = FDR(_execution().id)
        with patch.object(FDR, "decrypt_password", return_value="plain"), patch.object(
            FDR, "_get_ansible_node", return_value="ansible-node-x"
        ), patch.object(FDR, "download_to_remote", return_value={"success": True}) as mremote:
            runner.download_to_manual_target({"name": "f", "file_key": "k"}, t.id, "/tmp", 60, True)
        assert mremote.call_args[0][0] == "ansible-node-x"

    def test_windows_non_ansible_builds_winrm_creds(self):
        """Windows + 非 Ansible：用 winrm 凭据并归一化路径（覆盖 198-212）。"""
        t = _windows_target(driver=ExecutorDriver.SIDECAR)
        runner = FDR(_execution().id)
        with patch.object(FDR, "decrypt_password", return_value="decwin"), patch.object(
            FDR, "download_to_remote", return_value={"success": True}
        ) as mremote:
            runner.download_to_manual_target({"name": "f", "file_key": "k"}, t.id, "C:\\app\\dir", 60, True)
        # 路径被归一化为正斜杠
        assert mremote.call_args[0][2] == "C:/app/dir"
        # 用 winrm 凭据
        creds = mremote.call_args[0][3]
        assert creds["username"] == "Administrator"
        assert creds["password"] == "decwin"

    def test_windows_ansible_routes_to_windows_ansible(self):
        t = _windows_target(driver=ExecutorDriver.ANSIBLE)
        runner = FDR(_execution().id)
        with patch.object(FDR, "_download_to_windows_via_ansible", return_value={"success": True}) as m:
            out = runner.download_to_manual_target({"name": "f", "file_key": "k"}, t.id, "C:\\d", 60, True)
        assert out == {"success": True}
        # 路径已归一化为正斜杠传入
        assert m.call_args[0][2] == "C:/d"


class TestDownloadToWindowsViaAnsible:
    """覆盖 223-297：Windows Ansible 文件分发轮询。"""

    def _runner(self):
        return FDR(_execution().id)

    def test_missing_cloud_region_raises(self):
        t = _windows_target(cloud_region_id=None)
        with pytest.raises(ValueError, match="云区域"):
            self._runner()._download_to_windows_via_ansible(t, [{"name": "f"}], "C:/d", 60, True)

    def test_success_with_list_host_results(self):
        t = _windows_target(cloud_region_id=9)
        executor = MagicMock()
        executor.playbook.return_value = {"task_id": "tid-1"}
        executor.task_query.return_value = {
            "status": "success",
            "result": {
                "success": True,
                "result": [{"status": "success", "host": "10.0.0.2"}],
            },
        }
        runner = self._runner()
        with patch.object(FDR, "_get_ansible_node", return_value="node-a"), patch.object(
            FDR, "_build_host_credentials", return_value=[{"host": "10.0.0.2"}]
        ), patch(f"{MOD}.AnsibleExecutor", return_value=executor):
            out = runner._download_to_windows_via_ansible(t, [{"name": "f"}], "C:/d", 60, True)
        assert out["success"] is True
        assert out["error"] == ""
        # 使用 accepted task_id 查询
        executor.task_query.assert_called_with("tid-1", timeout=60)

    def test_failed_host_aggregates_error(self):
        t = _windows_target(cloud_region_id=9)
        executor = MagicMock()
        executor.playbook.return_value = {}  # 无 task_id → 回退到生成的 task_id
        executor.task_query.return_value = {
            "status": "failed",
            "result": {
                "success": False,
                "result": [{"status": "failed", "error_message": "disk full"}],
            },
        }
        runner = self._runner()
        with patch.object(FDR, "_get_ansible_node", return_value="node-a"), patch.object(
            FDR, "_build_host_credentials", return_value=[]
        ), patch(f"{MOD}.AnsibleExecutor", return_value=executor):
            out = runner._download_to_windows_via_ansible(t, [{"name": "f"}], "C:/d", 60, True)
        assert out["success"] is False
        assert "disk full" in out["error"]

    def test_non_list_result_returns_scalar(self):
        t = _windows_target(cloud_region_id=9)
        executor = MagicMock()
        executor.playbook.return_value = {"task_id": "tid"}
        executor.task_query.return_value = {
            "status": "success",
            "result": {"success": True, "result": "done", "error": ""},
        }
        runner = self._runner()
        with patch.object(FDR, "_get_ansible_node", return_value="node-a"), patch.object(
            FDR, "_build_host_credentials", return_value=[]
        ), patch(f"{MOD}.AnsibleExecutor", return_value=executor):
            out = runner._download_to_windows_via_ansible(t, [{"name": "f"}], "C:/d", 60, True)
        assert out == {"success": True, "result": "done", "error": ""}

    def test_invalid_query_result_raises(self):
        t = _windows_target(cloud_region_id=9)
        executor = MagicMock()
        executor.playbook.return_value = {"task_id": "tid"}
        executor.task_query.return_value = "not-a-dict"
        runner = self._runner()
        with patch.object(FDR, "_get_ansible_node", return_value="node-a"), patch.object(
            FDR, "_build_host_credentials", return_value=[]
        ), patch(f"{MOD}.AnsibleExecutor", return_value=executor):
            with pytest.raises(ValueError, match="格式非法"):
                runner._download_to_windows_via_ansible(t, [{"name": "f"}], "C:/d", 60, True)

    def test_polls_until_terminal_status(self):
        """先 running 再 success：覆盖 sleep 轮询 + 取消检查（265-268）。"""
        t = _windows_target(cloud_region_id=9)
        executor = MagicMock()
        executor.playbook.return_value = {"task_id": "tid"}
        executor.task_query.side_effect = [
            {"status": "running"},
            {"status": "success", "result": {"success": True, "result": "ok"}},
        ]
        runner = self._runner()
        with patch.object(FDR, "_get_ansible_node", return_value="node-a"), patch.object(
            FDR, "_build_host_credentials", return_value=[]
        ), patch.object(FDR, "is_cancelled", return_value=False), patch(
            f"{MOD}.AnsibleExecutor", return_value=executor
        ), patch(
            f"{MOD}.time.sleep"
        ) as msleep:
            out = runner._download_to_windows_via_ansible(t, [{"name": "f"}], "C:/d", 60, True)
        assert out["success"] is True
        assert executor.task_query.call_count == 2
        msleep.assert_called_once()

    def test_cancelled_during_poll_raises(self):
        """轮询间隙检测到取消：覆盖 265-266。"""
        t = _windows_target(cloud_region_id=9)
        executor = MagicMock()
        executor.playbook.return_value = {"task_id": "tid"}
        executor.task_query.return_value = {"status": "running"}
        runner = self._runner()
        with patch.object(FDR, "_get_ansible_node", return_value="node-a"), patch.object(
            FDR, "_build_host_credentials", return_value=[]
        ), patch.object(FDR, "is_cancelled", return_value=True), patch(
            f"{MOD}.AnsibleExecutor", return_value=executor
        ), patch(
            f"{MOD}.time.sleep"
        ):
            with pytest.raises(ValueError, match="任务已取消"):
                runner._download_to_windows_via_ansible(t, [{"name": "f"}], "C:/d", 60, True)
