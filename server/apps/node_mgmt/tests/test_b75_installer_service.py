"""InstallerService 真实行为测试：架构校验、包解析、任务创建、命令生成、状态查询。

仅 mock S3 下载与 InstallTokenService.generate_install_token 边界。
断言真实 DB 副作用与命令字符串结构。
"""

import os
import shlex
import subprocess
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.node_mgmt.constants.node import NodeConstants
from apps.node_mgmt.models import Node, NodeOrganization, PackageVersion
from apps.node_mgmt.models.cloud_region import CloudRegion, SidecarEnv
from apps.node_mgmt.models.installer import CollectorTask, CollectorTaskNode, ControllerTask, ControllerTaskNode
from apps.node_mgmt.services.installer import InstallerService


# --------------------------------------------------------------------------- #
# normalize_required_cpu_architecture
# --------------------------------------------------------------------------- #
def test_normalize_required_arch_valid_linux():
    assert InstallerService.normalize_required_cpu_architecture("linux", "amd64") == NodeConstants.X86_64_ARCH


def test_normalize_required_arch_missing_raises():
    with pytest.raises(BaseAppException) as exc:
        InstallerService.normalize_required_cpu_architecture("linux", "")
    assert "Missing or unsupported" in str(exc.value)


def test_normalize_required_arch_windows_arm_raises():
    with pytest.raises(BaseAppException) as exc:
        InstallerService.normalize_required_cpu_architecture("windows", "arm64")
    assert "Unsupported CPU architecture" in str(exc.value)


# --------------------------------------------------------------------------- #
# resolve_package_by_architecture
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_resolve_package_not_found_raises():
    with pytest.raises(BaseAppException) as exc:
        InstallerService.resolve_package_by_architecture(999999, "x86_64")
    assert "Package version not found" in str(exc.value)


@pytest.mark.django_db
def test_resolve_package_matched_returns_obj():
    pkg = PackageVersion.objects.create(
        type="controller",
        os="linux",
        cpu_architecture="x86_64",
        object="Controller",
        version="1.0.0",
        name="ctl.tar.gz",
    )
    resolved = InstallerService.resolve_package_by_architecture(pkg.id, "x86_64")
    assert resolved.id == pkg.id


@pytest.mark.django_db
def test_resolve_package_legacy_x86_controller():
    pkg = PackageVersion.objects.create(
        type="controller",
        os="linux",
        cpu_architecture="",
        object="Controller",
        version="1.0.0",
        name="ctl.tar.gz",
    )
    resolved = InstallerService.resolve_package_by_architecture(pkg.id, "x86_64")
    assert resolved.id == pkg.id


# --------------------------------------------------------------------------- #
# installer_metadata / installer_manifest
# --------------------------------------------------------------------------- #
def test_installer_metadata_unsupported_os_raises():
    with pytest.raises(BaseAppException) as exc:
        InstallerService.installer_metadata("solaris")
    assert "Unsupported operating system" in str(exc.value)


def test_installer_metadata_returns_artifact():
    meta = InstallerService.installer_metadata("linux", "x86_64")
    assert meta["os"] == "linux"
    assert meta["cpu_architecture"] == "x86_64"
    assert "object_key" in meta


def test_installer_manifest_structure():
    manifest = InstallerService.installer_manifest()
    assert "default_version" in manifest
    assert "windows" in manifest["artifacts"]
    assert "arm64" in manifest["artifacts"]["linux"]


# --------------------------------------------------------------------------- #
# install_controller / uninstall_controller
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_install_controller_creates_task_and_nodes():
    region = CloudRegion.objects.create(name="cr-install-ctrl")
    nodes = [
        {
            "ip": "10.0.0.1",
            "node_id": "node-ctrl-install",
            "node_name": "n1",
            "os": "linux",
            "cpu_architecture": "x86_64",
            "organizations": [1],
            "port": 22,
            "username": "root",
            "password": "secret",
            "private_key": "",
            "passphrase": "",
        }
    ]
    task_id = InstallerService.install_controller(
        region.id,
        "work-1",
        5,
        nodes,
        "x86_64",
        created_by="operator",
        domain="example.com",
    )
    task = ControllerTask.objects.get(id=task_id)
    assert task.type == "install"
    assert task.created_by == "operator"
    assert task.domain == "example.com"
    node = ControllerTaskNode.objects.get(task=task)
    assert node.node_id == "node-ctrl-install"
    assert node.ip == "10.0.0.1"
    # 密码被加密（不等于明文）
    assert node.password != "secret"
    assert node.password


