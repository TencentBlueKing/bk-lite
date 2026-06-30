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
