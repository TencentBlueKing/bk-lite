from types import SimpleNamespace

import pytest

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.node_mgmt.constants.node import NodeConstants
from apps.node_mgmt.services.installer_session import InstallerSessionService


pytestmark = pytest.mark.unit


def _token_data(os_name, *, install_mode="auto"):
    return {
        "package_id": 1,
        "cloud_region_id": 7,
        "ip": "10.0.0.9",
        "user": "root",
        "node_id": "node-installer",
        "node_name": "node-installer",
        "os": os_name,
        "install_mode": install_mode,
        "remaining_usage": 4,
        "organizations": [],
        "cpu_architecture": NodeConstants.X86_64_ARCH,
    }


def _stub_installer_session_dependencies(monkeypatch, envs):
    monkeypatch.setattr(InstallerSessionService, "_get_cloud_region_env", lambda _: envs)
    monkeypatch.setattr(
        "apps.node_mgmt.services.installer_session.PackageService.resolve_package_by_architecture",
        lambda *args: SimpleNamespace(
            id=1,
            name="controller.zip",
            object="Controller",
            os=NodeConstants.LINUX_OS,
            version="1.0.0",
        ),
    )
    monkeypatch.setattr(
        "apps.node_mgmt.services.installer_session.PackageService.resolve_existing_file_path",
        lambda _: "windows/Controller/1.0.0/controller.zip",
    )
    monkeypatch.setattr(
        "apps.node_mgmt.services.installer_session.generate_node_token",
        lambda *args: "sidecar-token",
    )


def test_linux_session_strict_mode_rejects_admin_fallback(monkeypatch):
    _stub_installer_session_dependencies(
        monkeypatch,
        {
            NodeConstants.SERVER_URL_KEY: "https://server.example",
            NodeConstants.NATS_SERVERS_KEY: "tls://nats.example:4222",
            "NATS_PROTOCOL": "tls",
            "NATS_ADMIN_USERNAME": "admin",
            NodeConstants.NATS_ADMIN_PASSWORD_KEY: "admin-password",
            NodeConstants.NATS_INSTALLER_CREDENTIALS_MODE_KEY: NodeConstants.NATS_INSTALLER_CREDENTIALS_MODE_STRICT,
        },
    )

    with pytest.raises(BaseAppException, match="dedicated NATS_INSTALLER"):
        InstallerSessionService.build_session_config(
            "token",
            token_data=_token_data(NodeConstants.LINUX_OS),
        )


@pytest.mark.parametrize("invalid_mode", ["typo", ""])
def test_linux_session_rejects_invalid_installer_credentials_mode(monkeypatch, invalid_mode):
    _stub_installer_session_dependencies(
        monkeypatch,
        {
            NodeConstants.SERVER_URL_KEY: "https://server.example",
            NodeConstants.NATS_SERVERS_KEY: "tls://nats.example:4222",
            "NATS_PROTOCOL": "tls",
            "NATS_ADMIN_USERNAME": "admin",
            NodeConstants.NATS_ADMIN_PASSWORD_KEY: "admin-password",
            NodeConstants.NATS_INSTALLER_CREDENTIALS_MODE_KEY: invalid_mode,
        },
    )

    with pytest.raises(BaseAppException, match="NATS_INSTALLER_CREDENTIALS_MODE must be legacy or strict"):
        InstallerSessionService.build_session_config(
            "token",
            token_data=_token_data(NodeConstants.LINUX_OS),
        )


def test_windows_remote_session_requires_dedicated_nats_credentials(monkeypatch):
    _stub_installer_session_dependencies(
        monkeypatch,
        {
            NodeConstants.SERVER_URL_KEY: "https://server.example",
            NodeConstants.NATS_SERVERS_KEY: "tls://nats.example:4222",
            "NATS_PROTOCOL": "tls",
            "NATS_ADMIN_USERNAME": "admin",
            NodeConstants.NATS_ADMIN_PASSWORD_KEY: "admin-password",
        },
    )

    with pytest.raises(BaseAppException, match="dedicated NATS_INSTALLER"):
        InstallerSessionService.build_session_config(
            "token",
            token_data=_token_data(NodeConstants.WINDOWS_OS),
        )


