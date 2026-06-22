"""issue #3524 回归测试：安装引导脚本默认启用 TLS 校验（不含 -k / --skip-tls）。"""

import pytest
from unittest.mock import patch

from apps.node_mgmt.services.installer import InstallerService


def _fake_session(token):
    return {
        "installer": {"filename": "bklite-controller-installer"},
        "install_dir": "/opt/fusion-collectors",
        "server_url": "https://bklite.example.com/api/v1/node_mgmt/open_api/node",
    }


@pytest.mark.parametrize("install_mode", [InstallerService.MANUAL_INSTALL_MODE, InstallerService.AUTO_INSTALL_MODE])
def test_bootstrap_command_does_not_contain_skip_tls_flag(install_mode, monkeypatch):
    """生成的引导命令不得包含 --skip-tls（TLS 验证不能默认关闭）。"""
    monkeypatch.setattr(
        "apps.node_mgmt.services.installer.InstallerSessionService.build_session_config",
        _fake_session,
    )
    cmd = InstallerService.get_linux_bootstrap_command("tok", install_mode=install_mode)
    assert "--skip-tls" not in cmd, f"bootstrap command must not contain --skip-tls: {cmd}"


@pytest.mark.parametrize("install_mode", [InstallerService.MANUAL_INSTALL_MODE, InstallerService.AUTO_INSTALL_MODE])
def test_bootstrap_command_does_not_use_insecure_curl(install_mode, monkeypatch):
    """生成的引导命令不得使用 curl -k（-k 禁用证书校验）。"""
    monkeypatch.setattr(
        "apps.node_mgmt.services.installer.InstallerSessionService.build_session_config",
        _fake_session,
    )
    cmd = InstallerService.get_linux_bootstrap_command("tok", install_mode=install_mode)
    # curl -sSLk 或 curl -k 均视为不安全
    assert "curl -sSLk" not in cmd, f"bootstrap command must not use curl -k: {cmd}"
    assert "curl -fsSLk" not in cmd, f"bootstrap command must not use curl -k: {cmd}"
