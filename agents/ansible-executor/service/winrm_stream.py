"""WinRM：先连接层 put_file 落文件，再对短命令做流式输出。"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import sys
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from service.ansible_runner import (
    DEFAULT_MAX_OUTPUT_BYTES,
    DEFAULT_STREAM_BATCH_SIZE,
    DEFAULT_STREAM_FLUSH_TIMEOUT,
    DEFAULT_STREAM_MAX_LINE_BYTES,
    DEFAULT_STREAM_QUEUE_SIZE,
    BufferedStreamPublisher,
    LineEventStreamer,
    StreamPublish,
    _write_restricted_bytes,
    cleanup_workspace,
    create_task_workspace,
    decode_command_output,
)
from service.linux_script_delivery import ScriptDeliveryError, format_host_failure
from service.windows_script_delivery import (
    ConnectionOpener,
    copy_windows_script_to_hosts,
    prepare_windows_script_bytes,
    remote_script_leaf,
    stage_local_windows_script,
)
from winrm.exceptions import WinRMOperationTimeoutError
from winrm.protocol import Protocol

_EXECUTOR_ROOT = Path(__file__).resolve().parents[1]

ProtocolFactory = Callable[[dict[str, Any]], Protocol]
WindowsCopier = Callable[..., None]
_SUPPORTED_SCRIPT_TYPES = {"bat", "powershell", "python"}
_SUPPORTED_TRANSPORTS = {"auto", "basic", "certificate", "ntlm", "kerberos", "credssp", "plaintext", "ssl"}
_UNSAFE_INTERPRETER_CHARS = set('|"&<>^%\r\n\t')

# Back-compat names used by older unit tests.
prepare_script_bytes = prepare_windows_script_bytes


@dataclass
class _HostState:
    host: str
    exit_code: int = 1
    retained: bytearray = field(default_factory=bytearray)
    total_bytes: int = 0
    streamer: LineEventStreamer = field(default_factory=LineEventStreamer)


@dataclass(frozen=True)
class _ThreadEvent:
    index: int
    kind: str
    chunk: bytes = b""
    exit_code: int = 1


def _build_protocol(credential: dict[str, Any]) -> Protocol:
    host = str(credential.get("host") or "").strip()
    if not host or any(char.isspace() for char in host) or any(char in host for char in "/@"):
        raise ValueError("invalid WinRM host")

    scheme = str(credential.get("winrm_scheme") or "http").strip().lower()
    if scheme not in {"http", "https"}:
        raise ValueError("winrm_scheme must be http or https")
    port = int(credential.get("port") or (5986 if scheme == "https" else 5985))
    if port < 1 or port > 65535:
        raise ValueError("invalid WinRM port")

    transport = str(credential.get("winrm_transport") or "ntlm").strip().lower()
    if transport not in _SUPPORTED_TRANSPORTS:
        raise ValueError("unsupported WinRM transport")
    cert_validation = "ignore" if credential.get("winrm_cert_validation") is False else "validate"
    return Protocol(
        endpoint=f"{scheme}://{host}:{port}/wsman",
        transport=transport,
        username=str(credential.get("user") or ""),
        password=str(credential.get("password") or ""),
        server_cert_validation=cert_validation,
        operation_timeout_sec=60,
        read_timeout_sec=70,
        proxy=None,
    )


def build_execute_command(
    token: str,
    script_type: str,
    *,
    windows_interpreter: str = "python",
) -> tuple[str, list[str]]:
    """Short remote command that only references the uploaded file path."""
    if script_type not in _SUPPORTED_SCRIPT_TYPES:
        raise ValueError(f"unsupported Windows stream script type: {script_type}")
    leaf = remote_script_leaf(token, script_type)
    if script_type == "powershell":
        return (
            "cmd.exe",
            [
                "/d",
                "/q",
                "/c",
                f'powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%TEMP%\\{leaf}"',
            ],
        )
    if script_type == "python":
        interpreter = str(windows_interpreter or "python").strip() or "python"
        if any(char in _UNSAFE_INTERPRETER_CHARS for char in interpreter):
            raise ValueError("invalid Windows Python interpreter")
        return ("cmd.exe", ["/d", "/q", "/c", f'{interpreter} -u "%TEMP%\\{leaf}"'])
    return ("cmd.exe", ["/d", "/q", "/c", f'"%TEMP%\\{leaf}"'])


def build_cleanup_command(token: str, script_type: str) -> tuple[str, list[str]]:
    leaf = remote_script_leaf(token, script_type)
    return ("cmd.exe", ["/d", "/q", "/c", f'del /f /q "%TEMP%\\{leaf}" >nul 2>nul'])


def _build_command(
    script_content: str,
    script_type: str,
    *,
    windows_interpreter: str = "python",
    token: str | None = None,
) -> tuple[str, list[str]]:
    prepare_windows_script_bytes(script_content, script_type)
    return build_execute_command(token or "testtoken", script_type, windows_interpreter=windows_interpreter)


def _run_command_to_completion(
    protocol: Protocol,
    shell_id: str,
    command: str,
    arguments: list[str],
    deadline: float,
) -> tuple[int, bytes]:
    command_id = protocol.run_command(shell_id, command, arguments)
    collected = bytearray()
    exit_code = 1
    try:
        while True:
            if time.monotonic() >= deadline:
                collected.extend(b"command timed out\n")
                return 124, bytes(collected)
            try:
                stdout, stderr, current_exit_code, command_done = protocol.get_command_output_raw(shell_id, command_id)
            except WinRMOperationTimeoutError:
                continue
            if stdout:
                collected.extend(stdout)
            if stderr:
                collected.extend(stderr)
            if command_done:
                exit_code = current_exit_code
                break
    finally:
        with contextlib.suppress(Exception):
            protocol.cleanup_command(shell_id, command_id)
    return exit_code, bytes(collected)


def _run_host(
    index: int,
    credential: dict[str, Any],
    token: str,
    script_type: str,
    timeout: int,
    emit: Callable[[_ThreadEvent], None],
    protocol_factory: ProtocolFactory,
    windows_interpreter: str,
) -> None:
    protocol = None
    shell_id = None
    command_id = None
    exit_code = 1
    deadline = time.monotonic() + timeout
    try:
        protocol = protocol_factory(credential)
        shell_id = protocol.open_shell()
        command, arguments = build_execute_command(token, script_type, windows_interpreter=windows_interpreter)
        command_id = protocol.run_command(shell_id, command, arguments)
        while True:
            if time.monotonic() >= deadline:
                emit(_ThreadEvent(index, "chunk", b"command timed out\n"))
                exit_code = 124
                break
            try:
                stdout, stderr, current_exit_code, command_done = protocol.get_command_output_raw(shell_id, command_id)
            except WinRMOperationTimeoutError:
                continue
            if stdout:
                emit(_ThreadEvent(index, "chunk", stdout))
            if stderr:
                emit(_ThreadEvent(index, "chunk", stderr))
            if command_done:
                exit_code = current_exit_code
                break
    except Exception as error:  # noqa: BLE001 - 转换为单主机执行结果
        emit(_ThreadEvent(index, "chunk", f"WinRM stream failed: {error}\n".encode("utf-8")))
    finally:
        if protocol is not None and shell_id and command_id:
            with contextlib.suppress(Exception):
                protocol.cleanup_command(shell_id, command_id)
        if protocol is not None and shell_id:
            with contextlib.suppress(Exception):
                cleanup_command, cleanup_arguments = build_cleanup_command(token, script_type)
                _run_command_to_completion(
                    protocol,
                    shell_id,
                    cleanup_command,
                    cleanup_arguments,
                    min(deadline, time.monotonic() + 15),
                )
            with contextlib.suppress(Exception):
                protocol.close_shell(shell_id)
        emit(_ThreadEvent(index, "done", exit_code=exit_code))


async def _copy_windows_script_via_subprocess(
    workspace: Path,
    local_path: str,
    leaf: str,
    script_type: str,
    host_credentials: list[dict[str, Any]],
) -> None:
    hosts = [str(item.get("host") or "") for item in host_credentials if item.get("host")]
    payload_path = workspace / "windows-put-file-job.json"
    _write_restricted_bytes(
        payload_path,
        json.dumps(
            {
                "local_path": local_path,
                "leaf": leaf,
                "script_type": script_type,
                "host_credentials": host_credentials,
            },
            ensure_ascii=False,
        ).encode("utf-8"),
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join([str(_EXECUTOR_ROOT), *[p for p in env.get("PYTHONPATH", "").split(os.pathsep) if p]])
    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "service.windows_script_delivery",
            str(payload_path),
            cwd=str(_EXECUTOR_ROOT),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            detail = (stderr or b"").decode("utf-8", errors="replace").strip() or "Windows put_file subprocess failed"
            failure = ScriptDeliveryError(detail, hosts)
            failure.host_output = format_host_failure(hosts, detail)
            raise failure
    finally:
        with contextlib.suppress(Exception):
            payload_path.unlink(missing_ok=True)


async def run_winrm_stream(
    host_credentials: list[dict[str, Any]],
    *,
    script_content: str,
    script_type: str,
    timeout: int,
    stream_publish: StreamPublish,
    stream_log_topic: str,
    execution_id: str,
    max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
    protocol_factory: ProtocolFactory = _build_protocol,
    stream_queue_size: int = DEFAULT_STREAM_QUEUE_SIZE,
    stream_batch_size: int = DEFAULT_STREAM_BATCH_SIZE,
    stream_flush_timeout: float = DEFAULT_STREAM_FLUSH_TIMEOUT,
    stream_max_line_bytes: int = DEFAULT_STREAM_MAX_LINE_BYTES,
    windows_interpreter: str = "python",
    skip_put_file: bool = False,
    copy_token: str | None = None,
    script_copier: WindowsCopier | None = None,
    connection_opener: ConnectionOpener | None = None,
) -> tuple[int, str, dict[str, Any]]:
    """WinRM put_file 上传脚本 → 短命令流式执行 → 清理远端与本地临时文件。"""
    if not host_credentials:
        raise ValueError("host_credentials are required for WinRM streaming")
    if script_type not in _SUPPORTED_SCRIPT_TYPES:
        raise ValueError(f"unsupported Windows stream script type: {script_type}")

    script_bytes = prepare_windows_script_bytes(script_content, script_type)
    token = copy_token or uuid.uuid4().hex
    leaf = remote_script_leaf(token, script_type)
    workspace: Path | None = None

    started = time.monotonic()
    if not skip_put_file:
        workspace = create_task_workspace(execution_id)
        try:
            local_script = stage_local_windows_script(workspace, script_bytes, script_type)
            # 注入 copier/opener（单测）走进程内；默认子进程投递，避免 executor event loop 内 WinRM stdin 挂死。
            if script_copier is not None:
                script_copier(
                    str(local_script),
                    leaf,
                    script_type,
                    list(host_credentials),
                )
            elif connection_opener is not None:
                copy_windows_script_to_hosts(
                    str(local_script),
                    leaf,
                    script_type,
                    list(host_credentials),
                    connection_opener=connection_opener,
                )
            else:
                await _copy_windows_script_via_subprocess(
                    workspace,
                    str(local_script),
                    leaf,
                    script_type,
                    list(host_credentials),
                )
        except Exception:
            cleanup_workspace(workspace)
            workspace = None
            raise

    remaining = max(1, int(timeout - (time.monotonic() - started)))
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[_ThreadEvent] = asyncio.Queue(maxsize=max(4, len(host_credentials) * 2))
    states = [
        _HostState(
            host=str(item.get("host") or ""),
            streamer=LineEventStreamer(max_line_bytes=stream_max_line_bytes),
        )
        for item in host_credentials
    ]
    retained_bytes = 0
    truncated = False
    stream_publisher = BufferedStreamPublisher(
        stream_publish,
        stream_log_topic,
        execution_id,
        queue_size=stream_queue_size,
        batch_size=stream_batch_size,
    )
    stream_publisher.start()

    def emit(event: _ThreadEvent) -> None:
        asyncio.run_coroutine_threadsafe(queue.put(event), loop).result(timeout=max(5, min(remaining, 30)))

    async def publish_line(line: str) -> None:
        stream_publisher.offer(line)

    workers = [
        asyncio.create_task(
            asyncio.to_thread(
                _run_host,
                index,
                credential,
                token,
                script_type,
                remaining,
                emit,
                protocol_factory,
                windows_interpreter,
            )
        )
        for index, credential in enumerate(host_credentials)
    ]
    completed = 0
    stream_meta: dict[str, Any] = {}
    try:
        while completed < len(states):
            event = await queue.get()
            state = states[event.index]
            if event.kind == "done":
                state.exit_code = event.exit_code
                trailing = state.streamer.flush()
                if trailing is not None:
                    await publish_line(trailing)
                completed += 1
                continue

            state.total_bytes += len(event.chunk)
            remaining_bytes = max_output_bytes - retained_bytes
            kept = b""
            if remaining_bytes > 0:
                kept = event.chunk[:remaining_bytes]
                state.retained.extend(kept)
                retained_bytes += len(kept)
            if len(event.chunk) > max(remaining_bytes, 0):
                truncated = True
            for line in state.streamer.feed(event.chunk):
                await publish_line(line)

        await asyncio.gather(*workers)
    finally:
        stream_meta = await stream_publisher.close(stream_flush_timeout)
        cleanup_workspace(workspace)

    output_parts = []
    for state in states:
        raw_status = "CHANGED" if state.exit_code == 0 else "FAILED"
        host_output, _ = decode_command_output(bytes(state.retained))
        output_parts.append(f"{state.host} | {raw_status} | rc={state.exit_code} >>\n{host_output.rstrip()}")
    output = "\n".join(output_parts)
    total_bytes = sum(state.total_bytes for state in states)
    code = 0 if states and all(state.exit_code == 0 for state in states) else 1
    return (
        code,
        output,
        {
            "truncated": truncated,
            "output_bytes_total": total_bytes,
            "output_bytes_retained": retained_bytes,
            "output_max_bytes": max_output_bytes,
            "stream_line_chunks": sum(state.streamer.chunked_lines for state in states),
            **stream_meta,
        },
    )
