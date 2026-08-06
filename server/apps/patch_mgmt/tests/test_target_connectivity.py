"""目标机连通性探测测试（mock Executor，不依赖真实主机）。"""
import pytest

from apps.core.mixinx import EncryptMixin
from apps.node_mgmt.models import CloudRegion
from apps.patch_mgmt.constants import ConnectivityStatus, OSType, PatchTargetSource
from apps.patch_mgmt.models import PatchTarget
from apps.patch_mgmt.services import target_connectivity
from apps.patch_mgmt.services.target_connectivity import probe_target, probe_target_data

TARGET_URL = "/api/v1/patch_mgmt/api/patch_target/"


def _target(**kw) -> PatchTarget:
    return PatchTarget.objects.create(**{
        "name": "host", "ip": "10.0.0.1", "os_type": OSType.LINUX,
        "ssh_port": 22, "winrm_port": 5986, "team": [1], **kw,
    })


class TestProbeTargetData:
    @pytest.mark.django_db
    def test_manual_linux_uses_regional_nats_executor_ssh(self, mocker):
        region = CloudRegion.objects.create(name="region-a")
        mocker.patch(
            "apps.patch_mgmt.services.target_execution_route.RegionService.get_region_service_instance_id",
            return_value="region-nats-executor",
        )
        executor = mocker.patch(
            "apps.patch_mgmt.services.target_connectivity.Executor"
        ).return_value
        executor.execute_ssh.return_value = {
            "exit_code": 0,
            "stdout": "patch-connectivity-ok\n",
        }

        result = probe_target_data({
            "ip": "10.0.0.8",
            "os_type": OSType.LINUX,
            "source_type": PatchTargetSource.MANUAL,
            "cloud_region_id": region.id,
            "ssh_port": 2222,
            "ssh_user": "root",
            "ssh_credential_type": "password",
            "ssh_password": "plain-secret",
        })

        assert result.reachable is True
        assert result.transport == "nats_ssh"
        assert result.port == 2222
        executor.execute_ssh.assert_called_once()
        assert executor.execute_ssh.call_args.kwargs["password"] == "plain-secret"
        assert executor.execute_ssh.call_args.kwargs["host"] == "10.0.0.8"
        assert executor.execute_ssh.call_args.kwargs["connection_test"] is True

    @pytest.mark.django_db
    def test_manual_windows_uses_regional_ansible_executor_win_ping(self, mocker):
        region = CloudRegion.objects.create(name="region-b")
        mocker.patch(
            "apps.patch_mgmt.services.target_execution_route.AnsibleExecutorResolver.resolve",
            return_value="ansible-node",
        )
        executor = mocker.patch(
            "apps.patch_mgmt.services.target_connectivity.AnsibleExecutor"
        ).return_value
        executor.adhoc.return_value = {"accepted": True, "task_id": "probe-task"}
        executor.task_query.return_value = {"status": "success"}

        probe = probe_target_data({
            "ip": "10.0.0.9",
            "os_type": OSType.WINDOWS,
            "source_type": PatchTargetSource.MANUAL,
            "cloud_region_id": region.id,
            "winrm_port": 5985,
            "winrm_scheme": "http",
            "winrm_transport": "ntlm",
            "winrm_user": "Administrator",
            "winrm_password": "plain-secret",
            "winrm_cert_validation": False,
        })

        assert probe.reachable is True
        assert probe.transport == "ansible_winrm"
        assert probe.port == 5985
        assert executor.adhoc.call_args.kwargs["module"] == "ansible.windows.win_ping"
        credential = executor.adhoc.call_args.kwargs["host_credentials"][0]
        assert credential["host"] == "10.0.0.9"
        assert credential["password"] == "plain-secret"
        executor.task_query.assert_called_once_with("probe-task", timeout=5)

    def test_manual_windows_uses_direct_winrm_only_in_explicit_debug_mode(
        self, mocker, settings
    ):
        settings.DEBUG = True
        settings.PATCH_MGMT_WINDOWS_EXECUTION_MODE = "direct_winrm"
        session = mocker.patch(
            "apps.patch_mgmt.services.target_connectivity.winrm.Session"
        ).return_value
        session.run_ps.return_value = type(
            "Result",
            (),
            {"status_code": 0, "std_out": b"patch-connectivity-ok", "std_err": b""},
        )()

        probe = probe_target_data({
            "ip": "10.0.0.9",
            "os_type": OSType.WINDOWS,
            "source_type": PatchTargetSource.MANUAL,
            "winrm_port": 5985,
            "winrm_scheme": "http",
            "winrm_transport": "ntlm",
            "winrm_user": "Administrator",
            "winrm_password": "plain-secret",
            "winrm_cert_validation": False,
        })

        assert probe.reachable is True
        assert probe.transport == "direct_winrm"
        assert probe.port == 5985