@pytest.mark.django_db
def test_uninstall_controller_creates_task_and_nodes():
    region = CloudRegion.objects.create(name="cr-uninstall")
    nodes = [
        {
            "ip": "10.0.0.2",
            "node_id": "node-ctrl-uninstall",
            "os": "linux",
            "port": 22,
            "username": "root",
            "password": "",
            "private_key": "key",
            "passphrase": "",
        }
    ]
    task_id = InstallerService.uninstall_controller(
        region.id,
        "work-2",
        nodes,
        created_by="operator",
        domain="example.com",
    )
    task = ControllerTask.objects.get(id=task_id)
    assert task.type == "uninstall"
    assert task.created_by == "operator"
    assert task.domain == "example.com"
    node = ControllerTaskNode.objects.get(task=task)
    assert node.node_id == "node-ctrl-uninstall"
    assert node.private_key != "key"


# --------------------------------------------------------------------------- #
# install_collector / install_collector_nodes
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_install_collector_creates_task_and_nodes():
    region = CloudRegion.objects.create(name="cr-install-col")
    node = Node.objects.create(
        id="n-col",
        name="n",
        ip="10.0.0.3",
        operating_system="linux",
        collector_configuration_directory="/etc",
        cloud_region=region,
    )
    task_id = InstallerService.install_collector(7, [node.id])
    task = CollectorTask.objects.get(id=task_id)
    assert task.type == "install"
    assert CollectorTaskNode.objects.filter(task=task, node_id=node.id).exists()


@pytest.mark.django_db
def test_install_collector_nodes_returns_info():
    region = CloudRegion.objects.create(name="cr-col-nodes")
    node = Node.objects.create(
        id="n-col-2",
        name="n",
        ip="10.0.0.4",
        operating_system="linux",
        collector_configuration_directory="/etc",
        cloud_region=region,
    )
    task = CollectorTask.objects.create(type="install", status="waiting", package_version_id=1)
    CollectorTaskNode.objects.create(task=task, node_id=node.id, status="waiting")
    result = InstallerService.install_collector_nodes(task.id)
    assert len(result) == 1
    assert result[0]["node_id"] == node.id
    assert result[0]["ip"] == "10.0.0.4"


@pytest.mark.django_db
def test_install_controller_nodes_returns_info():
    region = CloudRegion.objects.create(name="cr-ctrl-nodes")
    task = ControllerTask.objects.create(cloud_region=region, type="install", status="waiting", package_version_id=1)
    ControllerTaskNode.objects.create(
        task=task,
        ip="10.0.0.5",
        os="linux",
        port=22,
        username="root",
        password="x",
        node_name="n",
        organizations=[1],
        status="waiting",
    )
    result = InstallerService.install_controller_nodes(task.id)
    assert len(result) == 1
    assert result[0]["ip"] == "10.0.0.5"
    assert result[0]["status"] == "waiting"


@pytest.mark.django_db
def test_install_controller_nodes_filters_by_authorized_nodes():
    region = CloudRegion.objects.create(name="cr-ctrl-auth")
    allowed_node = Node.objects.create(
        id="n-ctrl-allowed",
        name="allowed",
        ip="10.0.0.10",
        operating_system="linux",
        collector_configuration_directory="/etc",
        cloud_region=region,
    )
    denied_node = Node.objects.create(
        id="n-ctrl-denied",
        name="denied",
        ip="10.0.0.11",
        operating_system="linux",
        collector_configuration_directory="/etc",
        cloud_region=region,
    )
    task = ControllerTask.objects.create(cloud_region=region, type="install", status="waiting", package_version_id=1)
    ControllerTaskNode.objects.create(
        task=task,
        node_id=allowed_node.id,
        ip=allowed_node.ip,
        os="linux",
        port=22,
        username="root",
        password="x",
        node_name="allowed",
        organizations=[1],
        status="waiting",
    )
    ControllerTaskNode.objects.create(
        task=task,
        node_id=denied_node.id,
        ip=denied_node.ip,
        os="linux",
        port=22,
        username="root",
        password="x",
        node_name="denied",
        organizations=[2],
        status="waiting",
    )

    result = InstallerService.install_controller_nodes(
        task.id,
        authorized_nodes=Node.objects.filter(id=allowed_node.id),
    )

    assert [item["node_id"] for item in result] == [allowed_node.id]
    assert [item["ip"] for item in result] == ["10.0.0.10"]


