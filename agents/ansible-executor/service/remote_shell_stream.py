"""通过 Ansible 控制连接增量采集 Linux 远端 shell 输出。"""

import asyncio
import base64
import binascii
import contextlib
import math
import re
import shlex
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from core.config import logger
from service.ansible_runner import (
    DEFAULT_STREAM_BATCH_SIZE,
    DEFAULT_STREAM_FLUSH_TIMEOUT,
    DEFAULT_STREAM_MAX_LINE_BYTES,
    DEFAULT_STREAM_QUEUE_SIZE,
    DEFAULT_MAX_OUTPUT_BYTES,
    BufferedStreamPublisher,
    LineEventStreamer,
    StreamPublish,
    parse_ansible_output_per_host,
    run_command,
)

CommandRunner = Callable[..., Awaitable[tuple[int, str, dict[str, Any]]]]
Sleep = Callable[[float], Awaitable[None]]

_CHUNK_MARKER = "__BKLITE_STREAM_CHUNK__"
_STATUS_MARKER = "__BKLITE_STREAM_STATUS__"
_STARTED_MARKER = "__BKLITE_STREAM_STARTED__"
_RUNNING_STATUS = "RUNNING"


@dataclass
class _HostState:
    host: str
    running: bool = True
    exit_code: int | None = None
    retained: bytearray = field(default_factory=bytearray)
    total_bytes: int = 0
    streamer: LineEventStreamer = field(default_factory=LineEventStreamer)


async def _mark_running_hosts_timed_out(states: dict[str, _HostState], append_chunk: Callable) -> None:
    for state in states.values():
        if state.running:
            state.running = False
            state.exit_code = 124
            await append_chunk(state, b"command timed out\n")


def _replace_adhoc_action(command: list[str], module: str, module_args: str) -> list[str]:
    """复制 ad-hoc 命令并替换模块/参数，控制命令不打开 verbose 输出。"""
    updated = [part for part in command if not re.fullmatch(r"-v+", part)]
    try:
        module_index = updated.index("-m") + 1
        args_index = updated.index("-a") + 1
    except (ValueError, IndexError) as error:
        raise ValueError("invalid ansible ad-hoc command") from error
    updated[module_index] = module
    updated[args_index] = module_args
    return updated


