"""PlaybookExecution 单测（_build_extra_vars 纯函数 + run / ansible 分支）"""

from unittest.mock import patch

import pytest

from apps.job_mgmt.constants import CredentialSource, ExecutionStatus, ExecutorDriver, JobType, OSType, SSHCredentialType, TargetSource
from apps.job_mgmt.models import JobExecution, Playbook, Target
from apps.job_mgmt.services.playbook_execution import PlaybookExecution

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


class TestBuildExtraVars:
    def test_empty_returns_empty(self):
        assert PlaybookExecution._build_extra_vars("", []) == {}

    def test_json_dict(self):
        assert PlaybookExecution._build_extra_vars('{"a": 1, "b": "x"}', []) == {"a": 1, "b": "x"}

    def test_old_format_maps_by_order(self):
        params_def = [{"name": "p1"}, {"name": "p2"}]
        assert PlaybookExecution._build_extra_vars("v1 v2", params_def) == {"p1": "v1", "p2": "v2"}

    def test_old_format_no_param_defs_returns_empty(self):
        assert PlaybookExecution._build_extra_vars("v1 v2", []) == {}

    def test_old_format_default_fallback(self):
        params_def = [{"name": "p1"}, {"name": "p2", "default": "d2"}]
        assert PlaybookExecution._build_extra_vars("v1", params_def) == {"p1": "v1", "p2": "d2"}


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
        "status": ExecutionStatus.PENDING,
        "target_source": TargetSource.MANUAL,
        "target_list": [{"target_id": 1}],
        "params": "{}",
        "team": [1],
    }
    defaults.update(over)
    return JobExecution.objects.create(**defaults)


class TestRun:
    def test_no_playbook_marks_failed(self):
        ex = _execution(playbook=None)
        PlaybookExecution(ex.id).run()
        ex.refresh_from_db()
        assert ex.status == ExecutionStatus.FAILED

    def test_unsupported_source_marks_failed(self):
        pb = Playbook.objects.create(name="p", version="v1.0.0", team=[1])
        ex = _execution(playbook=pb, target_source=TargetSource.NODE_MGMT, target_list=[{"node_id": "n1"}])
        PlaybookExecution(ex.id).run()
        ex.refresh_from_db()
        assert ex.status == ExecutionStatus.FAILED

    def test_ansible_path_invoked(self):
        t = _target()
        pb = Playbook.objects.create(name="p", version="v1.0.0", team=[1])
        ex = _execution(playbook=pb, target_list=[{"target_id": t.id}])
        with patch.object(PlaybookExecution, "_run_via_ansible") as mrun:
            PlaybookExecution(ex.id).run()
        mrun.assert_called_once()


class TestRunViaAnsible:
    def test_cancelled_skips(self):
        pb = Playbook.objects.create(name="p", version="v1.0.0", team=[1])
        ex = _execution(playbook=pb, status=ExecutionStatus.CANCELLED)
        with patch.object(PlaybookExecution, "_execute_playbook_via_ansible") as mexec:
            PlaybookExecution(ex.id)._run_via_ansible(ex, [{"target_id": 1}])
        mexec.assert_not_called()

    def test_success(self):
        pb = Playbook.objects.create(name="p", version="v1.0.0", team=[1])
        ex = _execution(playbook=pb, status=ExecutionStatus.RUNNING)
        with patch.object(PlaybookExecution, "_execute_playbook_via_ansible", return_value=None):
            PlaybookExecution(ex.id)._run_via_ansible(ex, [{"target_id": 1}])
        # 未抛即视为提交成功

    def test_exception_marks_failed(self):
        pb = Playbook.objects.create(name="p", version="v1.0.0", team=[1])
        ex = _execution(playbook=pb, status=ExecutionStatus.RUNNING)
        with patch.object(PlaybookExecution, "_execute_playbook_via_ansible", side_effect=RuntimeError("boom")):
            PlaybookExecution(ex.id)._run_via_ansible(ex, [{"target_id": 1}])
        ex.refresh_from_db()
        assert ex.status == ExecutionStatus.FAILED


class TestExecutePlaybookViaAnsible:
    def test_no_target_ids_raises(self):
        pb = Playbook.objects.create(name="p", version="v1.0.0", team=[1])
        ex = _execution(playbook=pb)
        with pytest.raises(ValueError):
            PlaybookExecution._execute_playbook_via_ansible(ex, [{}])

    def test_no_targets_found_raises(self):
        pb = Playbook.objects.create(name="p", version="v1.0.0", team=[1])
        ex = _execution(playbook=pb)
        with pytest.raises(ValueError):
            PlaybookExecution._execute_playbook_via_ansible(ex, [{"target_id": 999999}])

    def test_happy_path_no_file_submits(self):
        t = _target()
        pb = Playbook.objects.create(name="p", version="v1.0.0", params=[], team=[1])
        ex = _execution(playbook=pb, target_list=[{"target_id": t.id}], status=ExecutionStatus.RUNNING)
        with patch.object(PlaybookExecution, "_get_ansible_node", return_value="node-1"), patch(
            "apps.job_mgmt.services.playbook_execution.AnsibleExecutor"
        ) as MExec:
            MExec.return_value.playbook.return_value = {"task_id": "x"}
            out = PlaybookExecution._execute_playbook_via_ansible(ex, [{"target_id": t.id}])
        assert out is None  # 无文件
        MExec.return_value.playbook.assert_called_once()