@pytest.mark.django_db
def test_install_controller_nodes_filters_legacy_rows_by_scope_snapshot():
    region = CloudRegion.objects.create(name="cr-ctrl-legacy")
    node = Node.objects.create(
        id="n-ctrl-legacy",
        name="legacy",
        ip="10.0.0.12",
        operating_system="linux",
        collector_configuration_directory="/etc",
        cloud_region=region,
    )
    NodeOrganization.objects.create(node=node, organization=1)
    task = ControllerTask.objects.create(
        cloud_region=region,
        type="install",
        status="waiting",
        package_version_id=1,
        created_by="owner",
    )
    ControllerTaskNode.objects.create(
        task=task,
        ip=node.ip,
        os="linux",
        port=22,
        username="root",
        password="x",
        node_name="legacy",
        organizations=[1],
        status="waiting",
    )

    current_scope = InstallerService.install_controller_nodes(
        task.id,
        authorized_nodes=Node.objects.none(),
        scope=SimpleNamespace(data_team_ids=frozenset({1})),
    )
    sibling_scope = InstallerService.install_controller_nodes(
        task.id,
        authorized_nodes=Node.objects.none(),
        scope=SimpleNamespace(data_team_ids=frozenset({2})),
    )

    assert [item["ip"] for item in current_scope] == [node.ip]
    assert sibling_scope == []


# --------------------------------------------------------------------------- #
# get_manual_install_status
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_get_manual_install_status_mixed():
    region = CloudRegion.objects.create(name="cr-manual")
    Node.objects.create(
        id="installed-node",
        name="n",
        ip="10.0.0.6",
        operating_system="linux",
        collector_configuration_directory="/etc",
        cloud_region=region,
    )
    result = InstallerService.get_manual_install_status(["installed-node", "missing-node"])
    statuses = {item["node_id"]: item["status"] for item in result}
    assert statuses["installed-node"] == "installed"
    assert statuses["missing-node"] == "waiting"


# --------------------------------------------------------------------------- #
# get_install_command
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_get_install_command_missing_server_url_raises():
    region = CloudRegion.objects.create(name="cr-cmd-nourl")
    with pytest.raises(BaseAppException) as exc:
        InstallerService.get_install_command(
            user="u",
            ip="1.1.1.1",
            node_id="nid",
            os="linux",
            package_id=1,
            cloud_region_id=region.id,
            organizations=[1],
            node_name="n",
            cpu_architecture="x86_64",
        )
    assert "Missing NODE_SERVER_URL" in str(exc.value)


@pytest.mark.django_db
def test_get_install_command_windows_returns_session_url():
    region = CloudRegion.objects.create(name="cr-cmd-win")
    SidecarEnv.objects.create(
        cloud_region=region,
        key=NodeConstants.SERVER_URL_KEY,
        value="https://srv.local/",
        type="str",
    )
    with patch(
        "apps.node_mgmt.services.installer.InstallTokenService.generate_install_token",
        return_value="tok-abc",
    ):
        cmd = InstallerService.get_install_command(
            user="u",
            ip="1.1.1.1",
            node_id="nid",
            os="windows",
            package_id=1,
            cloud_region_id=region.id,
            organizations=[1],
            node_name="n",
            cpu_architecture="x86_64",
        )
    assert cmd == "https://srv.local/api/v1/node_mgmt/open_api/installer/session?token=tok-abc"


