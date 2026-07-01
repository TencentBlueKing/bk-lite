"""补充 node_mgmt 真实行为测试：installer 命令构建、collector tag 归一/分组、
package 路径构建与架构解析、版本升级映射、NodeSerializer 序列化。

仅 mock 真实外部边界（requests/Executor RPC）。其余断言真实输出与 DB 副作用。
"""
import pytest
from unittest.mock import MagicMock

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.node_mgmt.constants.controller import ControllerConstants
from apps.node_mgmt.constants.node import NodeConstants
from apps.node_mgmt.models import CloudRegion, Collector, Node, NodeComponentVersion, PackageVersion
from apps.node_mgmt.models.sidecar import NodeOrganization
from apps.node_mgmt.serializers.node import NodeSerializer
from apps.node_mgmt.services.package import PackageService
from apps.node_mgmt.services.version_upgrade import VersionUpgradeService
from apps.node_mgmt.utils import collector_tags
from apps.node_mgmt.utils import installer as installer_utils


# --------------------------------------------------------------------------- #
# installer.get_install_command / get_uninstall_command
# --------------------------------------------------------------------------- #
def test_get_install_command_linux_renders_all_placeholders():
    command = installer_utils.get_install_command(
        os=NodeConstants.LINUX_OS,
        package_name="fusion-collectors",
        cloud_region_id=7,
        sidecar_token="tok-123",
        server_url="https://srv.example.com",
        groups="1,2",
        node_name="node-a",
        node_id="node-id-a",
    )

    # 真实命令尾部携带所有渲染后的参数，且无残留占位符
    assert command.endswith(
        "https://srv.example.com/api/v1/node_mgmt/open_api/node tok-123 7 1,2 node-a node-id-a"
    )
    assert "{server_token}" not in command
    assert "{node_id}" not in command
    assert command.startswith(ControllerConstants.RUN_COMMAND[NodeConstants.LINUX_OS][:10])


def test_get_uninstall_command_returns_os_specific_template():
    linux_cmd = installer_utils.get_uninstall_command(NodeConstants.LINUX_OS)
    assert linux_cmd == ControllerConstants.UNINSTALL_COMMAND[NodeConstants.LINUX_OS]

    # 未知操作系统返回 None（dict.get 行为）
    assert installer_utils.get_uninstall_command("solaris") is None


# --------------------------------------------------------------------------- #
# installer.get_manual_install_command（mock 外部 HTTP 边界 requests.post）
# --------------------------------------------------------------------------- #
def test_get_manual_install_command_requires_webhook_url():
    with pytest.raises(BaseAppException) as exc:
        installer_utils.get_manual_install_command(
            os=NodeConstants.WINDOWS_OS,
            package_id=1,
            cloud_region_id=1,
            sidecar_token="t",
            server_url="https://s",
            groups="1",
            node_name="n",
            node_id="nid",
            webhook_url="",
        )
    assert "Webhook API URL is required" in str(exc.value)


def test_get_manual_install_command_returns_yaml_and_builds_api_url(monkeypatch):
    captured = {}

    def fake_post(url, json, headers, timeout, verify):
        captured["url"] = url
        captured["json"] = json
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"yaml": "apiVersion: v1"}
        return response

    monkeypatch.setattr(installer_utils.requests, "post", fake_post)
    monkeypatch.setattr(installer_utils, "get_webhook_tls_verify", lambda: True)

    result = installer_utils.get_manual_install_command(
        os=NodeConstants.WINDOWS_OS,
        package_id=9,
        cloud_region_id=3,
        sidecar_token="tok",
        server_url="https://srv",
        groups="5",
        node_name="node-x",
        node_id="node-id-x",
        webhook_url="https://hook.example.com/",
    )

    assert result == "apiVersion: v1"
    # 末尾斜杠被去除后拼接 /infra/kubernetes
    assert captured["url"] == "https://hook.example.com/infra/kubernetes"
    # 入参契约：node_id/zone_id/group_id 正确映射
    assert captured["json"]["node_id"] == "node-id-x"
    assert captured["json"]["zone_id"] == 3
    assert captured["json"]["group_id"] == "5"
    assert captured["json"]["api_token"] == "tok"


