import asyncio
import json
import logging
import os
import re
import shlex
import shutil
import stat
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
        raise ValueError(
            "inventory or inventory_content or host_credentials is required"
        )
    if inventory and host_credentials and not inventory_content:
        raise ValueError(
            "inventory path with host_credentials is ambiguous, use inventory_content or only host_credentials"
        )

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
    if private_key_passphrase is not None and not isinstance(
        private_key_passphrase, str
    ):
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
    if not playbook_path and not playbook_content:
        raise ValueError("playbook_path or playbook_content is required")
    if not inventory and not inventory_content and not host_credentials:
        raise ValueError(
            "inventory or inventory_content or host_credentials is required"
        )
    if inventory and host_credentials and not inventory_content:
        raise ValueError(
            "inventory path with host_credentials is ambiguous, use inventory_content or only host_credentials"
        )

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
    if private_key_passphrase is not None and not isinstance(
        private_key_passphrase, str
    ):
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
    )


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


def _build_host_credentials_inventory(
    workspace: Path, host_credentials: list[dict[str, Any]]
) -> str:
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

        password = item.get("password")
        if password:
            parts.append(f"ansible_password={_quote_inventory_value(password)}")
            if str(connection).strip().lower() == "ssh":
                parts.append(
                    "ansible_ssh_common_args="
                    f"{_quote_inventory_value(_get_password_auth_ssh_common_args(item))}"
                )

        private_key_file = item.get("private_key_file")
        private_key_content = item.get("private_key_content")
        if private_key_content:
            key_file = workspace / f"id_rsa_{idx}"
            key_file.write_text(str(private_key_content), encoding="utf-8")
            os.chmod(key_file, stat.S_IRUSR | stat.S_IWUSR)
            private_key_file = str(key_file)
        if private_key_file:
            parts.append(
                f"ansible_ssh_private_key_file={_quote_inventory_value(private_key_file)}"
            )

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
        private_key_path = _materialize_private_key(
            workspace, payload.private_key_content
        )
        extra_vars.setdefault("ansible_ssh_private_key_file", private_key_path)
        if payload.private_key_passphrase:
            extra_vars.setdefault(
                "ansible_ssh_passphrase", payload.private_key_passphrase
            )

    if payload.inventory_content or payload.host_credentials:
        inventory_file = workspace / "inventory.ini"
        parts: list[str] = []
        if payload.inventory_content:
            parts.append(payload.inventory_content.rstrip("\n"))
        if payload.host_credentials:
            parts.append(
                _build_host_credentials_inventory(
                    workspace, payload.host_credentials
                ).rstrip("\n")
            )
        inventory_file.write_text(
            "\n".join([p for p in parts if p]) + "\n", encoding="utf-8"
        )
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


def prepare_playbook_execution(payload: PlaybookRequest) -> tuple[list[str], Path]:
    workspace = create_task_workspace(payload.task_id)
    extra_vars = dict(payload.extra_vars or {})

    if payload.private_key_content and not payload.host_credentials:
        private_key_path = _materialize_private_key(
            workspace, payload.private_key_content
        )
        extra_vars.setdefault("ansible_ssh_private_key_file", private_key_path)
        if payload.private_key_passphrase:
            extra_vars.setdefault(
                "ansible_ssh_passphrase", payload.private_key_passphrase
            )

    playbook_path = payload.playbook_path
    if payload.playbook_content:
        playbook_file = workspace / "playbook.yml"
        playbook_file.write_text(payload.playbook_content, encoding="utf-8")
        playbook_path = str(playbook_file)

    inventory_value = payload.inventory
    if payload.inventory_content or payload.host_credentials:
        inventory_file = workspace / "inventory.ini"
        parts: list[str] = []
        if payload.inventory_content:
            parts.append(payload.inventory_content.rstrip("\n"))
        if payload.host_credentials:
            parts.append(
                _build_host_credentials_inventory(
                    workspace, payload.host_credentials
                ).rstrip("\n")
            )
        inventory_file.write_text(
            "\n".join([p for p in parts if p]) + "\n", encoding="utf-8"
        )
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
        cli_args.extend(
            ["--extra-vars", json.dumps(payload.extra_vars, ensure_ascii=False)]
        )
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