@pytest.mark.django_db
def test_get_install_command_linux_returns_bootstrap():
    region = CloudRegion.objects.create(name="cr-cmd-linux")
    SidecarEnv.objects.create(
        cloud_region=region,
        key=NodeConstants.SERVER_URL_KEY,
        value="https://srv.local",
        type="str",
    )
    session_cfg = {
        "installer": {"filename": "installer.bin"},
        "install_dir": "/opt/fusion",
        "server_url": "https://srv.local/api/v1/node_mgmt/open_api/node",
    }
    with (
        patch(
            "apps.node_mgmt.services.installer.InstallTokenService.generate_install_token",
            return_value="tok-xyz",
        ),
        patch(
            "apps.node_mgmt.services.installer.InstallerSessionService.build_session_config",
            return_value=session_cfg,
        ),
    ):
        cmd = InstallerService.get_install_command(
            user="u",
            ip="1.1.1.1",
            node_id="nid",
            os="linux",
            package_id=1,
            cloud_region_id=region.id,
            organizations=[1],
            node_name="n",
            cpu_architecture="x86_64",
        )
    assert "linux_bootstrap?token=tok-xyz" in cmd
    assert "curl" in cmd


# --------------------------------------------------------------------------- #
# get_linux_bootstrap_command
# --------------------------------------------------------------------------- #
_SESSION_CFG = {
    "installer": {"filename": "installer.bin"},
    "install_dir": "/opt/fusion",
    "server_url": "https://srv.local/api/v1/node_mgmt/open_api/node",
}


def _write_executable(path, content):
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _prepare_bootstrap_shell_test(tmp_path, shell_name, curl_exit_code=0, uid=0):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    bootstrap_temp = tmp_path / "bootstrap.sh"
    runner_log = tmp_path / "runner.log"
    bootstrap_log = tmp_path / "bootstrap.log"
    sudo_log = tmp_path / "sudo.log"

    _write_executable(bin_dir / "id", f"#!/bin/sh\nprintf '{uid}\\n'\n")
    _write_executable(
        bin_dir / "mktemp",
        '#!/bin/sh\n: > "$BOOTSTRAP_TEMP"\nprintf \'%s\\n\' "$BOOTSTRAP_TEMP"\n',
    )
    _write_executable(bin_dir / "rm", '#!/bin/sh\nexec /bin/rm "$@"\n')
    _write_executable(
        bin_dir / "sudo",
        '#!/bin/sh\nprintf "%s\\n" "$*" >> "$SUDO_LOG"\nif [ "$1" = "-n" ]; then shift; fi\nexec "$@"\n',
    )
    if curl_exit_code:
        curl_script = f"#!/bin/sh\nexit {curl_exit_code}\n"
    else:
        curl_script = """#!/bin/sh
output=''
while [ "$#" -gt 0 ]; do
  if [ "$1" = "-o" ]; then
    output="$2"
    shift 2
  else
    shift
  fi
done
printf '%s\n' '#!/bin/sh' 'printf "%s" "${SELECTED_SHELL:-bash}" > "$RUNNER_LOG"' 'printf ran > "$BOOTSTRAP_LOG"' > "$output"
"""
    _write_executable(bin_dir / "curl", curl_script)
    if shell_name == "bash":
        (bin_dir / shell_name).symlink_to("/bin/bash")
    else:
        _write_executable(
            bin_dir / shell_name,
            '#!/bin/sh\nSELECTED_SHELL=sh exec /bin/sh "$@"\n',
        )

    env = os.environ.copy()
    env.update(
        {
            "PATH": str(bin_dir),
            "BOOTSTRAP_TEMP": str(bootstrap_temp),
            "RUNNER_LOG": str(runner_log),
            "BOOTSTRAP_LOG": str(bootstrap_log),
            "SUDO_LOG": str(sudo_log),
        }
    )
    return env, bootstrap_temp, runner_log, bootstrap_log


@pytest.mark.django_db
def test_get_linux_bootstrap_command_manual_mode():
    with patch(
        "apps.node_mgmt.services.installer.InstallerSessionService.build_session_config",
        return_value=_SESSION_CFG,
    ):
        cmd = InstallerService.get_linux_bootstrap_command("tok", install_mode="manual")
    assert "sh -lc" not in cmd
    assert "bash -lc" not in cmd
    assert "command -v sh" in cmd
    assert "command -v bash" in cmd
    assert "curl -fsSLk" in cmd
    assert '-o "$bootstrap_file"' in cmd
    assert "| bash" not in cmd
    assert "| sh" not in cmd
    assert 'sudo "$bootstrap_shell" "$bootstrap_file"' in cmd
    assert "linux_bootstrap?token=tok" in cmd