def test_get_manual_install_command_raises_on_non_200(monkeypatch):
    def fake_post(url, json, headers, timeout, verify):
        response = MagicMock()
        response.status_code = 500
        response.text = "boom"
        return response

    monkeypatch.setattr(installer_utils.requests, "post", fake_post)
    monkeypatch.setattr(installer_utils, "get_webhook_tls_verify", lambda: False)

    with pytest.raises(BaseAppException) as exc:
        installer_utils.get_manual_install_command(
            os=NodeConstants.WINDOWS_OS,
            package_id=1,
            cloud_region_id=1,
            sidecar_token="t",
            server_url="https://s",
            groups="1",
            node_name="n",
            node_id="nid",
            webhook_url="https://hook",
        )
    assert "returned status 500" in str(exc.value)


def test_get_manual_install_command_raises_when_yaml_missing(monkeypatch):
    def fake_post(url, json, headers, timeout, verify):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"other": "x"}
        return response

    monkeypatch.setattr(installer_utils.requests, "post", fake_post)
    monkeypatch.setattr(installer_utils, "get_webhook_tls_verify", lambda: False)

    with pytest.raises(BaseAppException) as exc:
        installer_utils.get_manual_install_command(
            os=NodeConstants.WINDOWS_OS,
            package_id=1,
            cloud_region_id=1,
            sidecar_token="t",
            server_url="https://s",
            groups="1",
            node_name="n",
            node_id="nid",
            webhook_url="https://hook",
        )
    assert "missing 'yaml' field" in str(exc.value)


# --------------------------------------------------------------------------- #
# installer 执行包装：仅验证对 Executor 的入参契约（mock RPC 边界）
# --------------------------------------------------------------------------- #
def test_exec_command_to_remote_passes_ssh_arguments(monkeypatch):
    fake_executor = MagicMock()
    fake_executor.execute_ssh.return_value = "ok"
    monkeypatch.setattr(installer_utils, "Executor", lambda instance_id: fake_executor)

    result = installer_utils.exec_command_to_remote(
        "inst-1",
        "10.0.0.5",
        "root",
        "pwd",
        "ls -l",
        port=2222,
        private_key="key",
        passphrase="pp",
    )

    assert result == "ok"
    _, kwargs = fake_executor.execute_ssh.call_args
    args = fake_executor.execute_ssh.call_args.args
    assert args[0] == "ls -l"
    assert args[1] == "10.0.0.5"
    assert args[2] == "root"
    assert kwargs["password"] == "pwd"
    assert kwargs["port"] == 2222
    assert kwargs["private_key"] == "key"
    assert kwargs["passphrase"] == "pp"
    assert kwargs["fast_fail"] is True


def test_exec_command_to_local_uses_executor(monkeypatch):
    fake_executor = MagicMock()
    fake_executor.execute_local.return_value = "result"
    monkeypatch.setattr(installer_utils, "Executor", lambda instance_id: fake_executor)

    result = installer_utils.exec_command_to_local("inst-9", "uptime")

    assert result == "result"
    args = fake_executor.execute_local.call_args.args
    assert args[0] == "uptime"


# --------------------------------------------------------------------------- #
# collector_tags.normalize_collector_tags / split_collector_tags
# --------------------------------------------------------------------------- #
def test_normalize_collector_tags_dedups_and_appends_os_and_arch():
    result = collector_tags.normalize_collector_tags(
        tags=["telegraf", " telegraf ", "", "custom"],
        operating_system="Linux",
        cpu_architecture="aarch64",
    )

    # 去重 + 去空白；显式 tag 顺序保持，随后追加归一化后的 os 与 arch
    assert result == ["telegraf", "custom", NodeConstants.LINUX_OS, NodeConstants.ARM64_ARCH]


def test_normalize_collector_tags_skips_unknown_os_and_unknown_arch():
    result = collector_tags.normalize_collector_tags(
        tags=None,
        operating_system="solaris",
        cpu_architecture="sparc",
    )
    # 未知 os 不追加；未知架构归一化为 UNKNOWN 也不追加
    assert result == []


def test_normalize_collector_tags_does_not_duplicate_existing_os_tag():
    result = collector_tags.normalize_collector_tags(
        tags=[NodeConstants.LINUX_OS],
        operating_system="linux",
        cpu_architecture="x86_64",
    )
    assert result == [NodeConstants.LINUX_OS, NodeConstants.X86_64_ARCH]


