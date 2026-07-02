"""PlaybookExecution 补充单测：NATS OS 文件中转 / 清理失败 / shlex 回退。

只 mock 外部边界（AnsibleExecutor RPC、NATS OS upload/delete、归档校验、MinIO 文件句柄），
断言真实分支与调用契约。
"""

import pydantic.root_model  # noqa
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.job_mgmt.constants import (
    CredentialSource,
    ExecutionStatus,
    ExecutorDriver,
    JobType,
    OSType,
    SSHCredentialType,
    TargetSource,
)
from apps.job_mgmt.models import JobExecution, Target
from apps.job_mgmt.services.playbook_execution import PlaybookExecution

pytestmark = [pytest.mark.unit, pytest.mark.django_db]

MOD = "apps.job_mgmt.services.playbook_execution"


def _target(**over):
    defaults = {
        "name": "t",
        "ip": "10.0.0.1",
        "os_type": OSType.LINUX,
        "driver": ExecutorDriver.ANSIBLE,
        "credential_source": CredentialSource.MANUAL,
        "ssh_user": "root",
        "ssh_credential_type": SSHCredentialType.PASSWORD,
        "ssh_password": "pw",
        "cloud_region_id": 1,
        "team": [1],
    }
    defaults.update(over)
    return Target.objects.create(**defaults)


def _execution(**over):
    defaults = {
        "name": "pb-exec",
        "job_type": JobType.PLAYBOOK,
        "status": ExecutionStatus.RUNNING,
        "target_source": TargetSource.MANUAL,
        "target_list": [{"target_id": 1}],
        "params": "{}",
        "timeout": 60,
        "team": [1],
    }
    defaults.update(over)
    return JobExecution.objects.create(**defaults)


class TestBuildExtraVarsShlexFallback:
    def test_unbalanced_quotes_fallback_to_split(self):
        """params 含未闭合引号：shlex.split 抛 ValueError → 回退 str.split（覆盖 228-229）。"""
        params_def = [{"name": "a"}, {"name": "b"}]
        # 单个未闭合引号让 shlex.split 抛 ValueError
        out = PlaybookExecution._build_extra_vars("v1 'v2", params_def)
        assert out == {"a": "v1", "b": "'v2"}


class TestExecutePlaybookViaAnsibleFileTransfer:
    """覆盖 146-160：Playbook ZIP 从 MinIO 中转 NATS OS。

    用真实形态的假 playbook 代理（含 file 句柄）替换 ``execution.playbook``，
    避免触碰 Django FileField/MinIO 描述符，只 mock 归档校验与 NATS OS upload。
    """

    def _make(self, target):
        """真实落库 Target；execution/playbook 用 SimpleNamespace 代理，
        避免触碰 Django FileField/MinIO 描述符与 FK 约束。
        _execute_playbook_via_ansible 只读取这些属性 + 调 is_cancelled(id)。"""
        fake_file = MagicMock()
        fake_file.open.return_value = None
        fake_file.close.return_value = None
        pb_proxy = SimpleNamespace(
            file=fake_file,
            name="p",
            version="v1.0.0",
            params=[],
            file_name="p.zip",
            file_key="playbooks/p.zip",
            bucket_name="job-mgmt-private",
        )
        ex_proxy = SimpleNamespace(
            id=12345,
            timeout=60,
            params="{}",
            playbook=pb_proxy,
        )
        return ex_proxy, fake_file

    def test_file_transfer_success_appends_nats_key(self):
        t = _target()
        ex, fake_file = self._make(t)

        executor = MagicMock()
        executor.playbook.return_value = {"task_id": "x"}
        with patch.object(PlaybookExecution, "_get_ansible_node", return_value="node-1"), patch.object(
            PlaybookExecution, "is_cancelled", return_value=False
        ), patch(f"{MOD}.enforce_archive_limits", return_value=SimpleNamespace(raw_size=1234)), patch(
            f"{MOD}.upload_file_to_s3"
        ) as mupload, patch(
            f"{MOD}.AnsibleExecutor", return_value=executor
        ):
            out = PlaybookExecution._execute_playbook_via_ansible(ex, [{"target_id": t.id}])

        assert out == f"job-playbooks/{ex.id}/p.zip"
        called_files = executor.playbook.call_args.kwargs["files"]
        assert called_files[0]["name"] == "p.zip"
        assert called_files[0]["file_key"] == f"job-playbooks/{ex.id}/p.zip"
        mupload.assert_called_once()
        fake_file.close.assert_called_once()

    def test_file_transfer_failure_raises_and_closes(self):
        """upload 抛异常 → 包装成 ValueError，且 finally 仍 close（覆盖 155-158）。"""
        t = _target()
        ex, fake_file = self._make(t)

        with patch.object(PlaybookExecution, "_get_ansible_node", return_value="node-1"), patch.object(
            PlaybookExecution, "is_cancelled", return_value=False
        ), patch(f"{MOD}.enforce_archive_limits", return_value=SimpleNamespace(raw_size=1)), patch(
            f"{MOD}.upload_file_to_s3", side_effect=RuntimeError("os down")
        ):
            with pytest.raises(ValueError, match="Playbook 文件中转失败"):
                PlaybookExecution._execute_playbook_via_ansible(ex, [{"target_id": t.id}])
        fake_file.close.assert_called_once()


class TestRunViaAnsibleCleanup:
    """_run_via_ansible 提交失败的落库与清理行为。

    BUG（锁定当前行为）：playbook_execution.py 中 ``nats_file_key`` 仅在
    ``nats_file_key = self._execute_playbook_via_ansible(...)`` 成功返回时被赋值。
    当 ``_execute_playbook_via_ansible`` 在已把 ZIP 中转到 NATS OS *之后* 抛出异常
    （如 executor.playbook 失败），外层 ``nats_file_key`` 仍为 None，
    导致 75-79 的清理分支永不执行 → NATS OS 残留孤儿文件。
    此处断言当前行为：异常时落 FAILED，且 delete_s3_file 不被调用。
    """

    def test_exception_marks_failed_and_skips_cleanup(self):
        ex = _execution()
        runner = PlaybookExecution(ex.id)
        with patch.object(PlaybookExecution, "_execute_playbook_via_ansible", side_effect=RuntimeError("boom")), patch(
            f"{MOD}.delete_s3_file"
        ) as mdel, patch("apps.job_mgmt.services.execution_base_service.send_callback"):
            runner._run_via_ansible(ex, [{"target_id": 1}])
        ex.refresh_from_db()
        assert ex.status == ExecutionStatus.FAILED
        # nats_file_key 为 None（见类 docstring 的 BUG），不触发清理
        mdel.assert_not_called()
        assert ex.execution_results and ex.execution_results[0]["status"] == ExecutionStatus.FAILED
