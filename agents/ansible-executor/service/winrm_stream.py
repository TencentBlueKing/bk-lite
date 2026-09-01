"""复用单个 WinRM shell 增量接收 Windows 脚本输出。"""

import asyncio
import base64
import contextlib
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
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
    decode_command_output,
)
from winrm.exceptions import WinRMOperationTimeoutError
from winrm.protocol import Protocol

ProtocolFactory = Callable[[dict[str, Any]], Protocol]
_SUPPORTED_SCRIPT_TYPES = {"bat", "powershell"}
_SUPPORTED_TRANSPORTS = {"auto", "basic", "certificate", "ntlm", "kerberos", "credssp", "plaintext", "ssl"}


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
        operation_timeout_sec=5,
        read_timeout_sec=10,
        proxy=None,
    )


def _encoded_powershell(script: str) -> str:
    return base64.b64encode(script.encode("utf-16-le")).decode("ascii")


def _build_command(script_content: str, script_type: str) -> tuple[str, list[str]]:
    if script_type not in _SUPPORTED_SCRIPT_TYPES:
        raise ValueError(f"unsupported Windows stream script type: {script_type}")
    if script_type == "powershell":
        encoded = _encoded_powershell(script_content)
    else:
        token = uuid.uuid4().hex
        encoded_script = base64.b64encode(script_content.encode("utf-8")).decode("ascii")
        wrapper = "\n".join(
            [
                f"$path = Join-Path $env:TEMP '.bklite-stream-{token}.cmd'",
                f"$text = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{encoded_script}'))",
                "[IO.File]::WriteAllText($path, $text, [Text.Encoding]::Default)",
                "$exitCode = 1",
                "try {",
                "    & cmd.exe /d /q /c $path",
                "    $exitCode = [int]$LASTEXITCODE",
                "} finally {",
                "    Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue",
                "}",
                "exit $exitCode",
            ]
        )
        encoded = _encoded_powershell(wrapper)
    return (
        "powershell.exe",
        ["-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded],
    )


def _run_host(
    index: int,
    credential: dict[str, Any],
    command: str,
    arguments: list[str],
    timeout: int,
    emit: Callable[[_ThreadEvent], None],
    protocol_factory: ProtocolFactory,
) -> None:
    protocol = None
    shell_id = None
    command_id = None
    exit_code = 1
    deadline = time.monotonic() + timeout
    try:
        protocol = protocol_factory(credential)
        shell_id = protocol.open_shell()
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
                protocol.close_shell(shell_id)
        emit(_ThreadEvent(index, "done", exit_code=exit_code))


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
) -> tuple[int, str, dict[str, Any]]:
    """为每个 Windows 目标建立一个 WinRM shell，在同一会话中持续接收输出。"""
    if not host_credentials:
        raise ValueError("host_credentials are required for WinRM streaming")
    command, arguments = _build_command(script_content, script_type)
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
        asyncio.run_coroutine_threadsafe(queue.put(event), loop).result()

    async def publish_line(line: str) -> None:
        stream_publisher.offer(line)

    workers = [
        asyncio.create_task(
            asyncio.to_thread(
                _run_host,
                index,
                credential,
                command,
                arguments,
                timeout,
                emit,
                protocol_factory,
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
            remaining = max_output_bytes - retained_bytes
            kept = b""
            if remaining > 0:
                kept = event.chunk[:remaining]
                state.retained.extend(kept)
                retained_bytes += len(kept)
            if len(event.chunk) > max(remaining, 0):
                truncated = True
            for line in state.streamer.feed(event.chunk):
                await publish_line(line)

        await asyncio.gather(*workers)
    finally:
        stream_meta = await stream_publisher.close(stream_flush_timeout)
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