def test_split_collector_tags_groups_by_category():
    grouped = collector_tags.split_collector_tags(
        [NodeConstants.LINUX_OS, NodeConstants.X86_64_ARCH, "", "  ", "totally-unknown-tag"]
    )
    assert grouped["os"] == [NodeConstants.LINUX_OS]
    assert grouped["architecture"] == [NodeConstants.X86_64_ARCH]
    assert grouped["other"] == ["totally-unknown-tag"]
    # 空白/空字符串被跳过
    assert all(
        "" not in bucket and "  " not in bucket for bucket in grouped.values()
    )


# --------------------------------------------------------------------------- #
# PackageService 路径构建与上传架构归一化（纯函数）
# --------------------------------------------------------------------------- #
class _PkgStub:
    def __init__(self, os, arch, object_name, version, name):
        self.os = os
        self.cpu_architecture = arch
        self.object = object_name
        self.version = version
        self.name = name


def test_build_file_path_includes_architecture_segment():
    pkg = _PkgStub("linux", "arm64", "Controller", "1.0.0", "fc.tar.gz")
    assert PackageService.build_file_path(pkg) == "linux/arm64/Controller/1.0.0/fc.tar.gz"


def test_build_file_path_falls_back_to_generic_for_empty_arch():
    pkg = _PkgStub("linux", "", "Controller", "1.0.0", "fc.tar.gz")
    assert PackageService.build_file_path(pkg) == "linux/generic/Controller/1.0.0/fc.tar.gz"


def test_build_legacy_file_path_omits_architecture():
    pkg = _PkgStub("linux", "x86_64", "Controller", "2.0.0", "fc.tar.gz")
    assert PackageService.build_legacy_file_path(pkg) == "linux/Controller/2.0.0/fc.tar.gz"


def test_build_candidate_file_paths_dedups_when_paths_collide():
    # 空架构时 file_path 用 generic，legacy 无架构段，二者不同 -> 两条候选
    pkg = _PkgStub("linux", "", "Controller", "1.0.0", "fc.tar.gz")
    candidates = PackageService.build_candidate_file_paths(pkg)
    assert candidates == [
        "linux/generic/Controller/1.0.0/fc.tar.gz",
        "linux/Controller/1.0.0/fc.tar.gz",
    ]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("aarch64", NodeConstants.ARM64_ARCH),
        ("", "x86_64"),
        (None, "x86_64"),
        ("sparc", "x86_64"),
    ],
)
def test_normalize_upload_cpu_architecture_defaults_to_x86(raw, expected):
    assert PackageService.normalize_upload_cpu_architecture(raw) == expected


# --------------------------------------------------------------------------- #
# PackageService.resolve_collector_by_architecture（DB 真实副作用）
# --------------------------------------------------------------------------- #
def _make_collector(collector_id, arch):
    return Collector.objects.create(
        id=collector_id,
        name="Telegraf",
        service_type="exec",
        node_operating_system=NodeConstants.LINUX_OS,
        cpu_architecture=arch,
        executable_path="/opt/telegraf",
        execute_parameters="--config %s",
        introduction="",
        icon="telegraf",
        default_config={},
        tags=[],
        package_name="telegraf",
        created_by="tester",
        updated_by="tester",
    )


@pytest.mark.django_db
def test_resolve_collector_by_architecture_prefers_exact_arch_match():
    _make_collector("tg_x86", NodeConstants.X86_64_ARCH)
    arm = _make_collector("tg_arm", NodeConstants.ARM64_ARCH)

    resolved = PackageService.resolve_collector_by_architecture(
        NodeConstants.LINUX_OS, "Telegraf", "aarch64"
    )
    assert resolved is not None
    assert resolved.id == arm.id


@pytest.mark.django_db
def test_resolve_collector_by_architecture_x86_falls_back_to_legacy_x86_record():
    legacy = _make_collector("tg_x86_only", NodeConstants.X86_64_ARCH)

    resolved = PackageService.resolve_collector_by_architecture(
        NodeConstants.LINUX_OS, "Telegraf", "x86_64"
    )
    assert resolved is not None
    assert resolved.id == legacy.id


