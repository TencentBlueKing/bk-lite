"""混选 Linux+Windows 同一份 Python：两侧并行脚本流式，仍一次汇总结果。"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path
from typing import Any

from service.ansible_runner import (
    AdhocRequest,
    StreamPublish,
    _build_heredoc_command,
    _resolve_python_interpreter,
    _windows_python_executable,
    prepare_adhoc_execution,
)
from service.linux_script_delivery import ScriptDeliveryError
from service.remote_shell_stream import run_remote_shell_stream
from service.winrm_stream import run_winrm_stream


async def _noop_publish(_subject: str, _data: bytes) -> None:
    return None


def _split_credentials(host_credentials: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    linux_credentials = [item for item in host_credentials if str(item.get("connection", "ssh")).strip().lower() != "winrm"]
    windows_credentials = [item for item in host_credentials if str(item.get("connection", "")).strip().lower() == "winrm"]
    return linux_credentials, windows_credentials


def _merge_stream_meta(*metas: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {
        "truncated": False,
        "output_bytes_total": 0,
        "output_bytes_retained": 0,
        "output_max_bytes": 0,
        "stream_lines_dropped": 0,
        "stream_publish_failures": 0,
        "stream_flush_timed_out": False,
        "stream_line_chunks": 0,
    }
    for meta in metas:
        merged["truncated"] = bool(merged["truncated"] or meta.get("truncated"))
        merged["stream_flush_timed_out"] = bool(merged["stream_flush_timed_out"] or meta.get("stream_flush_timed_out"))
        for key in (
            "output_bytes_total",
            "output_bytes_retained",
            "stream_lines_dropped",
            "stream_publish_failures",
            "stream_line_chunks",
        ):
            merged[key] = int(merged[key]) + int(meta.get(key, 0) or 0)
        max_bytes = int(meta.get("output_max_bytes", 0) or 0)
        if max_bytes > int(merged["output_max_bytes"]):
            merged["output_max_bytes"] = max_bytes
    return merged


def _format_side_exception(hosts: list[dict[str, Any]], error: BaseException) -> tuple[int, str, dict[str, Any]]:
    message = str(error)
    if isinstance(error, ScriptDeliveryError):
        return 1, error.host_output, {"truncated": False, "output_bytes_total": 0, "output_bytes_retained": 0, "output_max_bytes": 0}
    lines = []
    for item in hosts:
        host = str(item.get("host") or "").strip()
        if not host:
            continue
        lines.append(f"{host} | FAILED | rc=1 >>\n{message}")
    output = "\n".join(lines) if lines else message
    return 1, output, {"truncated": False, "output_bytes_total": 0, "output_bytes_retained": 0, "output_max_bytes": 0}


async def run_mixed_python_script_stream(
    request: AdhocRequest,
    *,
    stream_publish: StreamPublish | None = None,
    stream_log_topic: str | None = None,
    execution_id: str | None = None,
) -> tuple[int, str, dict[str, Any], Path]:
    """并行执行 Linux 远端流式与 Windows WinRM 流式，合并为一次任务输出。"""
    host_credentials = list(request.host_credentials or [])
    linux_credentials, windows_credentials = _split_credentials(host_credentials)
    if not linux_credentials or not windows_credentials:
        raise ValueError("mixed Python streaming requires both Linux and Windows host_credentials")

    script_content = request.module_args
    interpreter = _resolve_python_interpreter(request.extra_vars)
    linux_script = _build_heredoc_command(f"{interpreter} -u", script_content)
    windows_interpreter = _windows_python_executable(interpreter)

    linux_request = replace(
        request,
        module="raw",
        module_args=linux_script,
        host_credentials=linux_credentials,
        inventory="",
        inventory_content=None,
        stream_remote_output=True,
        stream_remote_type=None,
    )
    cmd, workspace = prepare_adhoc_execution(linux_request)

    publish = stream_publish or _noop_publish
    topic = str(stream_log_topic or f"job.stream.{request.task_id or 'mixed'}.ansible")
    exec_id = str(execution_id or request.task_id or "mixed")
    timeout = int(request.execute_timeout)

    async def _run_linux() -> tuple[int, str, dict[str, Any]]:
        return await run_remote_shell_stream(
            cmd,
            script_content=linux_script,
            shell_executable="/bin/sh",
            timeout=timeout,
            host_credentials=linux_credentials,
            workspace=workspace,
            stream_publish=publish,
            stream_log_topic=topic,
            execution_id=exec_id,
        )

    async def _run_windows() -> tuple[int, str, dict[str, Any]]:
        return await run_winrm_stream(
            windows_credentials,
            script_content=script_content,
            script_type="python",
            timeout=timeout,
            stream_publish=publish,
            stream_log_topic=topic,
            execution_id=exec_id,
            windows_interpreter=windows_interpreter,
        )

    linux_outcome, windows_outcome = await asyncio.gather(_run_linux(), _run_windows(), return_exceptions=True)

    if isinstance(linux_outcome, BaseException):
        linux_code, linux_output, linux_meta = _format_side_exception(linux_credentials, linux_outcome)
    else:
        linux_code, linux_output, linux_meta = linux_outcome

    if isinstance(windows_outcome, BaseException):
        windows_code, windows_output, windows_meta = _format_side_exception(windows_credentials, windows_outcome)
    else:
        windows_code, windows_output, windows_meta = windows_outcome

    code = 0 if linux_code == 0 and windows_code == 0 else 1
    output = "\n".join(part for part in (linux_output, windows_output) if part)
    meta = _merge_stream_meta(linux_meta, windows_meta)
    return code, output, meta, workspace
