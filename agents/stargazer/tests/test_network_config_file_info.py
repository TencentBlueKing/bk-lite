import base64

import pytest

from plugins.inputs.network_config_file.network_config_file_info import NetworkConfigFileInfo, validate_safe_command


def test_validate_safe_command_allows_display_saved_configuration():
    assert validate_safe_command("display saved-configuration") == "display saved-configuration"


@pytest.mark.parametrize("command", ["reload", "configure terminal", "write erase", "delete flash:/x"])
def test_validate_safe_command_rejects_dangerous_commands(command):
    with pytest.raises(ValueError, match="高危"):
        validate_safe_command(command)


def test_merge_outputs_keeps_command_boundaries():
    merged = NetworkConfigFileInfo.merge_command_outputs(
        [
            {"command": "show running-config", "output": "line1"},
            {"command": "show version", "output": "line2"},
        ]
    )

    assert "===== command: show running-config =====" in merged
    assert "line1" in merged
    assert "===== command: show version =====" in merged
    assert "line2" in merged


class FakeNetConnect:
    def __init__(self):
        self.enabled = False
        self.commands = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def enable(self):
        self.enabled = True

    def disable_paging(self, command=None):
        self.commands.append(command)

    def send_command(self, command, **kwargs):
        self.commands.append(command)
        return f"output for {command}"


def test_collect_builds_success_payload(monkeypatch):
    fake = FakeNetConnect()
    monkeypatch.setattr(
        "plugins.inputs.network_config_file.network_config_file_info.ConnectHandler",
        lambda **kwargs: fake,
    )
    plugin = NetworkConfigFileInfo(
        {
            "host": "10.0.0.1",
            "username": "admin",
            "password": "secret",
            "enable_password": "enable-secret",
            "need_enable": "true",
            "device_type": "cisco_ios",
            "commands": "show running-config\nshow version",
            "config_name": "running-config",
            "collect_task_id": "42",
            "target_model_id": "switch",
            "target_instance_id": "101",
        }
    )

    result = plugin.list_all_resources()

    assert result["success"] is True
    payload = result["result"]
    assert payload["status"] == "success"
    assert payload["file_name"] == "running-config"
    decoded = base64.b64decode(payload["content_base64"]).decode()
    assert "output for show running-config" in decoded
    assert "output for show version" in decoded
    assert fake.enabled is True


def test_collect_returns_error_when_one_command_fails(monkeypatch):
    class FailingNetConnect(FakeNetConnect):
        def send_command(self, command, **kwargs):
            if command == "show bad":
                return "Invalid input detected"
            return "ok"

    fake = FailingNetConnect()
    monkeypatch.setattr(
        "plugins.inputs.network_config_file.network_config_file_info.ConnectHandler",
        lambda **kwargs: fake,
    )
    plugin = NetworkConfigFileInfo(
        {
            "host": "10.0.0.1",
            "username": "admin",
            "password": "secret",
            "device_type": "cisco_ios",
            "commands": "show version\nshow bad",
            "config_name": "running-config",
            "collect_task_id": "42",
            "target_model_id": "switch",
            "target_instance_id": "101",
        }
    )

    result = plugin.list_all_resources()

    assert result["success"] is False
    assert "show bad" in result["result"]["cmdb_collect_error"]
    assert "Invalid input" in result["result"]["cmdb_collect_error"]
