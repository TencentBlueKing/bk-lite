import asyncio
import importlib
import json
import logging
import os
import re
import shlex
import shutil
import ssl
import stat
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from service.runtime import current_entrypoint_command

logger = logging.getLogger(__name__)
BASE_TASK_DIR = Path(os.getenv("ANSIBLE_WORK_DIR", "/tmp/ansible-executor"))


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

    logger.info(
        "to_playbook_request payload check: "
        "task_id=%s "
        "playbook_path=%r "
        "playbook_content_is_none=%s "
        "inventory=%r "
        "inventory_content_is_none=%s "
        "host_credentials_count=%s "
        "files_count=%s "
        "file_distribution=%r "
        "payload_keys=%s",
        payload.get("task_id", ""),
        playbook_path,
        playbook_content is None,
        inventory,
        inventory_content is None,
        len(host_credentials),
        len(files),
        file_distribution,
        sorted(payload.keys()),
    )

    if not playbook_path and not playbook_content and not file_distribution:
        logger.error(
            "to_playbook_request validation failed: "
            "missing playbook_path/playbook_content/file_distribution "
            "task_id=%s "
            "raw_file_distribution=%r "
            "raw_payload=%r",
            payload.get("task_id", ""),
            payload.get("file_distribution"),
            payload,
        )
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


async def download_object_to_workspace(workspace: Path, bucket_name: str, file_item: dict[str, Any]) -> str:
    file_key = str(file_item.get("file_key", "")).strip()
    file_name = str(file_item.get("name", "")).strip() or Path(file_key).name
    if not file_key:
        raise ValueError("file_key is required")
    if not file_name:
        raise ValueError("file name is required")

    nats_client_module = importlib.import_module("nats.aio.client")
    nc = nats_client_module.Client()

    connect_kwargs: dict[str, Any] = {
        "servers": [item.strip() for item in os.getenv("NATS_SERVERS", "").split(",") if item.strip()],
        "connect_timeout": int(os.getenv("NATS_CONNECT_TIMEOUT", "5")),
        "name": "ansible-executor-object-store",
    }
    if not connect_kwargs["servers"]:
        raise ValueError("NATS_SERVERS is required for object store download")

    nats_username = os.getenv("NATS_USERNAME", "")
    nats_password = os.getenv("NATS_PASSWORD", "")
    if nats_username:
        connect_kwargs["user"] = nats_username
    if nats_password:
        connect_kwargs["password"] = nats_password

    if os.getenv("NATS_PROTOCOL", "nats").lower() == "tls":
        tls_context = ssl.create_default_context()
        nats_tls_ca_file = os.getenv("NATS_TLS_CA_FILE", "")
        if nats_tls_ca_file:
            tls_context.load_verify_locations(cafile=nats_tls_ca_file)
        connect_kwargs["tls"] = tls_context

    await nc.connect(**connect_kwargs)
    try:
        js = nc.jetstream(timeout=120)
        object_store = await js.object_store(bucket_name)
        destination = workspace / file_name
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("wb") as target_file:
            await object_store.get(file_key, writeinto=target_file)
        return str(destination)
    finally:
        await nc.close()


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
                parts.append("ansible_ssh_common_args=" f"{_quote_inventory_value(_get_password_auth_ssh_common_args(item))}")

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

    return "\n".join(lines) + ("\n" if lines else "")


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
    payload: PlaybookRequest,
) -> tuple[list[str], Path]:
    workspace = create_task_workspace(payload.task_id)
    extra_vars = dict(payload.extra_vars or {})

    if payload.private_key_content and not payload.host_credentials:
        private_key_path = _materialize_private_key(workspace, payload.private_key_content)
        extra_vars.setdefault("ansible_ssh_private_key_file", private_key_path)
        if payload.private_key_passphrase:
            extra_vars.setdefault("ansible_ssh_passphrase", payload.private_key_passphrase)

    playbook_path = payload.playbook_path
    playbook_content = payload.playbook_content
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
            local_path = await download_object_to_workspace(workspace, bucket_name, file_item)
            downloaded_files.append({**file_item, "local_path": local_path})
        playbook_content = _build_windows_file_distribution_playbook(downloaded_files, target_path, overwrite)

    if playbook_content:
        playbook_file = workspace / "playbook.yml"
        playbook_file.write_text(playbook_content, encoding="utf-8")
        playbook_path = str(playbook_file)

    inventory_value = payload.inventory
    if payload.inventory_content or payload.host_credentials:
        inventory_file = workspace / "inventory.ini"
        parts: list[str] = []
        if payload.inventory_content:
            parts.append(payload.inventory_content.rstrip("\n"))
        if payload.host_credentials:
            parts.append(_build_host_credentials_inventory(workspace, payload.host_credentials).rstrip("\n"))
        inventory_file.write_text("\n".join([p for p in parts if p]) + "\n", encoding="utf-8")
        inventory_value = str(inventory_file)

    cmd = build_playbook_command(
        PlaybookRequest(
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
    )
    return cmd, workspace


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


async def run_command(cmd: list[str], timeout: int) -> tuple[int, str]:
    logger.info("execute command: %s", " ".join(shlex.quote(part) for part in cmd))
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return 124, "command timed out"
    return proc.returncode or 0, stdout.decode("utf-8", errors="replace")