@pytest.mark.parametrize(
    "installer_credentials",
    [
        {
            NodeConstants.NATS_INSTALLER_USERNAME_KEY: "   ",
            NodeConstants.NATS_INSTALLER_PASSWORD_KEY: "installer-password",
        },
        {
            NodeConstants.NATS_INSTALLER_USERNAME_KEY: "installer",
            NodeConstants.NATS_INSTALLER_PASSWORD_KEY: "   ",
        },
    ],
)
def test_strict_session_rejects_blank_installer_credentials(monkeypatch, installer_credentials):
    _stub_installer_session_dependencies(
        monkeypatch,
        {
            NodeConstants.SERVER_URL_KEY: "https://server.example",
            NodeConstants.NATS_SERVERS_KEY: "tls://nats.example:4222",
            "NATS_PROTOCOL": "tls",
            NodeConstants.NATS_INSTALLER_CREDENTIALS_MODE_KEY: NodeConstants.NATS_INSTALLER_CREDENTIALS_MODE_STRICT,
            **installer_credentials,
        },
    )

    with pytest.raises(BaseAppException, match="dedicated NATS_INSTALLER"):
        InstallerSessionService.build_session_config(
            "token",
            token_data=_token_data(NodeConstants.LINUX_OS),
        )


def test_windows_remote_session_requires_tls_nats(monkeypatch):
    _stub_installer_session_dependencies(
        monkeypatch,
        {
            NodeConstants.SERVER_URL_KEY: "https://server.example",
            NodeConstants.NATS_SERVERS_KEY: "nats://nats.example:4222",
            "NATS_PROTOCOL": "nats",
            NodeConstants.NATS_INSTALLER_USERNAME_KEY: "installer",
            NodeConstants.NATS_INSTALLER_PASSWORD_KEY: "installer-password",
        },
    )

    with pytest.raises(BaseAppException, match="NATS_PROTOCOL=tls"):
        InstallerSessionService.build_session_config(
            "token",
            token_data=_token_data(NodeConstants.WINDOWS_OS),
        )


@pytest.mark.parametrize(
    ("mode", "installer_credentials", "expected_username"),
    [
        (NodeConstants.NATS_INSTALLER_CREDENTIALS_MODE_STRICT, {}, None),
        (NodeConstants.NATS_INSTALLER_CREDENTIALS_MODE_LEGACY, {}, "admin"),
        (None, {}, "admin"),
        (
            NodeConstants.NATS_INSTALLER_CREDENTIALS_MODE_STRICT,
            {
                NodeConstants.NATS_INSTALLER_USERNAME_KEY: "installer",
                NodeConstants.NATS_INSTALLER_PASSWORD_KEY: "installer-password",
            },
            "installer",
        ),
    ],
)
def test_windows_manual_installer_credentials_mode_matrix(
    monkeypatch,
    mode,
    installer_credentials,
    expected_username,
):
    envs = {
        NodeConstants.SERVER_URL_KEY: "https://server.example",
        NodeConstants.NATS_SERVERS_KEY: "tls://nats.example:4222",
        "NATS_PROTOCOL": "tls",
        "NATS_ADMIN_USERNAME": "admin",
        NodeConstants.NATS_ADMIN_PASSWORD_KEY: "admin-password",
        **installer_credentials,
    }
    if mode is not None:
        envs[NodeConstants.NATS_INSTALLER_CREDENTIALS_MODE_KEY] = mode
    _stub_installer_session_dependencies(monkeypatch, envs)

    if expected_username is None:
        with pytest.raises(BaseAppException, match="strict mode requires dedicated"):
            InstallerSessionService.build_session_config(
                "token",
                token_data=_token_data(NodeConstants.WINDOWS_OS, install_mode="manual"),
            )
        return

    config = InstallerSessionService.build_session_config(
        "token",
        token_data=_token_data(NodeConstants.WINDOWS_OS, install_mode="manual"),
    )

    assert config["storage"]["nats_username"] == expected_username
