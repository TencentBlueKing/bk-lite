"""FileDistributionRunner 单测（纯 helper + run 编排 + 下载分支）"""

from unittest.mock import MagicMock, patch

import pytest

from apps.job_mgmt.constants import ExecutionStatus, JobType, OSType, TargetSource
from apps.job_mgmt.models import JobExecution
from apps.job_mgmt.services.file_distribution_runner import FileDistributionRunner as FDR

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


class TestParseDistributionExecResult:
    @pytest.mark.parametrize("text", ["files copied successfully", "success", ""])
    def test_str_success(self, text):
        ok, err = FDR.parse_distribution_exec_result(text)
        assert ok is True

    def test_str_failure(self):
        ok, err = FDR.parse_distribution_exec_result("permission denied")
        assert ok is False and err

    def test_dict_success_flag(self):
        assert FDR.parse_distribution_exec_result({"success": True})[0] is True

    def test_dict_nonzero_code(self):
        ok, err = FDR.parse_distribution_exec_result({"code": 1, "error": "boom"})
        assert ok is False

    def test_dict_success_false_with_error(self):
        ok, err = FDR.parse_distribution_exec_result({"success": False, "error": "boom"})
        assert ok is False

    def test_dict_result_text_failed(self):
        ok, err = FDR.parse_distribution_exec_result({"result": "task failed"})
        assert ok is False

    def test_dict_default_true(self):
        assert FDR.parse_distribution_exec_result({"result": "ok"})[0] is True

    def test_unknown_type(self):
        ok, err = FDR.parse_distribution_exec_result(123)
        assert ok is False and "未知响应类型" in err


class TestSummarizeAndBuild:
    def test_summarize_success(self):
        result = {"file_results": [{"file_name": "a", "success": True, "error": ""}], "error_message": ""}
        FDR.summarize_distribution_result(result, True, [{"name": "a"}], "/tmp")
        assert result["status"] == ExecutionStatus.SUCCESS and result["exit_code"] == 0

    def test_summarize_failure(self):
        result = {"file_results": [{"file_name": "a", "success": False, "error": "denied"}], "error_message": ""}
        FDR.summarize_distribution_result(result, False, [{"name": "a"}], "/tmp")
        assert result["status"] == ExecutionStatus.FAILED and result["exit_code"] == 1

    def test_build_target_result(self):
        r = FDR._build_distribution_target_result({"node_id": "n1", "name": "h", "ip": "1.1.1.1"})
        assert r["target_key"] == "n1" and r["status"] == ExecutionStatus.PENDING

    def test_normalize_target_path_linux(self):
        assert FDR._normalize_target_path("/a/b", OSType.LINUX) == "/a/b"

    def test_normalize_target_path_windows(self):
        assert FDR._normalize_target_path("C:\\a\\b", OSType.WINDOWS) == "C:/a/b"


class TestGetCloudRegionName:
    def test_found(self):
        region = MagicMock()
        region.name = "region-1"
        with patch("apps.job_mgmt.services.file_distribution_runner.CloudRegion") as MCR:
            MCR.objects.filter.return_value.first.return_value = region
            assert FDR.get_cloud_region_name(1) == "region-1"

    def test_missing_raises(self):
        with patch("apps.job_mgmt.services.file_distribution_runner.CloudRegion") as MCR:
            MCR.objects.filter.return_value.first.return_value = None
            with pytest.raises(ValueError):
                FDR.get_cloud_region_name(1)


class TestDownloadToRemote:
    def test_missing_auth_raises(self):
        with pytest.raises(ValueError):
            FDR.download_to_remote("node", {"file_key": "k", "name": "f"}, "/tmp", {"password": None, "private_key": None}, 60, True)

    def test_with_password_calls_executor(self):
        creds = {"host": "h", "username": "u", "password": "p", "private_key": None, "port": 22}
        with patch("apps.job_mgmt.services.file_distribution_runner.Executor") as MExec:
            MExec.return_value.download_to_remote.return_value = "success"
            out = FDR.download_to_remote("node", {"file_key": "k", "name": "f"}, "/tmp", creds, 60, True)
        assert out == "success"


def _fd_execution(**over):
    defaults = {
        "name": "fd",
        "job_type": JobType.FILE_DISTRIBUTION,
        "status": ExecutionStatus.PENDING,
        "target_source": TargetSource.NODE_MGMT,
        "target_list": [{"node_id": "n1", "name": "h", "ip": "1.1.1.1"}],
        "files": [{"name": "f", "file_key": "k"}],
        "target_path": "/tmp/app",
        "team": [1],
    }
    defaults.update(over)
    return JobExecution.objects.create(**defaults)


class TestRun:
    def test_run_success(self):
        ex = _fd_execution()
        ok = {"target_key": "n1", "name": "h", "ip": "1.1.1.1", "status": ExecutionStatus.SUCCESS, "error_message": ""}
        with patch.object(FDR, "distribute_file_to_target", return_value=ok), patch("apps.job_mgmt.services.execution_base_service.send_callback"):
            FDR(ex.id).run()
        ex.refresh_from_db()
        assert ex.status == ExecutionStatus.SUCCESS

    def test_run_no_files_marks_success(self):
        ex = _fd_execution(files=[])
        with patch("apps.job_mgmt.services.execution_base_service.send_callback"):
            FDR(ex.id).run()
        ex.refresh_from_db()
        assert ex.status == ExecutionStatus.SUCCESS

    def test_run_blocked_path_marks_failed(self):
        from apps.job_mgmt.constants import DangerousLevel
        from apps.job_mgmt.models import DangerousPath

        DangerousPath.objects.create(name="etc", pattern="/etc", match_type="exact", level=DangerousLevel.FORBIDDEN, is_enabled=True, team=[])
        ex = _fd_execution(target_path="/etc/nginx")
        FDR(ex.id).run()
        ex.refresh_from_db()
        assert ex.status == ExecutionStatus.FAILED

    def test_distribute_file_to_target_local_success(self):
        ex = _fd_execution()
        with patch.object(FDR, "download_to_local_target", return_value="success"):
            result = FDR(ex.id).distribute_file_to_target(
                {"node_id": "n1", "name": "h", "ip": "1.1.1.1"}, TargetSource.NODE_MGMT, [{"name": "f", "file_key": "k"}], "/tmp", 60, True, 0
            )
        assert result["status"] == ExecutionStatus.SUCCESS
