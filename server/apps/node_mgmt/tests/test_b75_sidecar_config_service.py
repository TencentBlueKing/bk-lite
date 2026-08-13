"""SidecarConfigService 真实行为测试：读写配置、深合并、重启、属性同步。

仅 mock Executor RPC 边界。断言真实合并逻辑与命令构建/异常。
"""
import base64
import shlex
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from apps.node_mgmt.constants.controller import ControllerConstants
from apps.node_mgmt.constants.installer import InstallerConstants
from apps.node_mgmt.constants.node import NodeConstants
from apps.node_mgmt.models import Node
from apps.node_mgmt.models.cloud_region import CloudRegion
from apps.node_mgmt.services.sidecar_config import SidecarConfigService
from apps.node_mgmt.tasks.sidecar_config import sync_node_properties_to_sidecar
from nats_client.exceptions import NatsClientException

REPO_ROOT = Path(__file__).resolve().parents[4]
LINUX_SIDECAR_PATH = "/opt/fusion-collectors/sidecar.yml"
WINDOWS_SIDECAR_PATH = r"C:\fusion-collectors\sidecar.yml"
LINUX_MISSING_FILE_ERROR = (
    "Command execution failed with exit code 1: exit status 1 | "
    f"Output: cat: {LINUX_SIDECAR_PATH}: No such file or directory"
)
WINDOWS_MISSING_FILE_ERROR = (
    "Command execution failed with exit code 1: exit status 1 | "
    f"Output: Get-Content : Cannot find path '{WINDOWS_SIDECAR_PATH}' because it does not exist."
)


@pytest.fixture
def linux_node(db):
    region = CloudRegion.objects.create(name="cr-sc")
    return Node.objects.create(
        id="node-sc-1", name="sc-node", ip="10.2.2.2", operating_system="linux",
        collector_configuration_directory="/etc", cloud_region=region,
    )


@pytest.fixture
def windows_node(db):
    region = CloudRegion.objects.create(name="cr-sc-win")
    return Node.objects.create(
        id="node-sc-win", name="win-node", ip="10.2.2.3", operating_system="windows",
        collector_configuration_directory="C:\\etc", cloud_region=region,
    )


# --------------------------------------------------------------------------- #
# _deep_merge (pure)
# --------------------------------------------------------------------------- #
def test_deep_merge_nested_overrides():
    base = {"a": 1, "nested": {"x": 1, "y": 2}}
    updates = {"nested": {"y": 9, "z": 3}, "b": 2}
    result = SidecarConfigService._deep_merge(base, updates)
    assert result == {"a": 1, "nested": {"x": 1, "y": 9, "z": 3}, "b": 2}
    # base 未被修改
    assert base["nested"] == {"x": 1, "y": 2}


def test_deep_merge_scalar_overrides_dict():
    result = SidecarConfigService._deep_merge({"a": {"x": 1}}, {"a": "flat"})
    assert result == {"a": "flat"}


# --------------------------------------------------------------------------- #
# _get_config_path / _get_restart_command
# --------------------------------------------------------------------------- #
def test_sidecar_config_paths_use_yml_under_install_dirs():
    assert ControllerConstants.SIDECAR_CONFIG_FILENAME == "sidecar.yml"
    assert ControllerConstants.SIDECAR_CONFIG_PATH[NodeConstants.LINUX_OS] == LINUX_SIDECAR_PATH
    assert ControllerConstants.SIDECAR_CONFIG_PATH[NodeConstants.WINDOWS_OS] == WINDOWS_SIDECAR_PATH
    assert LINUX_SIDECAR_PATH == f"{InstallerConstants.LINUX_INSTALL_DEFAULT_DIR}/sidecar.yml"
    assert WINDOWS_SIDECAR_PATH == rf"{InstallerConstants.WINDOWS_INSTALL_DEFAULT_DIR}\sidecar.yml"
    assert LINUX_SIDECAR_PATH == (
        f"{ControllerConstants.LINUX_INSTALL_DIR}/{ControllerConstants.SIDECAR_CONFIG_FILENAME}"
    )
    assert WINDOWS_SIDECAR_PATH == (
        rf"{ControllerConstants.WINDOWS_INSTALL_DIR}\{ControllerConstants.SIDECAR_CONFIG_FILENAME}"
    )


