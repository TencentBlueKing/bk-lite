import asyncio
import contextlib
import importlib
import json
import os
import re
import shlex
import shutil
import signal
import ssl
import stat
import uuid
import zipfile
from codecs import decode as codecs_decode
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from core.config import ServiceConfig, logger
from service.runtime import current_entrypoint_command

BASE_TASK_DIR = Path(os.getenv("ANSIBLE_WORK_DIR", "/tmp/ansible-executor"))

_SENSITIVE_INVENTORY_PATTERNS = (
    "ansible_password",
    "ansible_ssh_passphrase",
    "ansible_become_password",
)


def _looks_like_utf16le(output: bytes) -> bool:
    if b"\x00" not in output:
        return False
    zero_count = sum(1 for idx in range(1, len(output), 2) if output[idx] == 0)
    return zero_count >= len(output) // 4


def _decode_utf16le_output(output: bytes) -> str | None:
    if len(output) < 2:
        return None
    candidate = output
    has_bom = candidate.startswith(b"\xff\xfe")
    if has_bom:
        candidate = candidate[2:]
    if len(candidate) < 2 or len(candidate) % 2 != 0:
        return None
    if not has_bom and not _looks_like_utf16le(candidate):
        return None
    try:
        return candidate.decode("utf-16-le")
    except UnicodeDecodeError:
        return None


def decode_command_output(output: bytes) -> tuple[str, str]:
    utf16_decoded = _decode_utf16le_output(output)
    if utf16_decoded is not None:
        return utf16_decoded, "utf16le"
    try:
        return output.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        pass
    try:
        return codecs_decode(output, "gbk"), "gbk"
    except UnicodeDecodeError:
        return output.decode("utf-8", errors="replace"), "utf-8-replace"


@dataclass
class AdhocRequest:
    inventory: str = ""
    inventory_content: str | None = None
    hosts: str = "all"
    module: str = "ping"
    module_args: str = ""
    extra_vars: dict[str, Any] | None = None
    execute_timeout: int = 60
    task_id: str | None = None
    callback: dict[str, Any] | None = None
    private_key_content: str | None = None
    private_key_passphrase: str | None = None
    host_credentials: list[dict[str, Any]] | None = None


@dataclass
class PlaybookRequest:
    playbook_path: str = ""
    playbook_content: str | None = None
    inventory: str = ""
    inventory_content: str | None = None
    extra_vars: dict[str, Any] | None = None
    execute_timeout: int = 600
    task_id: str | None = None
    callback: dict[str, Any] | None = None
    private_key_content: str | None = None
    private_key_passphrase: str | None = None
    host_credentials: list[dict[str, Any]] | None = None
    files: list[dict[str, Any]] | None = None
    file_distribution: dict[str, Any] | None = None


def _validate_host_credentials(payload: dict[str, Any]) -> list[dict[str, Any]]:
    host_credentials = payload.get("host_credentials")
    if host_credentials is None:
        return []
    if not isinstance(host_credentials, list):
        raise ValueError("host_credentials must be list")
    normalized: list[dict[str, Any]] = []
    for idx, item in enumerate(host_credentials):
        if not isinstance(item, dict):
            raise ValueError(f"host_credentials[{idx}] must be object")
        host = str(item.get("host", "")).strip()
        if not host:
            raise ValueError(f"host_credentials[{idx}].host is required")
        normalized.append(item)
    return normalized


