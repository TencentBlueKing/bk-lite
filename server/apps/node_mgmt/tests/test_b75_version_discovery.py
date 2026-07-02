"""version_discovery 任务真实行为测试。

仅 mock Executor RPC 边界。断言真实 DB 副作用与升级计算。
"""
import pytest
from unittest.mock import MagicMock, patch

from apps.node_mgmt.constants.node import NodeConstants
from apps.node_mgmt.models import Controller, Node, NodeComponentVersion, PackageVersion
from apps.node_mgmt.models.cloud_region import CloudRegion
from apps.node_mgmt.services.version_upgrade import VersionUpgradeService
from apps.node_mgmt.tasks import version_discovery as vd


# --------------------------------------------------------------------------- #
# VersionUpgradeService.get_latest_versions_map
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_get_latest_versions_map_picks_highest():
    PackageVersion.objects.create(
        type="controller", os="linux", cpu_architecture="x86_64",
        object="Controller", version="1.0.0", name="c1.tar.gz",
    )
    PackageVersion.objects.create(
        type="controller", os="linux", cpu_architecture="x86_64",
        object="Controller", version="2.5.0", name="c2.tar.gz",
    )
    result = VersionUpgradeService.get_latest_versions_map("controller")
    assert result["linux"]["Controller"]["x86_64"] == "2.5.0"


def test_get_latest_versions_map_exception_returns_empty():
    with patch(
        "apps.node_mgmt.services.version_upgrade.PackageVersion.objects.filter",
        side_effect=RuntimeError("db down"),
    ):
        assert VersionUpgradeService.get_latest_versions_map("controller") == {}


@pytest.fixture
def node(db):
    region = CloudRegion.objects.create(name="cr-vd")
    return Node.objects.create(
        id="node-vd",
        name="vd-node",
        ip="10.0.0.5",
        operating_system="linux",
        cpu_architecture="x86_64",
        collector_configuration_directory="/etc",
        cloud_region=region,
    )


def _discover_controller_version(node, latest_versions_map=None):
    all_controllers = list(Controller.objects.filter(name="Controller"))
    controllers_map = {(c.os, c.cpu_architecture): c for c in all_controllers}
    return vd._discover_controller_version(
        node,
        latest_versions_map or {},
        controllers_map,
        all_controllers,
    )


# --------------------------------------------------------------------------- #
# _calculate_upgrade_info
# --------------------------------------------------------------------------- #
def test_calculate_upgrade_info_normal_upgradeable():
    versions_map = {"linux": {"Controller": {"x86_64": "2.0.0"}}}
    latest, upgradeable = vd._calculate_upgrade_info(
        "1.0.0", "Controller", "linux", "x86_64", versions_map
    )
    assert latest == "2.0.0"
    assert upgradeable is True


def test_calculate_upgrade_info_current_latest_not_upgradeable():
    latest, upgradeable = vd._calculate_upgrade_info(
        "latest", "Controller", "linux", "x86_64", {}
    )
    assert upgradeable is False


def test_calculate_upgrade_info_current_unknown_not_upgradeable():
    latest, upgradeable = vd._calculate_upgrade_info(
        "unknown", "Controller", "linux", "x86_64", {}
    )
    assert upgradeable is False


def test_calculate_upgrade_info_latest_tag_means_upgradeable():
    versions_map = {"linux": {"Controller": {"x86_64": "latest-build"}}}
    latest, upgradeable = vd._calculate_upgrade_info(
        "1.0.0", "Controller", "linux", "x86_64", versions_map
    )
    assert upgradeable is True


def test_calculate_upgrade_info_no_latest_uses_current():
    latest, upgradeable = vd._calculate_upgrade_info(
        "1.0.0", "Controller", "linux", "x86_64", {}
    )
    assert latest == "1.0.0"
    assert upgradeable is False


def test_calculate_upgrade_info_arch_fallback_to_empty():
    versions_map = {"linux": {"Controller": {"": "3.0.0"}}}
    latest, upgradeable = vd._calculate_upgrade_info(
        "1.0.0", "Controller", "linux", "arm64", versions_map
    )
    assert latest == "3.0.0"
    assert upgradeable is True


# --------------------------------------------------------------------------- #
# _save_controller_version_success / failure
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_save_success_creates_record(node):
    record = vd._save_controller_version_success(
        node=node, component_id="c1", version="1.0.0", latest_version="2.0.0", upgradeable=True
    )
    assert record.pk is not None
    assert record.version == "1.0.0"
    assert record.upgradeable is True
    assert record.message == "版本获取成功"


