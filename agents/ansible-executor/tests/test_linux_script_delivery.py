from pathlib import Path

import pytest
from service.ansible_runner import _get_password_auth_ssh_common_args
from service.linux_script_delivery import (
    LINUX_SCRIPT_MAX_BYTES,
    ScriptDeliveryError,
    connection_options,
    copy_script_to_hosts,
    ensure_linux_script_bytes,
    open_ansible_ssh_connection,
)


def test_linux_script_limit_counts_bytes_and_accepts_exact_boundary():
    exact = "a" * LINUX_SCRIPT_MAX_BYTES
    assert ensure_linux_script_bytes(exact, ["10.0.0.1"]) == exact.encode("utf-8")

    with pytest.raises(ScriptDeliveryError, match=r"512 KiB limit: 524289 bytes"):
        ensure_linux_script_bytes("a" * (LINUX_SCRIPT_MAX_BYTES + 1), ["10.0.0.1"])

    with pytest.raises(ScriptDeliveryError, match=r"512 KiB limit: 600000 bytes"):
        ensure_linux_script_bytes("你" * 200_000, ["10.0.0.1"])


def test_password_ssh_args_match_inventory_and_key_auth_does_not_disable_host_checking():
    password_host = {"host": "10.0.0.8", "user": "root", "password": "sentinel-password", "connection": "ssh", "port": 2222}
    options = connection_options(password_host, "sftp", None)
    assert options["ssh_transfer_method"] == "sftp"
    assert options["host"] == "10.0.0.8"
    assert options["port"] == 2222
    assert options["ssh_common_args"] == _get_password_auth_ssh_common_args(password_host)

    key_host = {"host": "10.0.0.9", "user": "root", "connection": "ssh"}
    key_options = connection_options(key_host, "scp", "/tmp/id_rsa_0")
    assert "ssh_common_args" not in key_options
    assert "StrictHostKeyChecking=no" not in str(key_options)
    assert key_options["private_key_file"] == "/tmp/id_rsa_0"
    assert key_options["ssh_transfer_method"] == "scp"


def test_copy_falls_back_from_sftp_to_scp_and_keeps_existing_key(tmp_path):
    key_file = tmp_path / "id_rsa_0"
    key_file.write_text("existing-key", encoding="utf-8")
    calls: list[str] = []

    class Connection:
        def __init__(self, method: str):
            self.method = method

        def put_file(self, local_path: str, remote_path: str):
            calls.append(f"{self.method}:{Path(local_path).name}:{remote_path}")
            if self.method == "sftp":
                raise OSError("sftp subsystem unavailable")

        def close(self):
            calls.append(f"close:{self.method}")

    def opener(credential, method, private_key_file):
        assert credential["host"] == "10.0.0.8"
        assert private_key_file == str(key_file)
        return Connection(method)

    copy_script_to_hosts(
        str(tmp_path / "script"),
        "/tmp/.bklite-stream-token/script",
        [{"host": "10.0.0.8", "private_key_content": "new-key"}],
        tmp_path,
        connection_opener=opener,
    )

    assert calls == [
        "sftp:script:/tmp/.bklite-stream-token/script",
        "close:sftp",
        "scp:script:/tmp/.bklite-stream-token/script",
        "close:scp",
    ]
    assert key_file.read_text(encoding="utf-8") == "existing-key"


def test_copy_failure_does_not_include_password(tmp_path):
    class Connection:
        def put_file(self, _local_path: str, _remote_path: str):
            raise OSError("sentinel-password")

        def close(self):
            return None

    with pytest.raises(ScriptDeliveryError) as raised:
        copy_script_to_hosts(
            str(tmp_path / "script"),
            "/tmp/.bklite-stream-token/script",
            [{"host": "10.0.0.8", "password": "sentinel-password"}],
            tmp_path,
            connection_opener=lambda _credential, _method, _key: Connection(),
        )

    assert "sentinel-password" not in str(raised.value)
    assert "sentinel-password" not in raised.value.host_output
    assert "SFTP and scp are unavailable" in str(raised.value)
    assert "piped" not in str(raised.value)


def test_open_ansible_ssh_connection_sets_transfer_method(monkeypatch):
    captured: dict[str, object] = {}

    class Connection:
        def set_options(self, direct=None, **_kwargs):
            captured["direct"] = direct

    def fake_get(name, play_context, _stdin):
        captured["name"] = name
        captured["addr"] = play_context.remote_addr
        captured["password"] = play_context.password
        return Connection()

    import ansible.plugins.loader as loader

    monkeypatch.setattr(loader.connection_loader, "get", fake_get)
    open_ansible_ssh_connection(
        {"host": "10.0.0.8", "user": "root", "port": 2222, "password": "sentinel-password"},
        "sftp",
        None,
    )

    assert captured["name"] == "ssh"
    assert captured["addr"] == "10.0.0.8"
    assert captured["password"] == "sentinel-password"
    direct = captured["direct"]
    assert direct["host"] == "10.0.0.8"
    assert direct["ssh_transfer_method"] == "sftp"
    assert direct["remote_user"] == "root"
    assert direct["port"] == 2222
