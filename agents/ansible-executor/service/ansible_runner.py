import asyncio
import os
import json
import logging
import re
import shlex
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any


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


def to_adhoc_request(payload: dict[str, Any]) -> AdhocRequest:
    inventory = str(payload.get("inventory", "")).strip()
    inventory_content = payload.get("inventory_content")
    if inventory_content is not None and not isinstance(inventory_content, str):
        raise ValueError("inventory_content must be string")
    if not inventory and not inventory_content:
        raise ValueError("inventory or inventory_content is required")

    timeout = int(payload.get("execute_timeout", 60))
    if timeout < 1 or timeout > 3600:
        raise ValueError("execute_timeout must be in [1, 3600]")

    extra_vars = payload.get("extra_vars") or {}
    if not isinstance(extra_vars, dict):
        raise ValueError("extra_vars must be object")

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
    )


def to_playbook_request(payload: dict[str, Any]) -> PlaybookRequest:
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
    if not inventory and not inventory_content:
        raise ValueError("inventory or inventory_content is required")

    timeout = int(payload.get("execute_timeout", 600))
    if timeout < 1 or timeout > 7200:
        raise ValueError("execute_timeout must be in [1, 7200]")

    extra_vars = payload.get("extra_vars") or {}
    if not isinstance(extra_vars, dict):
        raise ValueError("extra_vars must be object")

    return PlaybookRequest(
        playbook_path=playbook_path,
        playbook_content=playbook_content,
        inventory=inventory,
        inventory_content=inventory_content,
        extra_vars=extra_vars,
        execute_timeout=timeout,
        task_id=str(payload.get("task_id", "")).strip() or None,
        callback=payload.get("callback"),
    )


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
    if payload.inventory_content:
        inventory_file = workspace / "inventory.ini"
        inventory_file.write_text(payload.inventory_content, encoding="utf-8")
        inventory_value = str(inventory_file)

    cmd = build_adhoc_command(
        AdhocRequest(
            inventory=inventory_value,
            inventory_content=None,
            hosts=payload.hosts,
            module=payload.module,
            module_args=payload.module_args,
            extra_vars=payload.extra_vars,
            execute_timeout=payload.execute_timeout,
            task_id=payload.task_id,
            callback=payload.callback,
        )
    )
    return cmd, workspace


def prepare_playbook_execution(payload: PlaybookRequest) -> tuple[list[str], Path]:
    workspace = create_task_workspace(payload.task_id)

    playbook_path = payload.playbook_path
    if payload.playbook_content:
        playbook_file = workspace / "playbook.yml"
        playbook_file.write_text(payload.playbook_content, encoding="utf-8")
        playbook_path = str(playbook_file)

    inventory_value = payload.inventory
    if payload.inventory_content:
        inventory_file = workspace / "inventory.ini"
        inventory_file.write_text(payload.inventory_content, encoding="utf-8")
        inventory_value = str(inventory_file)

    cmd = build_playbook_command(
        PlaybookRequest(
            playbook_path=playbook_path,
            playbook_content=None,
            inventory=inventory_value,
            inventory_content=None,
            extra_vars=payload.extra_vars,
            execute_timeout=payload.execute_timeout,
            task_id=payload.task_id,
            callback=payload.callback,
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

    cmd = [
        "ansible",
        payload.hosts,
        "-i",
        payload.inventory,
        "-m",
        payload.module,
    ]
    if payload.module_args:
        cmd.extend(["-a", payload.module_args])
    if extra_vars:
        cmd.extend(["--extra-vars", json.dumps(extra_vars, ensure_ascii=False)])
    return cmd


def build_playbook_command(payload: PlaybookRequest) -> list[str]:
    cmd = [
        "ansible-playbook",
        payload.playbook_path,
        "-i",
        payload.inventory,
    ]
    if payload.extra_vars:
        cmd.extend(["--extra-vars", json.dumps(payload.extra_vars, ensure_ascii=False)])
    return cmd


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
