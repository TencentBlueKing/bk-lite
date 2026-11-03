"""让技能沙箱按 UTF-8 读取子进程输出。

deepagents ``LocalShellBackend.execute`` 使用 ``subprocess.run(text=True)``，
在中文 Windows 上按系统 ANSI 代码页（GBK）解码管道。ppt-master 会把
stdout/stderr 重配成 UTF-8，读线程遇到非 GBK 字节会抛 ``UnicodeDecodeError``，
命令的真实输出因此丢失。
"""

from __future__ import annotations

import subprocess
from typing import Any

from deepagents.backends.local_shell import LocalShellBackend
from deepagents.backends.protocol import ExecuteResponse


def bind_utf8_execute(backend: Any) -> None:
    """只替换真正的 LocalShellBackend。测试里的 MagicMock 保持原样。"""
    if type(backend) is not LocalShellBackend:
        return

    def execute(command: str, *, timeout: int | None = None) -> ExecuteResponse:
        return execute_utf8(backend, command, timeout=timeout)

    backend.execute = execute


def execute_utf8(backend: LocalShellBackend, command: str, *, timeout: int | None = None) -> ExecuteResponse:
    """与 LocalShellBackend.execute 相同，管道按 UTF-8 解码，非法字节替换。"""
    if not command or not isinstance(command, str):
        return ExecuteResponse(
            output="Error: Command must be a non-empty string.",
            exit_code=1,
            truncated=False,
        )

    effective_timeout = timeout if timeout is not None else backend._default_timeout
    if effective_timeout <= 0:
        msg = f"timeout must be positive, got {effective_timeout}"
        raise ValueError(msg)

    try:
        result = subprocess.run(  # noqa: S602
            command,
            check=False,
            shell=True,
            capture_output=True,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=effective_timeout,
            env=backend._env,
            cwd=str(backend.cwd),
        )
    except subprocess.TimeoutExpired:
        if timeout is not None:
            msg = f"Error: Command timed out after {effective_timeout} seconds (custom timeout). The command may be stuck or require more time."
        else:
            msg = f"Error: Command timed out after {effective_timeout} seconds. For long-running commands, re-run using the timeout parameter."
        return ExecuteResponse(output=msg, exit_code=124, truncated=False)
    except Exception as exc:  # noqa: BLE001
        return ExecuteResponse(
            output=f"Error executing command ({type(exc).__name__}): {exc}",
            exit_code=1,
            truncated=False,
        )

    output_parts: list[str] = []
    if result.stdout:
        output_parts.append(result.stdout)
    if result.stderr:
        stderr_lines = result.stderr.strip().split("\n")
        output_parts.extend(f"[stderr] {line}" for line in stderr_lines)

    output = "\n".join(output_parts) if output_parts else "<no output>"
    truncated = False
    if len(output) > backend._max_output_bytes:
        output = output[: backend._max_output_bytes]
        output += f"\n\n... Output truncated at {backend._max_output_bytes} bytes."
        truncated = True
    if result.returncode != 0:
        output = f"{output.rstrip()}\n\nExit code: {result.returncode}"
    return ExecuteResponse(output=output, exit_code=result.returncode, truncated=truncated)