def _build_remote_commands(
    script_content: str,
    shell_executable: str,
    max_output_bytes: int,
) -> tuple[str, str, str, str]:
    token = uuid.uuid4().hex
    remote_dir = f"/tmp/.bklite-stream-{token}"
    script_path = f"{remote_dir}/script"
    output_path = f"{remote_dir}/output"
    cursor_path = f"{remote_dir}/cursor"
    status_path = f"{remote_dir}/status"
    pid_path = f"{remote_dir}/pid"
    runner_path = f"{remote_dir}/runner"
    fifo_path = f"{remote_dir}/output.fifo"
    overflow_path = f"{remote_dir}/overflow"

    encoded_script = base64.b64encode(script_content.encode("utf-8")).decode("ascii")
    runner = "\n".join(
        [
            "#!/bin/sh",
            "set +e",
            f"printf '%s\\n' \"$$\" > {shlex.quote(pid_path)}",
            f"mkfifo {shlex.quote(fifo_path)}",
            "("
            f"dd bs=1 count={max_output_bytes} 2>/dev/null; "
            f"dd bs=1 count=1 of={shlex.quote(overflow_path)} 2>/dev/null; "
            "cat >/dev/null"
            f") < {shlex.quote(fifo_path)} > {shlex.quote(output_path)} &",
            "drainer=$!",
            f"{shlex.quote(shell_executable)} {shlex.quote(script_path)} > {shlex.quote(fifo_path)} 2>&1",
            "result=$?",
            'wait "$drainer" 2>/dev/null || true',
            f"rm -f {shlex.quote(fifo_path)}",
            f"if [ -s {shlex.quote(overflow_path)} ]; then " f"printf '\\n...[output truncated]\\n' >> {shlex.quote(output_path)}; fi",
            f"printf '%s\\n' \"$result\" > {shlex.quote(status_path)}.tmp",
            f"mv -f {shlex.quote(status_path)}.tmp {shlex.quote(status_path)}",
        ]
    )
    encoded_runner = base64.b64encode(runner.encode("utf-8")).decode("ascii")

    start_command = "\n".join(
        [
            "set -e",
            "umask 077",
            f"mkdir {shlex.quote(remote_dir)}",
            f"printf %s {shlex.quote(encoded_script)} | base64 -d > {shlex.quote(script_path)}",
            f"printf %s {shlex.quote(encoded_runner)} | base64 -d > {shlex.quote(runner_path)}",
            f"chmod 700 {shlex.quote(script_path)} {shlex.quote(runner_path)}",
            "if command -v setsid >/dev/null 2>&1; then "
            f"nohup setsid -f /bin/sh {shlex.quote(runner_path)} >/dev/null 2>&1 < /dev/null; "
            "else "
            f"nohup /bin/sh {shlex.quote(runner_path)} >/dev/null 2>&1 < /dev/null & "
            f"printf '%s\\n' \"$!\" > {shlex.quote(pid_path)}; "
            "fi",
            "attempt=0",
            f"while [ ! -s {shlex.quote(pid_path)} ]; do " 'attempt=$((attempt + 1)); [ "$attempt" -lt 5 ] || exit 1; sleep 1; done',
            f"printf '%s\\n' {_STARTED_MARKER}",
        ]
    )
    poll_command = "\n".join(
        [
            f"output={shlex.quote(output_path)}",
            f"cursor={shlex.quote(cursor_path)}",
            "size=0",
            'if [ -f "$output" ]; then size=$(wc -c < "$output" | tr -d " "); fi',
            "offset=0",
            'if [ -f "$cursor" ]; then offset=$(cat "$cursor" 2>/dev/null || printf 0); fi',
            'case "$offset" in (*[!0-9]*|"") offset=0;; esac',
            'case "$size" in (*[!0-9]*|"") size=0;; esac',
            f"printf '%s\\n' {_CHUNK_MARKER}",
            'if [ "$size" -gt "$offset" ]; then '
            "count=$((size - offset)); "
            'dd if="$output" bs=1 skip="$offset" count="$count" 2>/dev/null | base64 | tr -d "\\n"; '
            "fi",
            "printf '\\n%s\\n' " + _STATUS_MARKER,
            f"if [ -f {shlex.quote(status_path)} ]; then " f"cat {shlex.quote(status_path)}; else printf '%s\\n' {_RUNNING_STATUS}; fi",
            'printf "%s\\n" "$size" > "$cursor"',
        ]
    )

    stop_command = "\n".join(
        [
            f"status={shlex.quote(status_path)}",
            f"pid_file={shlex.quote(pid_path)}",
            f"runner={shlex.quote(runner_path)}",
            'if [ ! -f "$status" ] && [ -f "$pid_file" ]; then',
            '  pid=$(cat "$pid_file" 2>/dev/null || true)',
            '  case "$pid" in',
            '    (*[!0-9]*|"") ;;',
            "    (*)",
            '      if [ -r "/proc/$pid/cmdline" ] ' '        && tr "\\000" " " < "/proc/$pid/cmdline" | grep -aF -- "$runner" >/dev/null; then',
            '        kill -- -"$pid" 2>/dev/null || kill "$pid" 2>/dev/null || true',
            "      fi",
            "      ;;",
            "  esac",
            "fi",
            f"rm -rf {shlex.quote(remote_dir)}",
        ]
    )
    return start_command, poll_command, stop_command, remote_dir


def _parse_poll_body(body: str) -> tuple[bytes, str]:
    if _CHUNK_MARKER not in body or _STATUS_MARKER not in body:
        raise ValueError("remote stream response markers missing")
    encoded, status = body.split(_CHUNK_MARKER, 1)[1].split(_STATUS_MARKER, 1)
    encoded = "".join(encoded.split())
    chunk = base64.b64decode(encoded, validate=True) if encoded else b""
    status_value = status.strip().splitlines()[0] if status.strip() else ""
    if status_value != _RUNNING_STATUS:
        try:
            int(status_value)
        except ValueError as error:
            raise ValueError("invalid remote stream status") from error
    return chunk, status_value