# --------------------------------------------------------------------------- #
# VersionUpgradeService.get_latest_versions_map（DB 真实副作用 + 版本排序）
# --------------------------------------------------------------------------- #
def _make_pkg(arch, version, os_type="linux", obj="Controller"):
    return PackageVersion.objects.create(
        type="controller",
        os=os_type,
        cpu_architecture=arch,
        object=obj,
        version=version,
        name=f"fc-{version}-{arch or 'generic'}.tar.gz",
        created_by="tester",
        updated_by="tester",
    )


@pytest.mark.django_db
def test_get_latest_versions_map_picks_highest_version_per_arch():
    _make_pkg(NodeConstants.X86_64_ARCH, "1.0.0")
    _make_pkg(NodeConstants.X86_64_ARCH, "1.10.0")
    _make_pkg(NodeConstants.X86_64_ARCH, "1.2.0")
    _make_pkg(NodeConstants.ARM64_ARCH, "0.9.0")

    result = VersionUpgradeService.get_latest_versions_map(component_type="controller")

    # 1.10.0 > 1.2.0 > 1.0.0 的语义化排序，而非字典序
    assert result["linux"]["Controller"][NodeConstants.X86_64_ARCH] == "1.10.0"
    assert result["linux"]["Controller"][NodeConstants.ARM64_ARCH] == "0.9.0"


@pytest.mark.django_db
def test_get_latest_versions_map_groups_empty_arch_under_empty_key():
    _make_pkg("", "3.0.0")

    result = VersionUpgradeService.get_latest_versions_map(component_type="controller")

    assert result["linux"]["Controller"][""] == "3.0.0"


@pytest.mark.django_db
def test_get_latest_versions_map_empty_when_no_packages():
    assert VersionUpgradeService.get_latest_versions_map(component_type="controller") == {}


# --------------------------------------------------------------------------- #
# NodeSerializer.get_organization / get_versions（DB 真实序列化）
# --------------------------------------------------------------------------- #
def _make_node_with_org(node_id, region, org=1):
    node = Node.objects.create(
        id=node_id,
        name=node_id,
        ip="10.0.0.50",
        operating_system="linux",
        cpu_architecture=NodeConstants.X86_64_ARCH,
        collector_configuration_directory="/etc/collector",
        cloud_region=region,
        install_method="manual",
        created_by="tester",
        updated_by="tester",
        domain="domain.com",
        updated_by_domain="domain.com",
    )
    NodeOrganization.objects.create(
        node=node,
        organization=org,
        created_by="tester",
        updated_by="tester",
        domain="domain.com",
        updated_by_domain="domain.com",
    )
    return node


@pytest.mark.django_db
def test_node_serializer_get_organization_returns_org_ids():
    region = CloudRegion.objects.create(
        name="ser-region", created_by="tester", updated_by="tester",
        domain="domain.com", updated_by_domain="domain.com",
    )
    node = _make_node_with_org("ser-node-1", region, org=7)

    data = NodeSerializer(node).data

    assert data["organization"] == [7]
    assert data["node_type"] == node.node_type


@pytest.mark.django_db
def test_node_serializer_get_versions_only_controller_with_unknown_fallback():
    region = CloudRegion.objects.create(
        name="ver-region", created_by="tester", updated_by="tester",
        domain="domain.com", updated_by_domain="domain.com",
    )
    node = _make_node_with_org("ver-node-1", region)

    NodeComponentVersion.objects.create(
        node=node,
        component_type="controller",
        component_id="5",
        version="1.0.0",
        latest_version="",  # 空 -> 序列化回退为 "unknown"
        upgradeable=False,
        message="ok",
        created_by="tester",
        updated_by="tester",
    )
    NodeComponentVersion.objects.create(
        node=node,
        component_type="collector",  # 非 controller，应被过滤
        component_id="9",
        version="2.0.0",
        latest_version="2.1.0",
        upgradeable=True,
        message="other",
        created_by="tester",
        updated_by="tester",
    )

    data = NodeSerializer(node).data

    assert len(data["versions"]) == 1
    version = data["versions"][0]
    assert version["component_type"] == "controller"
    assert version["component_id"] == "5"
    assert version["latest_version"] == "unknown"
    assert version["upgradeable"] is False
