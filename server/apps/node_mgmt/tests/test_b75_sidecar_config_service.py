"""SidecarConfigService 真实行为测试：读写配置、深合并、重启、属性同步。

仅 mock Executor RPC 边界。断言真实合并逻辑与命令构建/异常。
"""
import pytest
from unittest.mock import MagicMock, patch

from apps.node_mgmt.constants.controller import ControllerConstants
from apps.node_mgmt.models import Node
from apps.node_mgmt.models.cloud_region import CloudRegion
from apps.node_mgmt.services.sidecar_config import SidecarConfigService


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
@pytest.mark.django_db
def test_get_config_path_linux(linux_node):
    path = SidecarConfigService._get_config_path(linux_node)
    assert path == ControllerConstants.SIDECAR_CONFIG_PATH["linux"]


@pytest.mark.django_db
def test_get_restart_command_returns_tuple(linux_node):
    cmd, shell = SidecarConfigService._get_restart_command(linux_node)
    assert isinstance(cmd, str)


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
def test_read_config_windows_uses_powershell(windows_node):
    executor = MagicMock()
    executor.execute_local.return_value = {"success": True, "stdout": "node_name: w"}
    with patch("apps.node_mgmt.services.sidecar_config.Executor", return_value=executor):
        SidecarConfigService._read_config(windows_node)
    kwargs = executor.execute_local.call_args.kwargs
    assert kwargs["shell"] == "powershell"


# --------------------------------------------------------------------------- #
# _write_config / _restart_service
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_write_config_success(linux_node):
    executor = MagicMock()
    executor.execute_local.return_value = {"success": True}
    with patch("apps.node_mgmt.services.sidecar_config.Executor", return_value=executor):
        SidecarConfigService._write_config(linux_node, {"node_name": "x"})
    executor.execute_local.assert_called_once()


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
    assert "newname" in write_command
    assert "group:5" in write_command
    assert "group:6" in write_command
    assert "keepme" in write_command
    assert "group:1" not in write_command


@pytest.mark.django_db
def test_sync_node_properties_read_failure_raises(linux_node):
    executor = MagicMock()
    executor.execute_local.return_value = {"success": False, "stderr": "No such file"}
    with patch("apps.node_mgmt.services.sidecar_config.Executor", return_value=executor):
        with pytest.raises(ValueError):
            SidecarConfigService.sync_node_properties(linux_node, name="x")
