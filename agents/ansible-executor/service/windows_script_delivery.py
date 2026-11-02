"""通过 pywinrm Protocol 按 Ansible WinRM put_file 算法把脚本落到目标机临时目录。

不经过 Ansible 连接插件，避免 Display 锁 / 进程池在 executor 内卡死；
传输方式与 ansible.plugins.connection.winrm.put_file 相同（stdin base64 分块 + SHA1）。
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import json
from pathlib import Path
from typing import Any, Callable

from service.ansible_runner import WINDOWS_SCRIPT_MAX_BYTES, _write_restricted_bytes
from service.linux_script_delivery import ScriptDeliveryError, format_host_failure
from winrm.protocol import Protocol

_SCRIPT_SUFFIX = {"bat": ".cmd", "powershell": ".ps1", "python": ".py"}
_LOCAL_SCRIPT_PREFIX = "windows-job-script"
_COPY_FAILURE = "failed to copy Windows script to the target via WinRM put_file"
_TEMP_FAILURE = "failed to resolve Windows TEMP directory"
_PUT_CHUNK_BYTES = 250_000
_SUPPORTED_TRANSPORTS = {"auto", "basic", "certificate", "ntlm", "kerberos", "credssp", "plaintext", "ssl"}

ConnectionOpener = Callable[[dict[str, Any]], Any]


def remote_script_leaf(token: str, script_type: str) -> str:
    if script_type not in _SCRIPT_SUFFIX:
        raise ValueError(f"unsupported Windows script type: {script_type}")
    return f".bklite-stream-{token}{_SCRIPT_SUFFIX[script_type]}"


def prepare_windows_script_bytes(script_content: str, script_type: str) -> bytes:
    if script_type not in _SCRIPT_SUFFIX:
        raise ValueError(f"unsupported Windows script type: {script_type}")
    raw = str(script_content or "").encode("utf-8")
    if len(raw) > WINDOWS_SCRIPT_MAX_BYTES:
        raise ValueError(f"Windows script exceeds 512 KiB limit: {len(raw)} bytes")
    if script_type == "powershell":
        return b"\xef\xbb\xbf" + raw
    return raw


def stage_local_windows_script(directory: Path, script_bytes: bytes, script_type: str) -> Path:
    path = directory / f"{_LOCAL_SCRIPT_PREFIX}{_SCRIPT_SUFFIX[script_type]}"
    _write_restricted_bytes(path, script_bytes)
    return path


def connection_options(credential: dict[str, Any]) -> dict[str, Any]:
    """映射凭据为 WinRM Protocol 参数（测试 / 诊断用）。"""
    host = str(credential.get("host") or "").strip()
    scheme = str(credential.get("winrm_scheme") or "http").strip().lower() or "http"
    port = credential.get("port")
    if port is None or str(port).strip() == "":
        port = 5986 if scheme == "https" else 5985
    else:
        port = int(port)
    transport = str(credential.get("winrm_transport") or "ntlm").strip().lower() or "ntlm"
    cert_validation = "ignore" if credential.get("winrm_cert_validation") is False else "validate"
    return {
        "host": host,
        "user": str(credential.get("user") or ""),
        "password": str(credential.get("password") or ""),
        "port": port,
        "scheme": scheme,
        "transport": transport,
        "server_cert_validation": cert_validation,
    }


def build_winrm_protocol(credential: dict[str, Any]) -> Protocol:
    options = connection_options(credential)
    host = options["host"]
    if not host or any(char.isspace() for char in host) or any(char in host for char in "/@"):
        raise ValueError("invalid WinRM host")
    if options["scheme"] not in {"http", "https"}:
        raise ValueError("winrm_scheme must be http or https")
    if options["port"] < 1 or options["port"] > 65535:
        raise ValueError("invalid WinRM port")
    if options["transport"] not in _SUPPORTED_TRANSPORTS:
        raise ValueError("unsupported WinRM transport")
    return Protocol(
        endpoint=f"{options['scheme']}://{host}:{options['port']}/wsman",
        transport=options["transport"],
        username=options["user"],
        password=options["password"],
        server_cert_validation=options["server_cert_validation"],
        operation_timeout_sec=60,
        read_timeout_sec=70,
        proxy=None,
    )


class WinRMPutFileConnection:
    """最小连接面：exec_command / put_file / close，供投递与单测注入。"""

    def __init__(self, protocol: Protocol):
        self._protocol = protocol
        self._shell_id = protocol.open_shell()

    def exec_command(self, cmd: str, in_data: bytes | None = None, sudoable: bool = True) -> tuple[int, bytes, bytes]:
        del in_data, sudoable
        encoded = base64.b64encode(str(cmd).encode("utf-16-le")).decode("ascii")
        command_id = self._protocol.run_command(
            self._shell_id,
            "powershell.exe",
            ["-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
            console_mode_stdin=True,
        )
        try:
            stdout, stderr, code = self._protocol.get_command_output(self._shell_id, command_id)
            return int(code), stdout or b"", stderr or b""
        finally:
            with contextlib.suppress(Exception):
                self._protocol.cleanup_command(self._shell_id, command_id)

    def put_file(self, local_path: str, remote_path: str) -> None:
        safe_path = remote_path.replace("'", "''")
        writer = "\n".join(
            [
                "begin {",
                f"  $path = '{safe_path}'",
                '  $ErrorActionPreference = "Stop"',
                "  Set-StrictMode -Version 2",
                "  $fd = [System.IO.File]::Create($path)",
                "  $sha1 = [System.Security.Cryptography.SHA1CryptoServiceProvider]::Create()",
                "  $bytes = @()",
                "}",
                "process {",
                "  $bytes = [System.Convert]::FromBase64String($input)",
                "  $sha1.TransformBlock($bytes, 0, $bytes.Length, $bytes, 0) | Out-Null",
                "  $fd.Write($bytes, 0, $bytes.Length)",
                "}",
                "end {",
                "  $sha1.TransformFinalBlock($bytes, 0, 0) | Out-Null",
                '  $hash = [System.BitConverter]::ToString($sha1.Hash).Replace("-", "").ToLowerInvariant()',
                "  $fd.Close()",
                '  Write-Output "{""sha1"":""$hash""}"',
                "}",
            ]
        )
        encoded = base64.b64encode(writer.encode("utf-16-le")).decode("ascii")
        command_id = self._protocol.run_command(
            self._shell_id,
            "powershell.exe",
            ["-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
            console_mode_stdin=False,
        )
        try:
            local_size = Path(local_path).stat().st_size
            offset = 0
            with open(local_path, "rb") as handle:
                if local_size == 0:
                    self._protocol.send_command_input(self._shell_id, command_id, b"", end=True)
                else:
                    while True:
                        chunk = handle.read(_PUT_CHUNK_BYTES)
                        if not chunk:
                            break
                        offset += len(chunk)
                        self._protocol.send_command_input(
                            self._shell_id,
                            command_id,
                            base64.b64encode(chunk) + b"\r\n",
                            end=offset >= local_size,
                        )
            stdout, stderr, code = self._protocol.get_command_output(self._shell_id, command_id)
            if int(code) != 0:
                detail = (stderr or stdout or b"").decode("utf-8", errors="replace").strip() or _COPY_FAILURE
                raise RuntimeError(detail)
            text = (stdout or b"").decode("utf-8", errors="replace").strip()
            # Prefer last JSON-looking line (ignore CLIXML noise).
            remote_sha1 = ""
            for line in reversed(text.splitlines()):
                candidate = line.strip()
                if candidate.startswith("{") and "sha1" in candidate:
                    remote_sha1 = str(json.loads(candidate).get("sha1") or "")
                    break
            if not remote_sha1:
                raise RuntimeError(f"winrm put_file missing sha1; stdout={text[:200]!r}")
            local_sha1 = hashlib.sha1(Path(local_path).read_bytes()).hexdigest()
            if remote_sha1 != local_sha1:
                raise RuntimeError(f"Remote sha1 hash {remote_sha1} does not match local hash {local_sha1}")
        finally:
            with contextlib.suppress(Exception):
                self._protocol.cleanup_command(self._shell_id, command_id)

    def close(self) -> None:
        with contextlib.suppress(Exception):
            self._protocol.close_shell(self._shell_id)


def open_winrm_put_file_connection(credential: dict[str, Any]) -> WinRMPutFileConnection:
    return WinRMPutFileConnection(build_winrm_protocol(credential))


# Back-compat name used by earlier wiring/tests.
open_ansible_winrm_connection = open_winrm_put_file_connection


def _close_quietly(connection: Any) -> None:
    if connection is None:
        return
    closer = getattr(connection, "close", None)
    if closer is None:
        return
    try:
        closer()
    except Exception:
        return


def _join_windows_path(directory: str, leaf: str) -> str:
    return directory.rstrip("\\/") + "\\" + leaf


def _resolve_temp_directory(connection: Any) -> str:
    code, stdout, stderr = connection.exec_command("Write-Output $env:TEMP")
    text = (stdout or b"").decode("utf-8", errors="replace").strip()
    if code != 0 or not text:
        detail = (stderr or b"").decode("utf-8", errors="replace").strip() or text or _TEMP_FAILURE
        raise RuntimeError(detail)
    for line in text.splitlines():
        candidate = line.strip()
        if candidate and not candidate.startswith("#"):
            return candidate
    raise RuntimeError(_TEMP_FAILURE)


def _reencode_bat_script(connection: Any, remote_path: str) -> None:
    safe_path = remote_path.replace("'", "''")
    script = "\n".join(
        [
            f"$path = '{safe_path}'",
            "$utf8 = New-Object System.Text.UTF8Encoding($false, $true)",
            "$bytes = [IO.File]::ReadAllBytes($path)",
            "$text = $utf8.GetString($bytes)",
            "[IO.File]::WriteAllText($path, $text, [Text.Encoding]::Default)",
        ]
    )
    code, _stdout, stderr = connection.exec_command(script)
    if code != 0:
        detail = (stderr or b"").decode("utf-8", errors="replace").strip() or "BAT re-encode failed"
        raise RuntimeError(detail)


def _copy_one(
    opener: ConnectionOpener,
    credential: dict[str, Any],
    local_path: str,
    leaf: str,
    script_type: str,
) -> None:
    connection = None
    try:
        connection = opener(credential)
        temp_dir = _resolve_temp_directory(connection)
        remote_path = _join_windows_path(temp_dir, leaf)
        connection.put_file(local_path, remote_path)
        if script_type == "bat":
            _reencode_bat_script(connection, remote_path)
    finally:
        _close_quietly(connection)


def copy_windows_script_to_hosts(
    local_path: str,
    leaf: str,
    script_type: str,
    host_credentials: list[dict[str, Any]],
    *,
    connection_opener: ConnectionOpener | None = None,
) -> None:
    """把本地脚本 put_file 到每台 Windows 主机的 %TEMP%\\leaf。"""
    if script_type not in _SCRIPT_SUFFIX:
        raise ValueError(f"unsupported Windows script type: {script_type}")
    if not host_credentials:
        raise ValueError("host_credentials are required for Windows put_file delivery")
    opener = connection_opener or open_winrm_put_file_connection
    hosts = [str(item.get("host") or "") for item in host_credentials if item.get("host")]
    for credential in host_credentials:
        try:
            _copy_one(opener, credential, local_path, leaf, script_type)
        except ScriptDeliveryError:
            raise
        except Exception as error:  # noqa: BLE001 - 聚合成可回调的逐主机失败
            host = str(credential.get("host") or "")
            message = str(error).strip() or _COPY_FAILURE
            failure = ScriptDeliveryError(message, hosts)
            failure.host_output = format_host_failure([host] if host else hosts, message)
            raise failure from error


def _cli_main(argv: list[str] | None = None) -> int:
    """子进程入口：隔离 WinRM put_file，避免卡死 ansible-executor 的 event loop。"""
    import argparse
    import json
    import sys

    parser = argparse.ArgumentParser(prog="windows_script_delivery")
    parser.add_argument("payload_json", help="JSON file with local_path/leaf/script_type/host_credentials")
    args = parser.parse_args(argv)
    try:
        payload = json.loads(Path(args.payload_json).read_text(encoding="utf-8"))
        copy_windows_script_to_hosts(
            str(payload["local_path"]),
            str(payload["leaf"]),
            str(payload["script_type"]),
            list(payload["host_credentials"]),
        )
    except ScriptDeliveryError as error:
        sys.stderr.write(str(error.host_output or error) + "\n")
        return 2
    except Exception as error:  # noqa: BLE001
        sys.stderr.write(str(error) + "\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli_main())