async def run_remote_shell_stream(
    base_command: list[str],
    *,
    script_content: str,
    shell_executable: str,
    timeout: int,
    stream_publish: StreamPublish,
    stream_log_topic: str,
    execution_id: str,
    max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
    poll_interval: float = 1.0,
    command_runner: CommandRunner = run_command,
    sleep: Sleep = asyncio.sleep,
    stream_queue_size: int = DEFAULT_STREAM_QUEUE_SIZE,
    stream_batch_size: int = DEFAULT_STREAM_BATCH_SIZE,
    stream_flush_timeout: float = DEFAULT_STREAM_FLUSH_TIMEOUT,
    stream_max_line_bytes: int = DEFAULT_STREAM_MAX_LINE_BYTES,
) -> tuple[int, str, dict[str, Any]]:
    """后台执行 Linux 远端脚本，并通过短 Ansible 轮询实时发布新增日志行。"""
    start_args, poll_args, stop_args, remote_dir = _build_remote_commands(
        script_content,
        shell_executable,
        max_output_bytes,
    )
    start_command = _replace_adhoc_action(base_command, "shell", start_args)
    poll_command = _replace_adhoc_action(base_command, "shell", poll_args)
    stop_command = _replace_adhoc_action(base_command, "shell", stop_args)
    deadline = asyncio.get_running_loop().time() + timeout
    states: dict[str, _HostState] = {}
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
    stream_meta: dict[str, Any] = {}

    async def publish_line(line: str) -> None:
        stream_publisher.offer(line)

    async def append_chunk(state: _HostState, chunk: bytes) -> None:
        nonlocal retained_bytes, truncated
        state.total_bytes += len(chunk)
        remaining = max_output_bytes - retained_bytes
        if remaining > 0:
            kept = chunk[:remaining]
            state.retained.extend(kept)
            retained_bytes += len(kept)
        if len(chunk) > max(remaining, 0):
            truncated = True
        for line in state.streamer.feed(chunk):
            await publish_line(line)

    try:
        start_timeout = max(1, math.ceil(deadline - asyncio.get_running_loop().time()))
        start_code, start_output, _ = await command_runner(start_command, start_timeout)
        start_results = parse_ansible_output_per_host(start_output)
        for result in start_results:
            host = str(result.get("host", ""))
            state = _HostState(host=host, streamer=LineEventStreamer(max_line_bytes=stream_max_line_bytes))
            if result.get("status") != "success" or _STARTED_MARKER not in str(result.get("stdout", "")):
                state.running = False
                state.exit_code = int(result.get("exit_code") or 1)
                await append_chunk(state, str(result.get("stderr") or result.get("stdout") or "start failed").encode("utf-8"))
            states[host] = state
        if not states:
            stream_meta = await stream_publisher.close(stream_flush_timeout)
            return (
                start_code or 1,
                start_output,
                {
                    "truncated": False,
                    "output_bytes_total": len(start_output.encode("utf-8")),
                    "output_bytes_retained": len(start_output.encode("utf-8")),
                    "output_max_bytes": max_output_bytes,
                    "stream_line_chunks": 0,
                    **stream_meta,
                },
            )

        while any(state.running for state in states.values()):
            remaining_seconds = deadline - asyncio.get_running_loop().time()
            if remaining_seconds <= 0:
                await _mark_running_hosts_timed_out(states, append_chunk)
                break

            poll_timeout = max(1, math.ceil(remaining_seconds))
            poll_code, poll_output, _ = await command_runner(poll_command, poll_timeout)
            poll_results = {str(item.get("host", "")): item for item in parse_ansible_output_per_host(poll_output)}
            for host, state in states.items():
                if not state.running:
                    continue
                result = poll_results.get(host)
                if result is None or result.get("status") != "success":
                    if poll_code != 0:
                        state.running = False
                        state.exit_code = int((result or {}).get("exit_code") or poll_code or 1)
                        message = str((result or {}).get("stderr") or poll_output or "stream poll failed")
                        await append_chunk(state, message.encode("utf-8"))
                    continue
                try:
                    chunk, remote_status = _parse_poll_body(str(result.get("stdout", "")))
                except (ValueError, binascii.Error) as error:
                    state.running = False
                    state.exit_code = 1
                    await append_chunk(state, f"stream poll failed: {error}\n".encode("utf-8"))
                    continue
                await append_chunk(state, chunk)
                if remote_status != _RUNNING_STATUS:
                    state.running = False
                    state.exit_code = int(remote_status)
                    trailing = state.streamer.flush()
                    if trailing is not None:
                        await publish_line(trailing)

            if any(state.running for state in states.values()):
                await sleep(poll_interval)
    finally:
        with contextlib.suppress(Exception):
            await command_runner(stop_command, min(timeout, 30))
        stream_meta = await stream_publisher.close(stream_flush_timeout)
        logger.info("remote stream workspace cleaned: %s", remote_dir)

    output_parts: list[str] = []
    for state in states.values():
        exit_code = state.exit_code if state.exit_code is not None else 1
        raw_status = "CHANGED" if exit_code == 0 else "FAILED"
        host_output = state.retained.decode("utf-8", errors="replace").rstrip("\n")
        output_parts.append(f"{state.host} | {raw_status} | rc={exit_code} >>\n{host_output}")

    output = "\n".join(output_parts)
    total_bytes = sum(state.total_bytes for state in states.values())
    code = 0 if states and all(state.exit_code == 0 for state in states.values()) else 1
    return (
        code,
        output,
        {
            "truncated": truncated,
            "output_bytes_total": total_bytes,
            "output_bytes_retained": retained_bytes,
            "output_max_bytes": max_output_bytes,
            "stream_line_chunks": sum(state.streamer.chunked_lines for state in states.values()),
            **stream_meta,
        },
    )
