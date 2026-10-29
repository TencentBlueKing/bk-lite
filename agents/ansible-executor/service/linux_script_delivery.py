"""把 Linux 作业脚本复制到目标机，避免脚本正文进入 ansible 命令参数。"""

from pathlib import Path
from typing import Any, Callable

from service.ansible_runner import (
    WINDOWS_SCRIPT_MAX_BYTES,
    _get_explicit_ssh_common_args,
    _get_password_auth_ssh_common_args,
    _write_restricted_bytes,
)

# 与 Windows 作业脚本共用 512 KiB。这是产品上限，不是 Linux 单参数 128 KiB 内核限制。
LINUX_SCRIPT_MAX_BYTES = WINDOWS_SCRIPT_MAX_BYTES
_LOCAL_SCRIPT_NAME = "remote-shell-script"
_TRANSFER_METHODS = ("sftp", "scp")
_COPY_FAILURE = "failed to copy Linux script to the target; SFTP and scp are unavailable"
_DIRECTORY_FAILURE = "failed to create remote script directory"

ConnectionOpener = Callable[[dict[str, Any], str, str | None], Any]


class ScriptDeliveryError(Exception):
    """脚本尚未执行。host_output 是可被回调解析的逐主机失败结果。"""

    def __init__(self, message: str, hosts: list[str]):
        super().__init__(message)
        self.hosts = hosts
        self.host_output = format_host_failure(hosts, message)


def format_host_failure(hosts: list[str], message: str) -> str:
    usable = [host for host in hosts if host]
    if not usable:
        return message
    return "\n".join(f"{host} | FAILED | rc=1 >>\n{message}" for host in usable)


def ensure_linux_script_bytes(script_content: str, hosts: list[str]) -> bytes:
    script_bytes = str(script_content or "").encode("utf-8")
    if len(script_bytes) > LINUX_SCRIPT_MAX_BYTES:
        raise ScriptDeliveryError(
            f"Linux script exceeds 512 KiB limit: {len(script_bytes)} bytes",
            hosts,
        )
    return script_bytes


def stage_local_script(directory: Path, script_bytes: bytes) -> Path:
    path = directory / _LOCAL_SCRIPT_NAME
    _write_restricted_bytes(path, script_bytes)
    return path


def copy_ssh_common_args(credential: dict[str, Any]) -> str:
    """与同一次作业写入 inventory 的 SSH 参数一致，不另外放宽主机密钥校验。"""
    if credential.get("password"):
        return _get_password_auth_ssh_common_args(credential)
    return _get_explicit_ssh_common_args(credential) or ""


def connection_options(
    credential: dict[str, Any],
    method: str,
    private_key_file: str | None,
) -> dict[str, Any]:
    options: dict[str, Any] = {
        "host": str(credential.get("host") or ""),
        "ssh_transfer_method": method,
        "timeout": 30,
        "password": str(credential.get("password") or ""),
    }
    user = credential.get("user")
    if user:
        options["remote_user"] = str(user)
    port = credential.get("port")
    if port is not None and str(port).strip() != "":
        options["port"] = int(port)
    if private_key_file:
        options["private_key_file"] = private_key_file
    common_args = copy_ssh_common_args(credential)
    if common_args:
        options["ssh_common_args"] = common_args
    return options


def open_ansible_ssh_connection(
    credential: dict[str, Any],
    method: str,
    private_key_file: str | None,
) -> Any:
    from ansible.playbook.play_context import PlayContext
    from ansible.plugins.loader import connection_loader

    play_context = PlayContext()
    play_context.remote_addr = str(credential.get("host") or "")
    play_context.connection = "ssh"
    play_context.password = str(credential.get("password") or "")
    play_context.timeout = 30
    if credential.get("user"):
        play_context.remote_user = str(credential["user"])
    port = credential.get("port")
    if port is not None and str(port).strip() != "":
        play_context.port = int(port)
    connection = connection_loader.get("ssh", play_context, None)
    connection.set_options(direct=connection_options(credential, method, private_key_file))
    return connection


def copy_script_to_hosts(
    local_path: str,
    remote_path: str,
    host_credentials: list[dict[str, Any]],
    workspace: Path | None,
    *,
    connection_opener: ConnectionOpener | None = None,
) -> None:
    opener = connection_opener or open_ansible_ssh_connection
    hosts = [str(item.get("host") or "") for item in host_credentials if item.get("host")]
    for index, credential in enumerate(host_credentials):
        key_file = _private_key_path(workspace, index, credential)
        if not _copy_one(opener, credential, key_file, local_path, remote_path):
            raise ScriptDeliveryError(_COPY_FAILURE, hosts)


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


def _copy_one(
    opener: ConnectionOpener,
    credential: dict[str, Any],
    key_file: str | None,
    local_path: str,
    remote_path: str,
) -> bool:
    for method in _TRANSFER_METHODS:
        connection = None
        try:
            connection = opener(credential, method, key_file)
            connection.put_file(local_path, remote_path)
            return True
        except Exception:
            continue
        finally:
            _close_quietly(connection)
    return False


def _private_key_path(workspace: Path | None, index: int, credential: dict[str, Any]) -> str | None:
    if workspace is not None:
        existing = workspace / f"id_rsa_{index}"
        if existing.is_file():
            return str(existing)
        content = credential.get("private_key_content")
        if content:
            _write_restricted_bytes(existing, str(content).encode("utf-8"))
            return str(existing)
    configured = credential.get("private_key_file")
    if configured:
        return str(configured)
    return None