@pytest.mark.django_db
def test_save_success_updates_existing(node):
    NodeComponentVersion.objects.create(
        node=node, component_type="controller", component_id="c1", version="0.0.1"
    )
    record = vd._save_controller_version_success(
        node=node, component_id="c1", version="9.9.9", latest_version="9.9.9", upgradeable=False
    )
    assert record.version == "9.9.9"
    assert NodeComponentVersion.objects.filter(node=node, component_type="controller").count() == 1


@pytest.mark.django_db
def test_save_failure_creates_unknown_record(node):
    record = vd._save_controller_version_failure(node=node, message="boom")
    assert record.version == "unknown"
    assert record.component_id == "unknown"
    assert record.message == "boom"


@pytest.mark.django_db
def test_save_failure_updates_existing(node):
    NodeComponentVersion.objects.create(
        node=node, component_type="controller", component_id="c1", version="1.0.0"
    )
    record = vd._save_controller_version_failure(node=node, component_id="c1", message="failed")
    assert record.message == "failed"
    assert record.component_id == "c1"


# --------------------------------------------------------------------------- #
# _discover_controller_version
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_discover_no_controller_saves_failure(node):
    # 没有任何 Controller 配置
    _discover_controller_version(node)
    record = NodeComponentVersion.objects.get(node=node, component_type="controller")
    assert "未找到操作系统" in record.message


@pytest.mark.django_db
def test_discover_controller_no_version_command_saves_failure(node):
    Controller.objects.create(os="linux", cpu_architecture="x86_64", name="Controller", version_command="")
    _discover_controller_version(node)
    record = NodeComponentVersion.objects.get(node=node, component_type="controller")
    assert "未配置版本命令" in record.message


@pytest.mark.django_db
def test_discover_controller_success_with_executor(node):
    ctrl = Controller.objects.create(
        os="linux", cpu_architecture="x86_64", name="Controller", version_command="ctl --version"
    )
    versions_map = {"linux": {"Controller": {"x86_64": "2.0.0"}}}
    executor = MagicMock()
    executor.execute_local.return_value = "1.0.0\n"
    with patch("apps.node_mgmt.tasks.version_discovery.Executor", return_value=executor):
        _discover_controller_version(node, versions_map)

    record = NodeComponentVersion.objects.get(node=node, component_id=str(ctrl.id))
    assert record.version == "1.0.0"
    assert record.latest_version == "2.0.0"
    assert record.upgradeable is True


@pytest.mark.django_db
def test_discover_controller_invalid_version_output(node):
    ctrl = Controller.objects.create(
        os="linux", cpu_architecture="x86_64", name="Controller", version_command="ctl --version"
    )
    executor = MagicMock()
    executor.execute_local.return_value = "garbage output"
    with patch("apps.node_mgmt.tasks.version_discovery.Executor", return_value=executor):
        _discover_controller_version(node)
    record = NodeComponentVersion.objects.get(node=node, component_id=str(ctrl.id))
    assert "不是有效版本号" in record.message


@pytest.mark.django_db
def test_discover_controller_empty_output(node):
    ctrl = Controller.objects.create(
        os="linux", cpu_architecture="x86_64", name="Controller", version_command="ctl --version"
    )
    executor = MagicMock()
    executor.execute_local.return_value = "   "
    with patch("apps.node_mgmt.tasks.version_discovery.Executor", return_value=executor):
        _discover_controller_version(node)
    record = NodeComponentVersion.objects.get(node=node, component_id=str(ctrl.id))
    assert "空结果" in record.message


@pytest.mark.django_db
def test_discover_controller_executor_exception(node):
    ctrl = Controller.objects.create(
        os="linux", cpu_architecture="x86_64", name="Controller", version_command="ctl --version"
    )
    with patch(
        "apps.node_mgmt.tasks.version_discovery.Executor",
        side_effect=RuntimeError("rpc down"),
    ):
        _discover_controller_version(node)
    record = NodeComponentVersion.objects.get(node=node, component_id=str(ctrl.id))
    assert "异常" in record.message


# --------------------------------------------------------------------------- #
# discover_node_versions
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_discover_node_versions_counts(node):
    Controller.objects.create(
        os="linux", cpu_architecture="x86_64", name="Controller", version_command="ctl --version"
    )
    executor = MagicMock()
    executor.execute_local.return_value = "1.0.0"
    with patch("apps.node_mgmt.tasks.version_discovery.Executor", return_value=executor):
        result = vd.discover_node_versions()
    assert result["total"] == 1
    assert result["success_count"] == 1
    assert result["failed_count"] == 0
