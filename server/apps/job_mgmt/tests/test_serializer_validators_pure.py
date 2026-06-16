"""序列化器共用校验函数的纯单测（C2）

覆盖 :func:`validate_manual_credentials` 与 :func:`validate_scheduled_task_payload`
的关键分支；保证 Target / ScheduledTask 序列化器接口契约不变。
"""

import pytest
from rest_framework import serializers

from apps.job_mgmt.constants import CredentialSource, JobType, OSType, ScheduleType, SSHCredentialType, TargetSource
from apps.job_mgmt.serializers.validators import validate_manual_credentials, validate_scheduled_task_payload


@pytest.mark.unit
class TestValidateManualCredentialsLinux:
    def _base(self, **overrides):
        attrs = {
            "os_type": OSType.LINUX,
            "credential_source": CredentialSource.MANUAL,
            "ssh_user": "root",
            "ssh_credential_type": SSHCredentialType.PASSWORD,
            "ssh_password": "secret",
            "cloud_region_id": 1,
        }
        attrs.update(overrides)
        return attrs

    def test_password_path_passes(self):
        validate_manual_credentials(self._base(), require_cloud_region=True)

    def test_missing_ssh_user_raises(self):
        with pytest.raises(serializers.ValidationError) as exc:
            validate_manual_credentials(self._base(ssh_user=""), require_cloud_region=True)
        assert "ssh_user" in exc.value.detail

    def test_missing_password_raises(self):
        with pytest.raises(serializers.ValidationError) as exc:
            validate_manual_credentials(self._base(ssh_password=""), require_cloud_region=True)
        assert "ssh_password" in exc.value.detail

    def test_key_auth_requires_ssh_key_file(self):
        attrs = self._base(ssh_credential_type=SSHCredentialType.KEY, ssh_password="")
        with pytest.raises(serializers.ValidationError) as exc:
            validate_manual_credentials(attrs, require_cloud_region=True)
        assert "ssh_key_file" in exc.value.detail

    def test_key_auth_with_ssh_key_file_passes(self):
        attrs = self._base(ssh_credential_type=SSHCredentialType.KEY, ssh_password="", ssh_key_file=object())
        validate_manual_credentials(attrs, require_cloud_region=True)

    def test_cloud_region_required_when_flagged(self):
        with pytest.raises(serializers.ValidationError) as exc:
            validate_manual_credentials(self._base(cloud_region_id=None), require_cloud_region=True)
        assert "cloud_region_id" in exc.value.detail

    def test_cloud_region_not_required_when_disabled(self):
        """测试连接序列化器分支：字段层已强制 required=True，validate 不再重复"""
        validate_manual_credentials(self._base(cloud_region_id=None), require_cloud_region=False)


@pytest.mark.unit
class TestValidateManualCredentialsWindows:
    def _base(self, **overrides):
        attrs = {
            "os_type": OSType.WINDOWS,
            "credential_source": CredentialSource.MANUAL,
            "winrm_user": "Administrator",
            "winrm_password": "pwd",
        }
        attrs.update(overrides)
        return attrs

    def test_winrm_path_passes(self):
        validate_manual_credentials(self._base())

    def test_missing_winrm_user_raises(self):
        with pytest.raises(serializers.ValidationError) as exc:
            validate_manual_credentials(self._base(winrm_user=""))
        assert "winrm_user" in exc.value.detail

    def test_missing_winrm_password_raises(self):
        with pytest.raises(serializers.ValidationError) as exc:
            validate_manual_credentials(self._base(winrm_password=""))
        assert "winrm_password" in exc.value.detail


@pytest.mark.unit
class TestValidateManualCredentialsCredentialMode:
    def test_credential_id_required(self):
        attrs = {
            "os_type": OSType.LINUX,
            "credential_source": CredentialSource.CREDENTIAL,
        }
        with pytest.raises(serializers.ValidationError) as exc:
            validate_manual_credentials(attrs)
        assert "credential_id" in exc.value.detail

    def test_credential_id_present_passes(self):
        attrs = {
            "os_type": OSType.LINUX,
            "credential_source": CredentialSource.CREDENTIAL,
            "credential_id": "cred-1",
        }
        validate_manual_credentials(attrs)