@pytest.mark.django_db
def test_get_linux_bootstrap_command_auto_mode():
    with patch(
        "apps.node_mgmt.services.installer.InstallerSessionService.build_session_config",
        return_value=_SESSION_CFG,
    ):
        cmd = InstallerService.get_linux_bootstrap_command("tok", install_mode="auto")
    assert "sh -lc" not in cmd
    assert "bash -lc" not in cmd
    assert "command -v sh" in cmd
    assert "command -v bash" in cmd
    assert "curl -fsSLk" in cmd
    assert "| bash" not in cmd
    assert "| sh" not in cmd
    assert 'sudo -n "$bootstrap_shell" "$bootstrap_file"' in cmd
    assert 'sudo -n "$bootstrap_shell" -c true' in cmd
    assert "sudo -n true" not in cmd
    assert "passwordless sudo" in cmd


@pytest.mark.django_db
def test_get_linux_bootstrap_command_shell_quotes_bootstrap_url():
    session_cfg = {
        "installer": {"filename": "installer.bin"},
        "install_dir": "/opt/fusion",
        "server_url": "https://srv.local/path with space/it's/api/v1/node_mgmt/open_api/node",
    }
    with patch(
        "apps.node_mgmt.services.installer.InstallerSessionService.build_session_config",
        return_value=session_cfg,
    ):
        cmd = InstallerService.get_linux_bootstrap_command("tok", install_mode="auto")

    expected_url = "https://srv.local/path with space/it's/api/v1/node_mgmt/open_api/installer/linux_bootstrap?token=tok"
    assert shlex.quote(expected_url) in cmd


@pytest.mark.django_db
@pytest.mark.parametrize("shell_name", ["sh", "bash"])
def test_get_linux_bootstrap_command_runs_with_only_one_supported_shell(tmp_path, shell_name):
    env, bootstrap_temp, runner_log, bootstrap_log = _prepare_bootstrap_shell_test(tmp_path, shell_name)
    with patch(
        "apps.node_mgmt.services.installer.InstallerSessionService.build_session_config",
        return_value=_SESSION_CFG,
    ):
        cmd = InstallerService.get_linux_bootstrap_command("tok", install_mode="auto")

    result = subprocess.run(["/bin/sh", "-c", cmd], env=env, text=True, capture_output=True, check=False)

    assert result.returncode == 0, result.stderr
    assert runner_log.read_text(encoding="utf-8") == shell_name
    assert bootstrap_log.read_text(encoding="utf-8") == "ran"
    assert not bootstrap_temp.exists()
    assert not (tmp_path / "sudo.log").exists()


@pytest.mark.django_db
def test_get_linux_bootstrap_command_prefers_sh_when_sh_and_bash_are_available(tmp_path):
    env, _, runner_log, _ = _prepare_bootstrap_shell_test(tmp_path, "sh")
    (tmp_path / "bin" / "bash").symlink_to("/bin/bash")
    with patch(
        "apps.node_mgmt.services.installer.InstallerSessionService.build_session_config",
        return_value=_SESSION_CFG,
    ):
        cmd = InstallerService.get_linux_bootstrap_command("tok", install_mode="auto")

    result = subprocess.run(["/bin/sh", "-c", cmd], env=env, text=True, capture_output=True, check=False)

    assert result.returncode == 0, result.stderr
    assert runner_log.read_text(encoding="utf-8") == "sh"


@pytest.mark.django_db
def test_get_linux_bootstrap_command_auto_mode_uses_non_interactive_sudo_for_non_root(tmp_path):
    env, _, _, bootstrap_log = _prepare_bootstrap_shell_test(tmp_path, "sh", uid=1000)
    with patch(
        "apps.node_mgmt.services.installer.InstallerSessionService.build_session_config",
        return_value=_SESSION_CFG,
    ):
        cmd = InstallerService.get_linux_bootstrap_command("tok", install_mode="auto")

    result = subprocess.run(["/bin/sh", "-c", cmd], env=env, text=True, capture_output=True, check=False)
    sudo_calls = (tmp_path / "sudo.log").read_text(encoding="utf-8").splitlines()

    assert result.returncode == 0, result.stderr
    assert bootstrap_log.read_text(encoding="utf-8") == "ran"
    assert sudo_calls[0].endswith(" -c true")
    assert all(call.startswith("-n ") for call in sudo_calls)