def to_adhoc_request(payload: dict[str, Any]) -> AdhocRequest:
    host_credentials = _validate_host_credentials(payload)
    inventory = str(payload.get("inventory", "")).strip()
    inventory_content = payload.get("inventory_content")
    if inventory_content is not None and not isinstance(inventory_content, str):
        raise ValueError("inventory_content must be string")
    if not inventory and not inventory_content and not host_credentials:
        raise ValueError("inventory or inventory_content or host_credentials is required")
    if inventory and host_credentials and not inventory_content:
        raise ValueError("inventory path with host_credentials is ambiguous, use inventory_content or only host_credentials")

    timeout = int(payload.get("execute_timeout", 60))
    if timeout < 1 or timeout > 3600:
        raise ValueError("execute_timeout must be in [1, 3600]")

    extra_vars = payload.get("extra_vars") or {}
    if not isinstance(extra_vars, dict):
        raise ValueError("extra_vars must be object")

    private_key_content = payload.get("private_key_content")
    if private_key_content is not None and not isinstance(private_key_content, str):
        raise ValueError("private_key_content must be string")
    private_key_passphrase = payload.get("private_key_passphrase")
    if private_key_passphrase is not None and not isinstance(private_key_passphrase, str):
        raise ValueError("private_key_passphrase must be string")

    return AdhocRequest(
        inventory=inventory,
        inventory_content=inventory_content,
        hosts=str(payload.get("hosts", "all")),
        module=str(payload.get("module", "ping")),
        module_args=str(payload.get("module_args", "")),
        extra_vars=extra_vars,
        execute_timeout=timeout,
        task_id=str(payload.get("task_id", "")).strip() or None,
        callback=payload.get("callback"),
        private_key_content=private_key_content,
        private_key_passphrase=private_key_passphrase,
        host_credentials=host_credentials,
    )


def to_playbook_request(payload: dict[str, Any]) -> PlaybookRequest:
    host_credentials = _validate_host_credentials(payload)
    playbook_path = str(payload.get("playbook_path", "")).strip()
    playbook_content = payload.get("playbook_content")
    inventory = str(payload.get("inventory", "")).strip()
    inventory_content = payload.get("inventory_content")
    if playbook_content is not None and not isinstance(playbook_content, str):
        raise ValueError("playbook_content must be string")
    if inventory_content is not None and not isinstance(inventory_content, str):
        raise ValueError("inventory_content must be string")
    files = payload.get("files") or []
    if not isinstance(files, list):
        raise ValueError("files must be list")
    file_distribution = payload.get("file_distribution") or None
    if file_distribution is not None and not isinstance(file_distribution, dict):
        raise ValueError("file_distribution must be object")

    no_playbook_path = not playbook_path
    no_playbook_content = not playbook_content
    no_file_distribution = not file_distribution

    if no_playbook_path and no_playbook_content and no_file_distribution:
        raise ValueError("playbook_path or playbook_content is required")
    if not inventory and not inventory_content and not host_credentials:
        raise ValueError("inventory or inventory_content or host_credentials is required")
    if inventory and host_credentials and not inventory_content:
        raise ValueError("inventory path with host_credentials is ambiguous, use inventory_content or only host_credentials")

    timeout = int(payload.get("execute_timeout", 600))
    if timeout < 1 or timeout > 7200:
        raise ValueError("execute_timeout must be in [1, 7200]")

    extra_vars = payload.get("extra_vars") or {}
    if not isinstance(extra_vars, dict):
        raise ValueError("extra_vars must be object")

    private_key_content = payload.get("private_key_content")
    if private_key_content is not None and not isinstance(private_key_content, str):
        raise ValueError("private_key_content must be string")
    private_key_passphrase = payload.get("private_key_passphrase")
    if private_key_passphrase is not None and not isinstance(private_key_passphrase, str):
        raise ValueError("private_key_passphrase must be string")

    return PlaybookRequest(
        playbook_path=playbook_path,
        playbook_content=playbook_content,
        inventory=inventory,
        inventory_content=inventory_content,
        extra_vars=extra_vars,
        execute_timeout=timeout,
        task_id=str(payload.get("task_id", "")).strip() or None,
        callback=payload.get("callback"),
        private_key_content=private_key_content,
        private_key_passphrase=private_key_passphrase,
        host_credentials=host_credentials,
        files=files,
        file_distribution=file_distribution,
    )