@pytest.mark.unit
class TestValidateScheduledTaskPayloadCreate:
    """instance=None 的创建场景"""

    def _base(self, **overrides):
        attrs = {
            "schedule_type": ScheduleType.CRON,
            "cron_expression": "* * * * *",
            "job_type": JobType.SCRIPT,
            "script_content": "echo hi",
            "script_type": "shell",
            "target_source": TargetSource.NODE_MGMT,
            "target_list": [{"node_id": "n1"}],
        }
        attrs.update(overrides)
        return attrs

    def test_cron_path_passes(self):
        validate_scheduled_task_payload(self._base(), instance=None)

    def test_cron_requires_expression(self):
        with pytest.raises(serializers.ValidationError) as exc:
            validate_scheduled_task_payload(self._base(cron_expression=""), instance=None)
        assert "cron_expression" in exc.value.detail

    def test_once_requires_scheduled_time(self):
        attrs = self._base(schedule_type=ScheduleType.ONCE)
        attrs.pop("cron_expression", None)
        with pytest.raises(serializers.ValidationError) as exc:
            validate_scheduled_task_payload(attrs, instance=None)
        assert "scheduled_time" in exc.value.detail

    def test_script_requires_script_or_content(self):
        attrs = self._base(script_content="", script=None)
        with pytest.raises(serializers.ValidationError) as exc:
            validate_scheduled_task_payload(attrs, instance=None)
        assert "script" in exc.value.detail

    def test_script_content_without_type_raises(self):
        attrs = self._base(script_type=None)
        with pytest.raises(serializers.ValidationError) as exc:
            validate_scheduled_task_payload(attrs, instance=None)
        assert "script_type" in exc.value.detail

    def test_file_distribution_requires_files(self):
        attrs = {
            "schedule_type": ScheduleType.CRON,
            "cron_expression": "* * * * *",
            "job_type": JobType.FILE_DISTRIBUTION,
            "target_path": "/tmp",
            "target_source": TargetSource.NODE_MGMT,
            "target_list": [{"node_id": "n1"}],
        }
        with pytest.raises(serializers.ValidationError) as exc:
            validate_scheduled_task_payload(attrs, instance=None)
        assert "files" in exc.value.detail

    def test_file_distribution_requires_target_path(self):
        attrs = {
            "schedule_type": ScheduleType.CRON,
            "cron_expression": "* * * * *",
            "job_type": JobType.FILE_DISTRIBUTION,
            "files": [{"file_id": 1}],
            "target_source": TargetSource.NODE_MGMT,
            "target_list": [{"node_id": "n1"}],
        }
        with pytest.raises(serializers.ValidationError) as exc:
            validate_scheduled_task_payload(attrs, instance=None)
        assert "target_path" in exc.value.detail

    def test_playbook_requires_playbook(self):
        attrs = {
            "schedule_type": ScheduleType.CRON,
            "cron_expression": "* * * * *",
            "job_type": JobType.PLAYBOOK,
            "target_source": TargetSource.NODE_MGMT,
            "target_list": [{"node_id": "n1"}],
        }
        with pytest.raises(serializers.ValidationError) as exc:
            validate_scheduled_task_payload(attrs, instance=None)
        assert "playbook" in exc.value.detail


@pytest.mark.unit
class TestValidateScheduledTaskPayloadUpdateFallback:
    """instance 非空时，未传字段回退到 instance 属性"""

    def test_unchanged_fields_resolved_from_instance(self):
        """只更新 name 时，schedule_type/job_type 等校验从 instance 取值"""

        class _Inst:
            schedule_type = ScheduleType.CRON
            cron_expression = "* * * * *"
            job_type = JobType.SCRIPT
            script = None
            script_content = "echo"
            script_type = "shell"
            files = None
            target_path = ""
            playbook = None
            target_source = TargetSource.NODE_MGMT

        validate_scheduled_task_payload({"name": "renamed"}, instance=_Inst())

    def test_instance_value_can_be_overridden_by_attrs(self):
        """显式传入空 cron_expression 会失败，即使 instance 上有合法值"""

        class _Inst:
            schedule_type = ScheduleType.CRON
            cron_expression = "* * * * *"

        with pytest.raises(serializers.ValidationError) as exc:
            validate_scheduled_task_payload({"cron_expression": ""}, instance=_Inst())
        assert "cron_expression" in exc.value.detail