@pytest.mark.django_db
class TestProbeTarget:
    def test_node_linux_executes_local_probe_by_node_id(self, mocker):
        executor_factory = mocker.patch(
            "apps.patch_mgmt.services.target_connectivity.Executor"
        )
        executor_factory.return_value.execute_local.return_value = {
            "exit_code": 0,
            "stdout": "patch-connectivity-ok",
        }
        target = _target(
            source_type=PatchTargetSource.NODE_MGMT,
            node_id="node-1",
        )

        result = probe_target(target)

        assert result.reachable is True
        assert result.transport == "node_executor"
        assert result.port is None
        executor_factory.assert_called_once_with("node-1")
        call = executor_factory.return_value.execute_local.call_args
        assert call.kwargs["shell"] == "sh"
        assert "patch-connectivity-ok" in call.args[0]

    def test_node_windows_executes_powershell_probe_by_node_id(self, mocker):
        executor = mocker.patch(
            "apps.patch_mgmt.services.target_connectivity.Executor"
        ).return_value
        executor.execute_local.return_value = {
            "exit_code": 0,
            "stdout": "patch-connectivity-ok",
        }

        result = probe_target(_target(
            os_type=OSType.WINDOWS,
            source_type=PatchTargetSource.NODE_MGMT,
            node_id="windows-node",
        ))

        assert result.reachable is True
        assert result.transport == "node_executor"
        assert executor.execute_local.call_args.kwargs["shell"] == "powershell"

    def test_manual_linux_uses_decrypted_credentials(self, mocker):
        region = CloudRegion.objects.create(name="region-c")
        credentials = {"ssh_password": "plain-secret"}
        EncryptMixin.encrypt_field("ssh_password", credentials)
        target = _target(
            source_type=PatchTargetSource.MANUAL,
            cloud_region_id=region.id,
            ssh_port=2222,
            ssh_user="root",
            ssh_password=credentials["ssh_password"],
        )
        mocker.patch(
            "apps.patch_mgmt.services.target_execution_route.RegionService.get_region_service_instance_id",
            return_value="region-executor",
        )
        executor = mocker.patch(
            "apps.patch_mgmt.services.target_connectivity.Executor"
        ).return_value
        executor.execute_ssh.return_value = {
            "exit_code": 0,
            "stdout": "patch-connectivity-ok",
        }

        res = probe_target(target)

        assert res.reachable is True
        assert res.port == 2222
        assert executor.execute_ssh.call_args.kwargs["password"] == "plain-secret"

    def test_command_without_marker_is_failed(self, mocker):
        executor = mocker.patch(
            "apps.patch_mgmt.services.target_connectivity.Executor"
        ).return_value
        executor.execute_local.return_value = {"exit_code": 0, "stdout": "unexpected"}

        res = probe_target(_target(
            source_type=PatchTargetSource.NODE_MGMT,
            node_id="node-1",
        ))

        assert res.reachable is False
        assert res.reason_code == "command_failed"

    def test_missing_node_id_is_explicit_configuration_failure(self):
        res = probe_target(_target(
            source_type=PatchTargetSource.NODE_MGMT,
            node_id="",
        ))

        assert res.reachable is False
        assert res.reason_code == "invalid_configuration"
        assert "node_id" in res.detail

    def test_executor_health_is_not_used_as_connectivity_result(self, mocker):
        executor = mocker.patch(
            "apps.patch_mgmt.services.target_connectivity.Executor"
        ).return_value
        executor.execute_local.side_effect = TimeoutError("command timeout")

        res = probe_target(_target(
            source_type=PatchTargetSource.NODE_MGMT,
            node_id="node-1",
        ))

        assert res.reachable is False
        assert res.reason_code == "connection_timeout"
        executor.health_check.assert_not_called()

    def test_missing_ansible_executor_is_explicitly_reported(self, mocker):
        mocker.patch(
            "apps.patch_mgmt.services.target_execution_route.AnsibleExecutorResolver.resolve",
            side_effect=RuntimeError("not found"),
        )

        res = probe_target(_target(
            os_type=OSType.WINDOWS,
            source_type=PatchTargetSource.MANUAL,
            cloud_region_id=99,
        ))

        assert res.reachable is False
        assert res.reason_code == "executor_unavailable"
        assert "Ansible Executor" in res.detail

    def test_unknown_source_type_is_failed(self):
        res = probe_target(_target(
            source_type="unsupported",
            node_id="node-1",
        ))

        assert res.reachable is False
        assert res.reason_code == "invalid_configuration"