def test_sidecar_config_filename_matches_fusion_collector_templates():
    linux_template = REPO_ROOT / "agents/fusion-collector/misc/linux/sidecar.yml"
    windows_template = REPO_ROOT / "agents/fusion-collector/misc/windows/sidecar.yml"
    assert linux_template.is_file()
    assert windows_template.is_file()
    assert not (linux_template.with_suffix(".yaml")).exists()
    assert not (windows_template.with_suffix(".yaml")).exists()
    assert ControllerConstants.SIDECAR_CONFIG_PATH[NodeConstants.LINUX_OS].endswith(linux_template.name)
    assert ControllerConstants.SIDECAR_CONFIG_PATH[NodeConstants.WINDOWS_OS].endswith(windows_template.name)


@pytest.mark.django_db
def test_get_config_path_linux(linux_node):
    assert SidecarConfigService._get_config_path(linux_node) == LINUX_SIDECAR_PATH


@pytest.mark.django_db
def test_get_config_path_windows(windows_node):
    assert SidecarConfigService._get_config_path(windows_node) == WINDOWS_SIDECAR_PATH


@pytest.mark.django_db
def test_get_restart_command_returns_tuple(linux_node):
    cmd, shell = SidecarConfigService._get_restart_command(linux_node)
    assert isinstance(cmd, str)


@pytest.mark.django_db
def test_get_restart_command_windows_uses_powershell(windows_node):
    cmd, shell = SidecarConfigService._get_restart_command(windows_node)
    assert shell == "powershell"
    assert "sidecar" in cmd


# --------------------------------------------------------------------------- #
# _read_config
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_read_config_success(linux_node):
    executor = MagicMock()
    executor.execute_local.return_value = {"success": True, "stdout": "node_name: foo\ntags:\n  - a"}
    with patch("apps.node_mgmt.services.sidecar_config.Executor", return_value=executor):
        config = SidecarConfigService._read_config(linux_node)
    assert config["node_name"] == "foo"
    assert config["tags"] == ["a"]


@pytest.mark.django_db
def test_read_config_file_not_found_raises(linux_node):
    executor = MagicMock()
    executor.execute_local.return_value = {"success": False, "stderr": "No such file"}
    with patch("apps.node_mgmt.services.sidecar_config.Executor", return_value=executor):
        with pytest.raises(ValueError) as exc:
            SidecarConfigService._read_config(linux_node)
    assert "not found" in str(exc.value)


@pytest.mark.django_db
def test_read_config_permission_denied_raises(linux_node):
    executor = MagicMock()
    executor.execute_local.return_value = {"success": False, "stderr": "Permission denied"}
    with patch("apps.node_mgmt.services.sidecar_config.Executor", return_value=executor):
        with pytest.raises(ValueError) as exc:
            SidecarConfigService._read_config(linux_node)
    assert "Permission denied" in str(exc.value)


@pytest.mark.django_db
def test_read_config_empty_file_raises(linux_node):
    executor = MagicMock()
    executor.execute_local.return_value = {"success": True, "stdout": "   "}
    with patch("apps.node_mgmt.services.sidecar_config.Executor", return_value=executor):
        with pytest.raises(ValueError) as exc:
            SidecarConfigService._read_config(linux_node)
    assert "empty" in str(exc.value)


@pytest.mark.django_db
def test_read_config_linux_cats_install_path(linux_node):
    executor = MagicMock()
    executor.execute_local.return_value = "node_name: foo\n"
    with patch("apps.node_mgmt.services.sidecar_config.Executor", return_value=executor):
        SidecarConfigService._read_config(linux_node)
    command = executor.execute_local.call_args.args[0]
    assert command == f"cat {shlex.quote(LINUX_SIDECAR_PATH)}"
    assert executor.execute_local.call_args.kwargs["shell"] is None


@pytest.mark.django_db
def test_read_config_windows_reads_install_path(windows_node):
    executor = MagicMock()
    executor.execute_local.return_value = "node_name: w\n"
    with patch("apps.node_mgmt.services.sidecar_config.Executor", return_value=executor):
        SidecarConfigService._read_config(windows_node)
    command = executor.execute_local.call_args.args[0]
    kwargs = executor.execute_local.call_args.kwargs
    assert command == f"Get-Content -Path '{WINDOWS_SIDECAR_PATH}' -Raw"
    assert kwargs["shell"] == "powershell"


