from pathlib import Path

import pytest
from service.linux_script_delivery import ScriptDeliveryError
from service.windows_script_delivery import (
    connection_options,
    copy_windows_script_to_hosts,
    prepare_windows_script_bytes,
    remote_script_leaf,
    stage_local_windows_script,
)


def test_prepare_windows_script_bytes_rejects_over_512_kib():
    with pytest.raises(ValueError, match="512 KiB"):
        prepare_windows_script_bytes("x" * (512 * 1024 + 1), "python")


def test_connection_options_map_winrm_credentials():
    options = connection_options(
        {
            "host": "10.10.90.120",
            "user": "cwadmin",
            "password": "secret",
            "port": 5985,
            "winrm_scheme": "http",
            "winrm_transport": "ntlm",
            "winrm_cert_validation": False,
        }
    )
    assert options["host"] == "10.10.90.120"
    assert options["user"] == "cwadmin"
    assert options["password"] == "secret"
    assert options["port"] == 5985
    assert options["scheme"] == "http"
    assert options["transport"] == "ntlm"
    assert options["server_cert_validation"] == "ignore"


def test_copy_windows_script_resolves_temp_put_file_and_optional_bat_reencode(tmp_path):
    local = stage_local_windows_script(tmp_path, b"@echo off\r\necho hi\r\n", "bat")
    leaf = remote_script_leaf("tok1", "bat")
    calls: list[str] = []

    class Connection:
        def exec_command(self, cmd: str, in_data=None, sudoable=True):
            calls.append(f"exec:{cmd}")
            if "TEMP" in cmd and "WriteAllText" not in cmd:
                return 0, b"C:\\Users\\cwadmin\\AppData\\Local\\Temp\r\n", b""
            if "WriteAllText" in cmd:
                return 0, b"", b""
            return 1, b"", b"unexpected"

        def put_file(self, local_path: str, remote_path: str):
            calls.append(f"put:{Path(local_path).name}:{remote_path}")
            assert remote_path.endswith("\\" + leaf)

        def close(self):
            calls.append("close")

    copy_windows_script_to_hosts(
        str(local),
        leaf,
        "bat",
        [{"host": "10.10.90.120", "connection": "winrm"}],
        connection_opener=lambda credential: Connection(),
    )

    assert calls[0].startswith("exec:Write-Output")
    assert calls[1].startswith("put:")
    assert any("WriteAllText" in item for item in calls)
    assert calls[-1] == "close"


def test_copy_windows_script_surfaces_put_file_failure(tmp_path):
    local = stage_local_windows_script(tmp_path, b"print(1)\n", "python")
    leaf = remote_script_leaf("tok2", "python")

    class Connection:
        def exec_command(self, cmd: str, in_data=None, sudoable=True):
            return 0, b"C:\\Temp\n", b""

        def put_file(self, local_path: str, remote_path: str):
            raise OSError("put exploded")

        def close(self):
            return None

    with pytest.raises(ScriptDeliveryError) as raised:
        copy_windows_script_to_hosts(
            str(local),
            leaf,
            "python",
            [{"host": "10.10.90.120"}],
            connection_opener=lambda credential: Connection(),
        )
    assert "put exploded" in raised.value.host_output
    assert "10.10.90.120" in raised.value.host_output