@pytest.mark.django_db
class TestCheckConnectivityViewApi:
    def test_unsaved_linux_form_uses_submitted_credentials(self, su_client, mocker):
        probe = mocker.patch(
            "apps.patch_mgmt.views.patch_target.probe_target_data",
            return_value=target_connectivity.TargetProbeResult(True, 22, "SSH 认证成功"),
        )

        resp = su_client.post(
            f"{TARGET_URL}test_connectivity/",
            {
                "ip": "10.0.0.8",
                "os_type": OSType.LINUX,
                "source_type": PatchTargetSource.MANUAL,
                "cloud_region_id": 1,
                "ssh_port": 22,
                "ssh_user": "root",
                "ssh_credential_type": "password",
                "ssh_password": "plain-secret",
            },
            format="json",
        )

        assert resp.status_code == 200
        assert resp.data["connectivity_status"] == ConnectivityStatus.CONNECTED
        assert probe.call_args.args[0]["ssh_password"] == "plain-secret"
        assert probe.call_args.args[0]["cloud_region_id"] == 1

    def test_action_sets_connected(self, su_client, mocker):
        mocker.patch(
            "apps.patch_mgmt.services.target_connectivity.probe_target",
            return_value=target_connectivity.TargetProbeResult(True, 22, "SSH 认证成功"),
        )
        target = _target()
        resp = su_client.post(f"{TARGET_URL}{target.id}/check_connectivity/")
        assert resp.status_code == 200
        assert resp.data["connectivity_status"] == ConnectivityStatus.CONNECTED
        target.refresh_from_db()
        assert target.connectivity_status == ConnectivityStatus.CONNECTED

    def test_edit_form_test_reuses_saved_password_without_mutating_target(self, su_client, mocker):
        credentials = {"ssh_password": "saved-secret"}
        EncryptMixin.encrypt_field("ssh_password", credentials)
        target = _target(ssh_user="old-root", ssh_password=credentials["ssh_password"])
        protocol_probe = mocker.patch(
            "apps.patch_mgmt.views.patch_target.probe_target_data",
            return_value=target_connectivity.TargetProbeResult(True, 22, "SSH 认证成功"),
        )

        resp = su_client.post(
            f"{TARGET_URL}{target.id}/check_connectivity/",
            {"ssh_user": "new-root"},
            format="json",
        )

        assert resp.status_code == 200
        tested = protocol_probe.call_args.args[0]
        assert tested["ssh_user"] == "new-root"
        assert tested["ssh_password"] == "saved-secret"
        target.refresh_from_db()
        assert target.ssh_user == "old-root"

    def test_action_sets_failed(self, su_client, mocker):
        mocker.patch(
            "apps.patch_mgmt.services.target_connectivity.probe_target",
            return_value=target_connectivity.TargetProbeResult(False, 22, "SSH 认证失败"),
        )
        target = _target()
        resp = su_client.post(f"{TARGET_URL}{target.id}/check_connectivity/")
        assert resp.status_code == 200
        assert resp.data["connectivity_status"] == ConnectivityStatus.FAILED


@pytest.mark.django_db
class TestTargetCredentialUpdate:
    def test_new_password_replaces_key_and_removes_old_file(self, su_client, mocker):
        target = _target(
            ssh_user="root",
            ssh_credential_type="key",
            ssh_key_file="patch-target-keys/old.pem",
        )
        delete = mocker.patch.object(target.ssh_key_file.storage, "delete")
        response = su_client.put(
            f"{TARGET_URL}{target.id}/",
            {
                "name": target.name,
                "ip": target.ip,
                "ssh_credential_type": "password",
                "ssh_password": "new-secret",
            },
            format="json",
        )
        assert response.status_code == 200, response.data

        target.refresh_from_db()
        assert target.ssh_key_file.name == ""
        assert target.ssh_password != "new-secret"
        delete.assert_called_once_with("patch-target-keys/old.pem")

    def test_unchanged_password_is_preserved(self, su_client):
        credentials = {"ssh_password": "saved-secret"}
        EncryptMixin.encrypt_field("ssh_password", credentials)
        target = _target(ssh_user="root", ssh_password=credentials["ssh_password"])

        response = su_client.put(
            f"{TARGET_URL}{target.id}/",
            {"name": "renamed", "ip": target.ip},
            format="json",
        )
        assert response.status_code == 200, response.data

        target.refresh_from_db()
        assert target.ssh_password == credentials["ssh_password"]

    def test_metadata_only_update_does_not_probe(self, su_client, mocker):
        target = _target(connectivity_status=ConnectivityStatus.CONNECTED)
        probe = mocker.patch("apps.patch_mgmt.tasks.probe_target_connectivity.delay")

        response = su_client.put(
            f"{TARGET_URL}{target.id}/",
            {"name": "renamed", "ip": target.ip},
            format="json",
        )

        assert response.status_code == 200, response.data
        target.refresh_from_db()
        assert target.connectivity_status == ConnectivityStatus.CONNECTED
        probe.assert_not_called()

    def test_connection_update_resets_status_and_enqueues_probe(self, su_client, mocker):
        target = _target(connectivity_status=ConnectivityStatus.CONNECTED)
        probe = mocker.patch("apps.patch_mgmt.tasks.probe_target_connectivity.delay")

        response = su_client.put(
            f"{TARGET_URL}{target.id}/",
            {"name": target.name, "ip": "10.0.0.2"},
            format="json",
        )

        assert response.status_code == 200, response.data
        target.refresh_from_db()
        assert target.connectivity_status == ConnectivityStatus.UNKNOWN
        probe.assert_called_once_with(target.id)
