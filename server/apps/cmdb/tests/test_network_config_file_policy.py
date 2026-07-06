import pytest

from apps.cmdb.services.network_config_file_policy import (
    SUPPORTED_NETWORK_CONFIG_MODELS,
    get_supported_brand_options,
    resolve_device_type,
    validate_commands,
    validate_network_config_instance,
    validate_safe_command,
)
from apps.core.exceptions.base_app_exception import BaseAppException


def test_supported_models_are_only_mvp_network_models():
    assert SUPPORTED_NETWORK_CONFIG_MODELS == {"switch", "router", "firewall", "loadbalance"}


@pytest.mark.parametrize(
    ("brand", "expected"),
    [
        ("华为", "huawei"),
        ("Huawei", "huawei"),
        ("H3C", "hp_comware"),
        ("HP Comware", "hp_comware"),
        ("Cisco", "cisco_ios"),
        ("Juniper", "juniper_junos"),
        ("F5", "f5_tmsh"),
        ("Fortinet", "fortinet"),
    ],
)
def test_resolve_device_type_normalizes_supported_brand_aliases(brand, expected):
    assert resolve_device_type(brand) == expected


def test_resolve_device_type_rejects_empty_brand():
    with pytest.raises(BaseAppException, match="缺少厂商"):
        resolve_device_type("")


def test_resolve_device_type_rejects_unsupported_brand():
    with pytest.raises(BaseAppException, match="暂不支持"):
        resolve_device_type("UnknownVendor")


def test_validate_network_config_instance_requires_supported_model_and_brand():
    instance = {"_id": 11, "model_id": "switch", "brand": "Cisco", "ip_addr": "10.0.0.1"}

    result = validate_network_config_instance(instance)

    assert result["device_type"] == "cisco_ios"
    assert result["host"] == "10.0.0.1"


def test_validate_network_config_instance_rejects_non_mvp_model():
    with pytest.raises(BaseAppException, match="仅支持"):
        validate_network_config_instance({"model_id": "host", "brand": "Cisco", "ip_addr": "10.0.0.1"})


def test_get_supported_brand_options_is_frontend_friendly():
    options = get_supported_brand_options()

    assert {"label": "Cisco", "device_type": "cisco_ios"} in options
    assert any("华为" in item["label"] for item in options)


# ---------------------------------------------------------------------------
# P1-2.5 — validate_safe_command 必须拦截更多高危命令
# ---------------------------------------------------------------------------

class TestValidateSafeCommandDangerous:
    """P1-2.5: 原黑名单只覆盖 Cisco/Huawei 常见写操作,但漏了多类真高危命令:
    - 'write' (Cisco write erase / write memory,清/写配置)
    - 'request' (Junos request system reboot 等)
    - 'do' (Cisco 从 config 模式逃逸,临时跑任意命令)
    - shell 逃逸类(sudo / bash / sh / python)
    - 文件删除 rm
    - 跳转类 telnet / ssh

    这些都是真实设备上能搞坏生产的高危操作。"""

    @pytest.mark.parametrize("command", [
        "write erase", "write memory", "WRITE", "write",
        "request system reboot", "request system halt", "request",
        "do show running-config", "do",
    ])
    def test_dangerous_writes_and_escape_are_blocked(self, command):
        with pytest.raises(BaseAppException, match="高危操作"):
            validate_safe_command(command)

    @pytest.mark.parametrize("command", [
        "sudo reboot", "bash", "sh", "python -c 'import os'",
        "rm -rf /", "telnet 10.0.0.1", "ssh user@host",
    ])
    def test_shell_escape_and_jump_are_blocked(self, command):
        with pytest.raises(BaseAppException, match="高危操作"):
            validate_safe_command(command)

    @pytest.mark.parametrize("command", [
        "show running-config",
        "display version",
        "show version",
        "show ip interface brief",
    ])
    def test_legitimate_read_commands_are_allowed(self, command):
        # 合法的只读命令必须能通过
        assert validate_safe_command(command) == command.lower().strip() or validate_safe_command(command) == " ".join(command.split())


def test_validate_commands_rejects_when_any_command_is_dangerous():
    """validate_commands 必须在任一命令高危时整批拒收。"""
    with pytest.raises(BaseAppException, match="高危操作"):
        validate_commands("show version\nwrite erase\ndisplay version")