@pytest.mark.django_db
def test_read_config_accepts_plain_stdout_string(linux_node):
    executor = MagicMock()
    executor.execute_local.return_value = "node_name: foo\ntags:\n  - a\n"
    with patch("apps.node_mgmt.services.sidecar_config.Executor", return_value=executor):
        config = SidecarConfigService._read_config(linux_node)
    assert config["node_name"] == "foo"
    assert config["tags"] == ["a"]


@pytest.mark.django_db
def test_read_config_nats_exception_file_not_found_linux(linux_node):
    executor = MagicMock()
    executor.execute_local.side_effect = NatsClientException(LINUX_MISSING_FILE_ERROR)
    with patch("apps.node_mgmt.services.sidecar_config.Executor", return_value=executor):
        with pytest.raises(ValueError) as exc:
            SidecarConfigService._read_config(linux_node)
    assert "not found" in str(exc.value)
    assert LINUX_SIDECAR_PATH in str(exc.value)


@pytest.mark.django_db
def test_read_config_nats_exception_file_not_found_windows(windows_node):
    executor = MagicMock()
    executor.execute_local.side_effect = NatsClientException(WINDOWS_MISSING_FILE_ERROR)
    with patch("apps.node_mgmt.services.sidecar_config.Executor", return_value=executor):
        with pytest.raises(ValueError) as exc:
            SidecarConfigService._read_config(windows_node)
    assert "not found" in str(exc.value)
    assert WINDOWS_SIDECAR_PATH in str(exc.value)


# --------------------------------------------------------------------------- #
# _write_config / _restart_service
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_write_config_linux_targets_install_path(linux_node):
    executor = MagicMock()
    executor.execute_local.return_value = ""
    with patch("apps.node_mgmt.services.sidecar_config.Executor", return_value=executor):
        SidecarConfigService._write_config(linux_node, {"node_name": "x"})
    command = executor.execute_local.call_args.args[0]
    assert shlex.quote(LINUX_SIDECAR_PATH) in command
    assert executor.execute_local.call_args.kwargs["shell"] == "bash"


@pytest.mark.django_db
def test_write_config_windows_targets_install_path(windows_node):
    executor = MagicMock()
    executor.execute_local.return_value = ""
    with patch("apps.node_mgmt.services.sidecar_config.Executor", return_value=executor):
        SidecarConfigService._write_config(windows_node, {"node_name": "x"})
    command = executor.execute_local.call_args.args[0]
    kwargs = executor.execute_local.call_args.kwargs
    assert f"Set-Content -Path '{WINDOWS_SIDECAR_PATH}'" in command
    assert kwargs["shell"] == "powershell"


@pytest.mark.django_db
def test_write_config_linux_does_not_embed_yaml_in_shell(linux_node):
    executor = MagicMock()
    executor.execute_local.return_value = {"success": True}
    injected_name = "safe\nEOF\nid > /tmp/pwned\n"

    with patch("apps.node_mgmt.services.sidecar_config.Executor", return_value=executor):
        SidecarConfigService._write_config(linux_node, {"node_name": injected_name})

    command = executor.execute_local.call_args.args[0]
    kwargs = executor.execute_local.call_args.kwargs
    assert kwargs["shell"] == "bash"
    assert "<< 'EOF'" not in command
    assert injected_name not in command
    assert "id > /tmp/pwned" not in command
    command_parts = shlex.split(command)
    encoded_content = command_parts[2]
    assert yaml.safe_load(base64.b64decode(encoded_content).decode("utf-8")) == {
        "node_name": injected_name
    }


def _load_linux_write_command_yaml(command):
    encoded_content = shlex.split(command)[2]
    return yaml.safe_load(base64.b64decode(encoded_content).decode("utf-8"))


@pytest.mark.django_db
def test_write_config_permission_denied_raises(linux_node):
    executor = MagicMock()
    executor.execute_local.return_value = {"success": False, "stderr": "Permission denied"}
    with patch("apps.node_mgmt.services.sidecar_config.Executor", return_value=executor):
        with pytest.raises(ValueError) as exc:
            SidecarConfigService._write_config(linux_node, {"a": 1})
    assert "Permission denied" in str(exc.value)


@pytest.mark.django_db
def test_restart_service_failure_raises(linux_node):
    executor = MagicMock()
    executor.execute_local.return_value = {"success": False, "stderr": "no perm"}
    with patch("apps.node_mgmt.services.sidecar_config.Executor", return_value=executor):
        with pytest.raises(ValueError) as exc:
            SidecarConfigService._restart_service(linux_node)
    assert "restart failed" in str(exc.value)


