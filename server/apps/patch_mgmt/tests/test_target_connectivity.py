"""目标机连通性探测测试(mock socket,不依赖真实主机)。"""
import pytest

from apps.core.mixinx import EncryptMixin
from apps.patch_mgmt.constants import ConnectivityStatus, OSType
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
    def test_linux_probe_authenticates_with_ssh_credentials(self, mocker):
        client = mocker.Mock()
        client.exec_command.return_value = (None, mocker.Mock(), mocker.Mock())
        client.exec_command.return_value[1].channel.recv_exit_status.return_value = 0
        ssh_client = mocker.patch("paramiko.SSHClient", return_value=client)

        result = probe_target_data({
            "ip": "10.0.0.8",
            "os_type": OSType.LINUX,
            "ssh_port": 2222,
            "ssh_user": "root",
            "ssh_credential_type": "password",
            "ssh_password": "plain-secret",
        })

        assert result.reachable is True
        assert result.detail == "SSH 认证成功"
        ssh_client.assert_called_once_with()
        assert client.connect.call_args.kwargs["password"] == "plain-secret"
        assert client.connect.call_args.kwargs["hostname"] == "10.0.0.8"

    def test_windows_probe_authenticates_with_winrm_credentials(self, mocker):
        result = mocker.Mock(status_code=0)
        session = mocker.Mock()
        session.run_ps.return_value = result
        session_factory = mocker.patch("winrm.Session", return_value=session)

        probe = probe_target_data({
            "ip": "10.0.0.9",
            "os_type": OSType.WINDOWS,
            "winrm_port": 5985,
            "winrm_scheme": "http",
            "winrm_transport": "ntlm",
            "winrm_user": "Administrator",
            "winrm_password": "plain-secret",
            "winrm_cert_validation": False,
        })

        assert probe.reachable is True
        assert probe.detail == "WinRM 认证成功"
        assert session_factory.call_args.args[0] == "http://10.0.0.9:5985/wsman"
        assert session_factory.call_args.kwargs["auth"] == ("Administrator", "plain-secret")


@pytest.mark.django_db
class TestProbeTarget:
    def test_reachable_linux_uses_decrypted_credentials(self, mocker):
        credentials = {"ssh_password": "plain-secret"}
        EncryptMixin.encrypt_field("ssh_password", credentials)
        target = _target(ssh_port=2222, ssh_user="root", ssh_password=credentials["ssh_password"])
        protocol_probe = mocker.patch.object(
            target_connectivity,
            "probe_target_data",
            return_value=target_connectivity.TargetProbeResult(True, 2222, "SSH 认证成功"),
        )

        res = probe_target(target)

        assert res.reachable is True
        assert res.port == 2222
        assert protocol_probe.call_args.args[0]["ssh_password"] == "plain-secret"
        assert protocol_probe.call_args.args[0]["ssh_port"] == 2222

    def test_windows_uses_winrm_port(self, mocker):
        protocol_probe = mocker.patch.object(
            target_connectivity,
            "probe_target_data",
            return_value=target_connectivity.TargetProbeResult(True, 5985, "WinRM 认证成功"),
        )
        res = probe_target(_target(os_type=OSType.WINDOWS, winrm_port=5985))
        assert res.port == 5985
        assert protocol_probe.call_args.args[0]["winrm_port"] == 5985

    def test_unreachable_returns_false(self, mocker):
        mocker.patch.object(
            target_connectivity,
            "probe_target_data",
            return_value=target_connectivity.TargetProbeResult(False, 22, "SSH 认证失败"),
        )
        res = probe_target(_target())
        assert res.reachable is False


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