@pytest.mark.django_db
def test_get_linux_bootstrap_command_manual_mode_uses_interactive_sudo_for_non_root(tmp_path):
    env, _, _, bootstrap_log = _prepare_bootstrap_shell_test(tmp_path, "sh", uid=1000)
    with patch(
        "apps.node_mgmt.services.installer.InstallerSessionService.build_session_config",
        return_value=_SESSION_CFG,
    ):
        cmd = InstallerService.get_linux_bootstrap_command("tok", install_mode="manual")

    result = subprocess.run(["/bin/sh", "-c", cmd], env=env, text=True, capture_output=True, check=False)
    sudo_calls = (tmp_path / "sudo.log").read_text(encoding="utf-8").splitlines()

    assert result.returncode == 0, result.stderr
    assert bootstrap_log.read_text(encoding="utf-8") == "ran"
    assert len(sudo_calls) == 1
    assert not sudo_calls[0].startswith("-n ")


@pytest.mark.django_db
def test_get_linux_bootstrap_command_preserves_download_failure_and_cleans_temp_file(tmp_path):
    env, bootstrap_temp, runner_log, bootstrap_log = _prepare_bootstrap_shell_test(
        tmp_path,
        "sh",
        curl_exit_code=22,
    )
    with patch(
        "apps.node_mgmt.services.installer.InstallerSessionService.build_session_config",
        return_value=_SESSION_CFG,
    ):
        cmd = InstallerService.get_linux_bootstrap_command("tok", install_mode="auto")

    result = subprocess.run(["/bin/sh", "-c", cmd], env=env, text=True, capture_output=True, check=False)

    assert result.returncode == 1
    assert not runner_log.exists()
    assert not bootstrap_log.exists()
    assert not bootstrap_temp.exists()


@pytest.mark.django_db
def test_get_linux_bootstrap_command_preserves_installer_failure_and_cleans_temp_file(tmp_path):
    env, bootstrap_temp, _, bootstrap_log = _prepare_bootstrap_shell_test(tmp_path, "sh")
    curl_path = tmp_path / "bin" / "curl"
    _write_executable(
        curl_path,
        """#!/bin/sh
output=''
while [ "$#" -gt 0 ]; do
  if [ "$1" = "-o" ]; then output="$2"; shift 2; else shift; fi
done
printf '%s\n' '#!/bin/sh' 'printf ran > "$BOOTSTRAP_LOG"' 'exit 7' > "$output"
""",
    )
    with patch(
        "apps.node_mgmt.services.installer.InstallerSessionService.build_session_config",
        return_value=_SESSION_CFG,
    ):
        cmd = InstallerService.get_linux_bootstrap_command("tok", install_mode="auto")

    result = subprocess.run(["/bin/sh", "-c", cmd], env=env, text=True, capture_output=True, check=False)

    assert result.returncode == 7
    assert bootstrap_log.read_text(encoding="utf-8") == "ran"
    assert not bootstrap_temp.exists()


@pytest.mark.django_db
def test_get_linux_bootstrap_command_reports_missing_supported_shell(tmp_path):
    empty_path = tmp_path / "bin"
    empty_path.mkdir()
    env = os.environ.copy()
    env["PATH"] = str(empty_path)
    with patch(
        "apps.node_mgmt.services.installer.InstallerSessionService.build_session_config",
        return_value=_SESSION_CFG,
    ):
        cmd = InstallerService.get_linux_bootstrap_command("tok", install_mode="auto")

    result = subprocess.run(["/bin/sh", "-c", cmd], env=env, text=True, capture_output=True, check=False)

    assert result.returncode == 1
    assert "controller installation requires sh or bash" in result.stderr


# --------------------------------------------------------------------------- #
# download installers (S3 boundary mocked)
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_download_windows_installer_calls_s3():
    download = AsyncMock(return_value=b"win-bytes")
    with patch("apps.node_mgmt.services.installer.download_file_by_s3", download):
        result = InstallerService.download_windows_installer("x86_64")
    assert result == b"win-bytes"


@pytest.mark.django_db
def test_download_linux_installer_calls_s3():
    download = AsyncMock(return_value=b"linux-bytes")
    with patch("apps.node_mgmt.services.installer.download_file_by_s3", download):
        result = InstallerService.download_linux_installer("arm64")
    assert result == b"linux-bytes"