async def download_object_to_workspace(config: ServiceConfig, workspace: Path, bucket_name: str, file_item: dict[str, Any]) -> str:
    file_key = str(file_item.get("file_key", "")).strip()
    file_name = str(file_item.get("name", "")).strip() or Path(file_key).name
    if not file_key:
        raise ValueError("file_key is required")
    if not file_name:
        raise ValueError("file name is required")
    destination = _safe_workspace_path(workspace, file_name, "file name")

    nats_client_module = importlib.import_module("nats.aio.client")
    nc = nats_client_module.Client()

    connect_kwargs: dict[str, Any] = {
        "servers": list(config.nats_servers),
        "connect_timeout": int(config.nats_conn_timeout),
        "name": "ansible-executor-object-store",
    }
    if not connect_kwargs["servers"]:
        raise ValueError("NATS_SERVERS is required for object store download")

    nats_username = config.nats_username
    nats_password = config.nats_password
    if nats_username:
        connect_kwargs["user"] = nats_username
    if nats_password:
        connect_kwargs["password"] = nats_password

    if str(config.nats_protocol).lower() == "tls":
        tls_context = ssl.create_default_context()
        nats_tls_ca_file = config.nats_tls_ca_file
        if nats_tls_ca_file:
            tls_context.load_verify_locations(cafile=nats_tls_ca_file)
        connect_kwargs["tls"] = tls_context

    await nc.connect(**connect_kwargs)
    try:
        js = nc.jetstream(timeout=120)
        object_store = await js.object_store(bucket_name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("wb") as target_file:
            await object_store.get(file_key, writeinto=target_file)
        return str(destination)
    finally:
        await nc.close()


def _safe_workspace_path(workspace: Path, relative_path: str, field_name: str) -> Path:
    raw_path = str(relative_path).strip()
    if not raw_path:
        raise ValueError(f"{field_name} is required")
    candidate = Path(raw_path)
    if candidate.is_absolute() or any(part in {"..", ""} for part in candidate.parts):
        raise ValueError(f"{field_name} must be a relative path inside workspace")

    base = workspace.resolve()
    target = (base / candidate).resolve(strict=False)
    try:
        target.relative_to(base)
    except ValueError as exc:
        raise ValueError(f"{field_name} must stay inside workspace") from exc
    return target


def _safe_extract_zip(zip_file: zipfile.ZipFile, workspace: Path) -> None:
    for member in zip_file.infolist():
        safe_target = _safe_workspace_path(workspace, member.filename, "zip member")
        if member.is_dir():
            continue
        mode = member.external_attr >> 16
        if stat.S_ISLNK(mode):
            raise ValueError(f"zip member must not be symlink: {member.filename}")
        if safe_target.exists() and safe_target.is_symlink():
            raise ValueError(f"zip member target must not be symlink: {member.filename}")
    zip_file.extractall(workspace)


def _normalize_windows_target_path(target_path: str) -> str:
    return str(target_path).replace("\\", "/").rstrip("/")


def _join_windows_target_path(target_path: str, file_name: str) -> str:
    return f"{_normalize_windows_target_path(target_path)}/{file_name}"


def _build_windows_file_distribution_playbook(downloaded_files: list[dict[str, Any]], target_path: str, overwrite: bool) -> str:
    normalized_target_path = _normalize_windows_target_path(target_path)
    tasks = []
    for file_item in downloaded_files:
        file_name = str(file_item.get("name", "")).strip()
        local_path = str(file_item.get("local_path", "")).strip()
        if not file_name or not local_path:
            raise ValueError("downloaded file item requires name and local_path")
        tasks.append(
            {
                "name": f"Copy {file_name} to Windows host",
                "ansible.windows.win_copy": {
                    "src": local_path,
                    "dest": _join_windows_target_path(normalized_target_path, file_name),
                    "force": bool(overwrite),
                },
            }
        )

    playbook = [
        {
            "hosts": "all",
            "gather_facts": False,
            "tasks": tasks,
        }
    ]
    return yaml.safe_dump(playbook, allow_unicode=True, sort_keys=False)


def _materialize_private_key(workspace: Path, key_content: str) -> str:
    key_file = workspace / "id_rsa"
    key_file.write_text(key_content, encoding="utf-8")
    os.chmod(key_file, stat.S_IRUSR | stat.S_IWUSR)
    return str(key_file)


def _quote_inventory_value(value: Any) -> str:
    text = str(value)
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    if any(ch.isspace() for ch in text):
        return f'"{escaped}"'
    return escaped


def _mask_sensitive_inventory_content(content: str) -> str:
    masked = str(content)
    for key in _SENSITIVE_INVENTORY_PATTERNS:
        masked = re.sub(rf"({key}=)(\S+)", r"\1***", masked)
    return masked


def _get_password_auth_ssh_common_args(item: dict[str, Any]) -> str:
    explicit_args = item.get("ansible_ssh_common_args") or item.get("ssh_common_args")
    if explicit_args:
        return str(explicit_args)
    return "-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"


def _normalize_ansible_host_status(raw_status: str) -> str:
    normalized = str(raw_status).strip().upper()
    if normalized in {"SUCCESS", "CHANGED", "SKIPPED"}:
        return "success"
    return "failed"


def _build_parsed_host_result(host: str, raw_status: str, exit_code: int | None, output_lines: list[str]) -> dict[str, Any]:
    output = "\n".join(output_lines).strip()
    status = _normalize_ansible_host_status(raw_status)
    final_exit_code = exit_code if exit_code is not None else (0 if status == "success" else 1)
    stdout = output if status == "success" else ""
    stderr = "" if status == "success" else output
    return {
        "host": host,
        "status": status,
        "raw_status": str(raw_status).strip().upper(),
        "stdout": stdout,
        "stderr": stderr,
        "exit_code": final_exit_code,
        "error_message": "" if status == "success" else output,
    }


def parse_ansible_output_per_host(output: str) -> list[dict[str, Any]]:
    host_line_pattern = re.compile(r"^(\S+)\s+\|\s+(SUCCESS|CHANGED|FAILED|UNREACHABLE!?|SKIPPED)(?:\s+\|\s+rc=(-?\d+))?\s+(>>|=>)\s*(.*)$")
    results: list[dict[str, Any]] = []
    current_host: str | None = None
    current_status: str | None = None
    current_exit_code: int | None = None
    current_output_lines: list[str] = []
    preamble_lines: list[str] = []

    for line in str(output or "").splitlines():
        matched = host_line_pattern.match(line)
        if matched:
            if current_host and current_status:
                results.append(
                    _build_parsed_host_result(
                        current_host,
                        current_status,
                        current_exit_code,
                        current_output_lines,
                    )
                )
            current_host = matched.group(1)
            current_status = matched.group(2)
            rc_text = matched.group(3)
            current_exit_code = int(rc_text) if rc_text is not None else None
            initial_output = matched.group(5).strip()
            current_output_lines = list(preamble_lines)
            preamble_lines = []
            if initial_output:
                current_output_lines.append(initial_output)
            continue

        if current_host:
            current_output_lines.append(line)
        else:
            preamble_lines.append(line)

    if current_host and current_status:
        results.append(
            _build_parsed_host_result(
                current_host,
                current_status,
                current_exit_code,
                current_output_lines,
            )
        )

    return results


def parse_playbook_recap(output: str) -> list[dict[str, Any]]:
    """
    解析 playbook 输出的 PLAY RECAP 部分，构建 per-host 结果数组。

    PLAY RECAP 格式示例：
        10.10.41.149  : ok=1  changed=0  unreachable=0  failed=0  skipped=0  rescued=0  ignored=0

    判定逻辑：failed > 0 或 unreachable > 0 时视为失败。
    """
    recap_pattern = re.compile(r"^(\S+)\s+:\s+ok=(\d+)\s+changed=(\d+)\s+unreachable=(\d+)\s+failed=(\d+)")

    # 找到 PLAY RECAP 行之后的内容
    lines = str(output or "").splitlines()
    recap_start = -1
    for i, line in enumerate(lines):
        if line.strip().startswith("PLAY RECAP"):
            recap_start = i + 1
            break

    if recap_start < 0:
        return []

    results: list[dict[str, Any]] = []
    for line in lines[recap_start:]:
        matched = recap_pattern.match(line.strip())
        if not matched:
            continue

        host = matched.group(1)
        unreachable = int(matched.group(4))
        failed = int(matched.group(5))

        is_failed = failed > 0 or unreachable > 0
        status = "failed" if is_failed else "success"

        # 提取该 host 的 task 输出片段
        host_output = _extract_host_task_output(lines[: recap_start - 1], host)

        results.append(
            {
                "host": host,
                "status": status,
                "raw_status": "FAILED" if is_failed else "SUCCESS",
                "stdout": host_output if not is_failed else "",
                "stderr": host_output if is_failed else "",
                "exit_code": 1 if is_failed else 0,
                "error_message": host_output if is_failed else "",
            }
        )

    return results


def _extract_host_task_output(lines: list[str], host: str) -> str:
    """从 playbook 输出中提取指定 host 的 task 输出内容（仅提取有意义的值）。"""
    host_lines: list[str] = []
    capturing = False

    for line in lines:
        # 匹配 ok: [host], changed: [host], fatal: [host], skipping: [host] 等
        if re.match(rf"^(ok|changed|fatal|failed|skipping|unreachable):\s+\[{re.escape(host)}\]", line):
            capturing = True
            continue

        # 新 TASK 或 PLAY 行结束当前捕获
        if line.startswith("TASK [") or line.startswith("PLAY [") or line.startswith("PLAY RECAP"):
            capturing = False
            continue

        # task path 行跳过
        if line.startswith("task path:"):
            continue

        if capturing:
            host_lines.append(line)

    # 尝试从 JSON 块中提取 msg/stdout/results 等有意义的内容
    raw_output = "\n".join(host_lines).strip()
    return _extract_meaningful_output(raw_output)


def _extract_meaningful_output(raw_output: str) -> str:
    """从 ansible task 输出中提取有意义的内容（如 msg, stdout, results）。"""
    import json as _json

    # 尝试解析为 JSON 对象
    try:
        data = _json.loads(raw_output)
        if isinstance(data, dict):
            # 优先提取常见字段
            for key in ("msg", "stdout", "stdout_lines", "results"):
                if key in data:
                    val = data[key]
                    if isinstance(val, list):
                        return "\n".join(str(item) for item in val)
                    return str(val)
            # 没有常见字段，返回整个 JSON
            return raw_output
    except (_json.JSONDecodeError, TypeError, ValueError):
        pass

    # 非 JSON，尝试去掉外层花括号内的 JSON 片段
    # 匹配形如 { "msg": "..." } 的内容
    json_match = re.search(r"\{[^{}]*\}", raw_output, re.DOTALL)
    if json_match:
        try:
            data = _json.loads(json_match.group())
            if isinstance(data, dict):
                for key in ("msg", "stdout", "stdout_lines", "results"):
                    if key in data:
                        val = data[key]
                        if isinstance(val, list):
                            return "\n".join(str(item) for item in val)
                        return str(val)
        except (_json.JSONDecodeError, TypeError, ValueError):
            pass

    return raw_output


def _build_host_credentials_inventory(workspace: Path, host_credentials: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for idx, item in enumerate(host_credentials):
        host = str(item.get("host", "")).strip()
        parts = [host]

        user = item.get("user")
        if user:
            parts.append(f"ansible_user={_quote_inventory_value(user)}")

        port = item.get("port")
        if port is not None and str(port).strip() != "":
            parts.append(f"ansible_port={_quote_inventory_value(port)}")

        connection = item.get("connection")
        if connection:
            parts.append(f"ansible_connection={_quote_inventory_value(connection)}")
            if str(connection).strip().lower() == "winrm":
                winrm_scheme = item.get("winrm_scheme")
                if winrm_scheme:
                    parts.append(f"ansible_winrm_scheme={_quote_inventory_value(winrm_scheme)}")

                winrm_transport = item.get("winrm_transport")
                if winrm_transport:
                    parts.append(f"ansible_winrm_transport={_quote_inventory_value(winrm_transport)}")

                if item.get("winrm_cert_validation") is False:
                    parts.append("ansible_winrm_server_cert_validation=ignore")

        password = item.get("password")
        if password:
            parts.append(f"ansible_password={_quote_inventory_value(password)}")
            if str(connection).strip().lower() == "ssh":
                parts.append(f"ansible_ssh_common_args={_quote_inventory_value(_get_password_auth_ssh_common_args(item))}")

        private_key_file = item.get("private_key_file")
        private_key_content = item.get("private_key_content")
        if private_key_content:
            key_file = workspace / f"id_rsa_{idx}"
            key_file.write_text(str(private_key_content), encoding="utf-8")
            os.chmod(key_file, stat.S_IRUSR | stat.S_IWUSR)
            private_key_file = str(key_file)
        if private_key_file:
            parts.append(f"ansible_ssh_private_key_file={_quote_inventory_value(private_key_file)}")

        passphrase = item.get("private_key_passphrase")
        if passphrase:
            parts.append(f"ansible_ssh_passphrase={_quote_inventory_value(passphrase)}")

        lines.append(" ".join(parts))

    if not lines:
        return ""
    return "[all]\n" + "\n".join(lines) + "\n"


def _sanitize_task_id(task_id: str | None) -> str:
    if not task_id:
        return uuid.uuid4().hex
    normalized = re.sub(r"[^A-Za-z0-9._-]", "_", task_id)
    return normalized.strip("._-") or uuid.uuid4().hex


def create_task_workspace(task_id: str | None = None) -> Path:
    BASE_TASK_DIR.mkdir(parents=True, exist_ok=True)
    task_name = _sanitize_task_id(task_id)
    workspace = BASE_TASK_DIR / task_name
    if workspace.exists():
        workspace = BASE_TASK_DIR / f"{task_name}-{uuid.uuid4().hex[:8]}"
    workspace.mkdir(parents=True, exist_ok=False)
    return workspace


def cleanup_workspace(workspace: Path | None) -> None:
    if not workspace:
        return
    base = BASE_TASK_DIR.resolve()
    try:
        target = workspace.resolve()
    except FileNotFoundError:
        return
    if not str(target).startswith(str(base)):
        logger.warning("skip unsafe workspace cleanup: %s", workspace)
        return
    shutil.rmtree(target, ignore_errors=True)


def prepare_adhoc_execution(payload: AdhocRequest) -> tuple[list[str], Path]:
    workspace = create_task_workspace(payload.task_id)
    inventory_value = payload.inventory
    extra_vars = dict(payload.extra_vars or {})

    if payload.private_key_content and not payload.host_credentials:
        private_key_path = _materialize_private_key(workspace, payload.private_key_content)
        extra_vars.setdefault("ansible_ssh_private_key_file", private_key_path)
        if payload.private_key_passphrase:
            extra_vars.setdefault("ansible_ssh_passphrase", payload.private_key_passphrase)

    if payload.inventory_content or payload.host_credentials:
        inventory_file = workspace / "inventory.ini"
        parts: list[str] = []
        if payload.inventory_content:
            parts.append(payload.inventory_content.rstrip("\n"))
        if payload.host_credentials:
            parts.append(_build_host_credentials_inventory(workspace, payload.host_credentials).rstrip("\n"))
        inventory_file.write_text("\n".join([p for p in parts if p]) + "\n", encoding="utf-8")
        inventory_value = str(inventory_file)

    cmd = build_adhoc_command(
        AdhocRequest(
            inventory=inventory_value,
            inventory_content=None,
            hosts=payload.hosts,
            module=payload.module,
            module_args=payload.module_args,
            extra_vars=extra_vars,
            execute_timeout=payload.execute_timeout,
            task_id=payload.task_id,
            callback=payload.callback,
            private_key_content=None,
            private_key_passphrase=None,
            host_credentials=None,
        )
    )
    return cmd, workspace


async def prepare_playbook_execution(
    config: ServiceConfig,
    payload: PlaybookRequest,
) -> tuple[list[str], Path, PlaybookRequest]:
    workspace = create_task_workspace(payload.task_id)
    extra_vars = dict(payload.extra_vars or {})

    logger.info(
        "[prepare_playbook_start] task_id=%s workspace=%s playbook_path=%s "
        "has_playbook_content=%s has_files=%s has_file_distribution=%s "
        "has_host_credentials=%s has_private_key=%s extra_vars_keys=%s timeout=%s",
        payload.task_id,
        workspace,
        payload.playbook_path,
        bool(payload.playbook_content),
        bool(payload.files),
        bool(payload.file_distribution),
        bool(payload.host_credentials),
        bool(payload.private_key_content),
        list((payload.extra_vars or {}).keys()),
        payload.execute_timeout,
    )

    if payload.private_key_content and not payload.host_credentials:
        private_key_path = _materialize_private_key(workspace, payload.private_key_content)
        extra_vars.setdefault("ansible_ssh_private_key_file", private_key_path)
        if payload.private_key_passphrase:
            extra_vars.setdefault("ansible_ssh_passphrase", payload.private_key_passphrase)

    playbook_path = payload.playbook_path
    playbook_content = payload.playbook_content

    # Playbook ZIP 包处理：当有 files 但没有 file_distribution 时，
    # 下载 ZIP 文件并解压到 workspace，playbook_path 指向解压后的入口文件
    if payload.files and not payload.file_distribution:
        logger.info("[prepare_playbook] 开始处理 Playbook ZIP 文件: file_count=%d", len(payload.files))
        for file_item in payload.files:
            bucket_name = str(file_item.get("bucket_name", "")).strip()
            if not bucket_name:
                raise ValueError("file item bucket_name is required")
            logger.info(
                "[prepare_playbook] 下载文件: name=%s file_key=%s bucket=%s",
                file_item.get("name"),
                file_item.get("file_key"),
                bucket_name,
            )
            local_path = await download_object_to_workspace(config, workspace, bucket_name, file_item)
            logger.info("[prepare_playbook] 文件已下载: local_path=%s", local_path)
            if local_path.endswith(".zip"):
                with zipfile.ZipFile(local_path, "r") as zf:
                    namelist = zf.namelist()
                    logger.info("[prepare_playbook] ZIP 内容 (%d 个文件): %s", len(namelist), namelist)
                    zf.extractall(workspace)
                logger.info("[prepare_playbook] ZIP 已解压到: %s", workspace)
                # 列出解压后的 workspace 内容
                all_files = [str(p.relative_to(workspace)) for p in workspace.rglob("*") if p.is_file()]
                logger.info("[prepare_playbook] workspace 文件列表: %s", all_files)
                # 在解压后的内容中查找 playbook.yml 入口文件
                playbook_entry = payload.playbook_path or "playbook.yml"
                # 支持 ZIP 内有顶层目录的情况（如 playbook-template/playbook.yml）
                candidates = list(workspace.rglob(Path(playbook_entry).name))
                logger.info("[prepare_playbook] 查找入口文件 '%s', 候选: %s", playbook_entry, candidates)
                if candidates:
                    playbook_path = str(candidates[0])
                    logger.info("[prepare_playbook] 使用 playbook_path=%s", playbook_path)
                else:
                    raise ValueError(f"ZIP 解压后未找到入口文件: {playbook_entry}")
                # 已通过 ZIP 提供 playbook，清除 playbook_content 避免被覆盖
                playbook_content = None

    if payload.file_distribution:
        bucket_name = str(payload.file_distribution.get("bucket_name", "")).strip()
        target_path = str(payload.file_distribution.get("target_path", "")).strip()
        overwrite = bool(payload.file_distribution.get("overwrite", True))
        if not bucket_name:
            raise ValueError("file_distribution.bucket_name is required")
        if not target_path:
            raise ValueError("file_distribution.target_path is required")

        downloaded_files: list[dict[str, Any]] = []
        for file_item in payload.files or []:
            local_path = await download_object_to_workspace(config, workspace, bucket_name, file_item)
            if local_path.endswith(".zip"):
                with zipfile.ZipFile(local_path, "r") as zip_file:
                    _safe_extract_zip(zip_file, workspace)
            downloaded_files.append({**file_item, "local_path": local_path})
        playbook_content = _build_windows_file_distribution_playbook(downloaded_files, target_path, overwrite)

    if playbook_content:
        playbook_file = workspace / "playbook.yml"
        playbook_file.write_text(playbook_content, encoding="utf-8")
        playbook_path = str(playbook_file)
        logger.info("[prepare_playbook] playbook_content 已写入: %s", playbook_file)

    inventory_value = payload.inventory
    if payload.inventory_content or payload.host_credentials:
        inventory_file = workspace / "inventory.ini"
        parts: list[str] = []
        if payload.inventory_content:
            parts.append(payload.inventory_content.rstrip("\n"))
        if payload.host_credentials:
            logger.info("[prepare_playbook] 构建 host_credentials inventory: %d 个主机", len(payload.host_credentials))
            parts.append(_build_host_credentials_inventory(workspace, payload.host_credentials).rstrip("\n"))
        inventory_file.write_text("\n".join([p for p in parts if p]) + "\n", encoding="utf-8")
        inventory_value = str(inventory_file)
        logger.info("[prepare_playbook] inventory 已写入: %s", inventory_file)

    prepared_payload = PlaybookRequest(
        playbook_path=playbook_path,
        playbook_content=None,
        inventory=inventory_value,
        inventory_content=None,
        extra_vars=extra_vars,
        execute_timeout=payload.execute_timeout,
        task_id=payload.task_id,
        callback=payload.callback,
        private_key_content=None,
        private_key_passphrase=None,
        host_credentials=None,
        files=None,
        file_distribution=None,
    )
    cmd = build_playbook_command(prepared_payload)
    logger.info("[prepare_playbook] 最终命令: %s", " ".join(cmd))
    logger.info(
        "[prepare_playbook] 最终参数: playbook_path=%s inventory=%s extra_vars_keys=%s",
        prepared_payload.playbook_path,
        prepared_payload.inventory,
        list(extra_vars.keys()),
    )
    return cmd, workspace, prepared_payload


def build_adhoc_command(payload: AdhocRequest) -> list[str]:
    extra_vars = dict(payload.extra_vars or {})
    if "ansible_connection" not in extra_vars and payload.hosts in {
        "localhost",
        "127.0.0.1",
    }:
        extra_vars["ansible_connection"] = "local"

    cli_args = [
        payload.hosts,
        "-i",
        payload.inventory,
        "-m",
        payload.module,
    ]
    if payload.module_args:
        cli_args.extend(["-a", payload.module_args])
    if extra_vars:
        cli_args.extend(["--extra-vars", json.dumps(extra_vars, ensure_ascii=False)])
    return [
        *current_entrypoint_command(),
        "--internal-ansible-cli",
        "adhoc",
        "--",
        *cli_args,
    ]


def build_playbook_command(payload: PlaybookRequest) -> list[str]:
    cli_args = [
        payload.playbook_path,
        "-i",
        payload.inventory,
        "-vvv",
    ]
    if payload.extra_vars:
        cli_args.extend(["--extra-vars", json.dumps(payload.extra_vars, ensure_ascii=False)])
    return [
        *current_entrypoint_command(),
        "--internal-ansible-cli",
        "playbook",
        "--",
        *cli_args,
    ]


def build_playbook_list_hosts_command(payload: PlaybookRequest) -> list[str]:
    cli_args = [
        payload.playbook_path,
        "-i",
        payload.inventory,
        "--list-hosts",
        "-vvv",
    ]
    if payload.extra_vars:
        cli_args.extend(["--extra-vars", json.dumps(payload.extra_vars, ensure_ascii=False)])
    return [
        *current_entrypoint_command(),
        "--internal-ansible-cli",
        "playbook",
        "--",
        *cli_args,
    ]


def build_playbook_winrm_preflight_command(payload: PlaybookRequest) -> list[str]:
    cli_args = [
        "all",
        "-i",
        payload.inventory,
        "-m",
        "ansible.windows.win_ping",
    ]
    if payload.extra_vars:
        cli_args.extend(["--extra-vars", json.dumps(payload.extra_vars, ensure_ascii=False)])
    return [
        *current_entrypoint_command(),
        "--internal-ansible-cli",
        "adhoc",
        "--",
        *cli_args,
    ]


async def run_command(cmd: list[str], timeout: int) -> tuple[int, str]:
    process_kwargs: dict[str, Any] = {}
    if os.name == "posix":
        process_kwargs["start_new_session"] = True
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        **process_kwargs,
    )
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        if os.name == "posix":
            with contextlib.suppress(ProcessLookupError):
                os.killpg(proc.pid, signal.SIGKILL)
        else:
            proc.kill()
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(proc.wait(), timeout=5)
        if proc.returncode is None:
            proc.kill()
            await proc.wait()
        logger.error("command timed out: %s", " ".join(shlex.quote(part) for part in cmd))
        return 124, "command timed out"
    output, decode_strategy = decode_command_output(stdout)
    exit_code = proc.returncode or 0
    logger.info(
        "command output log: exit_code=%s strategy=%s bytes=%s raw_prefix=%s decoded_prefix=%r",
        exit_code,
        decode_strategy,
        len(stdout),
        stdout[:32].hex(),
        output[:120],
    )
    return exit_code, output