# --------------------------------------------------------------------------- #
# update_config (full flow)
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_update_config_node_not_found_raises():
    with pytest.raises(ValueError) as exc:
        SidecarConfigService.update_config("no-node", {})
    assert "Node not found" in str(exc.value)


@pytest.mark.django_db
def test_update_config_merges_and_returns(linux_node):
    executor = MagicMock()
    # read returns base config, write/restart succeed
    executor.execute_local.side_effect = [
        {"success": True, "stdout": "node_name: old\nlog_level: info"},
        {"success": True},
        {"success": True},
    ]
    with patch("apps.node_mgmt.services.sidecar_config.Executor", return_value=executor):
        result = SidecarConfigService.update_config(linux_node.id, {"log_level": "debug"})
    assert result["log_level"] == "debug"
    assert result["node_name"] == "old"


# --------------------------------------------------------------------------- #
# sync_node_properties
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_sync_node_properties_noop_when_nothing_to_sync(linux_node):
    # 不应调用 Executor
    with patch("apps.node_mgmt.services.sidecar_config.Executor") as exec_cls:
        SidecarConfigService.sync_node_properties(linux_node)
    exec_cls.assert_not_called()


@pytest.mark.django_db
def test_sync_node_properties_updates_name_and_orgs(linux_node):
    executor = MagicMock()
    executor.execute_local.side_effect = [
        {"success": True, "stdout": "node_name: old\ntags:\n  - group:1\n  - keepme"},
        {"success": True},
        {"success": True},
    ]
    with patch("apps.node_mgmt.services.sidecar_config.Executor", return_value=executor):
        SidecarConfigService.sync_node_properties(linux_node, name="newname", organizations=["5", "6"])
    # 写配置时第二次调用，验证内容含新名称与新 group tags
    write_command = executor.execute_local.call_args_list[1].args[0]
    written_config = _load_linux_write_command_yaml(write_command)
    assert written_config["node_name"] == "newname"
    assert written_config["tags"] == ["keepme", "group:5", "group:6"]


@pytest.mark.django_db
def test_sync_node_properties_updates_name_and_orgs_windows(windows_node):
    executor = MagicMock()
    executor.execute_local.side_effect = [
        "node_name: old\ntags:\n  - group:1\n  - keepme\n",
        "",
        "",
    ]
    with patch("apps.node_mgmt.services.sidecar_config.Executor", return_value=executor):
        SidecarConfigService.sync_node_properties(
            windows_node, name="newname", organizations=["5", "6"]
        )
    write_command = executor.execute_local.call_args_list[1].args[0]
    assert f"Set-Content -Path '{WINDOWS_SIDECAR_PATH}'" in write_command
    assert "node_name: newname" in write_command
    assert "group:5" in write_command
    assert "group:6" in write_command


@pytest.mark.django_db
def test_sync_node_properties_nats_missing_file_raises(linux_node):
    executor = MagicMock()
    executor.execute_local.side_effect = NatsClientException(LINUX_MISSING_FILE_ERROR)
    with patch("apps.node_mgmt.services.sidecar_config.Executor", return_value=executor):
        with pytest.raises(ValueError, match="not found"):
            SidecarConfigService.sync_node_properties(linux_node, name="x")


@pytest.mark.django_db
def test_sync_task_returns_failure_for_missing_linux_config(linux_node):
    executor = MagicMock()
    executor.execute_local.side_effect = NatsClientException(LINUX_MISSING_FILE_ERROR)
    with patch("apps.node_mgmt.services.sidecar_config.Executor", return_value=executor):
        result = sync_node_properties_to_sidecar.run(linux_node.id, name="x")
    assert result["success"] is False
    assert "not found" in result["error"]
    assert LINUX_SIDECAR_PATH in result["error"]


@pytest.mark.django_db
def test_sync_task_returns_failure_for_missing_windows_config(windows_node):
    executor = MagicMock()
    executor.execute_local.side_effect = NatsClientException(WINDOWS_MISSING_FILE_ERROR)
    with patch("apps.node_mgmt.services.sidecar_config.Executor", return_value=executor):
        result = sync_node_properties_to_sidecar.run(windows_node.id, name="x")
    assert result["success"] is False
    assert "not found" in result["error"]
    assert WINDOWS_SIDECAR_PATH in result["error"]
