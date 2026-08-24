import json
import math
import multiprocessing
import os
import threading
from typing import TYPE_CHECKING, Any

from apps.core.logger import log_logger as logger

if TYPE_CHECKING:
    from apps.log.services.log_extractor.semantics import ExecutionResult, NormalizedRule


def _positive_number_env(name: str, default: int | float, caster):
    try:
        value = caster(os.getenv(name, str(default)))
        valid = math.isfinite(value) and value > 0
    except (OverflowError, TypeError, ValueError):
        return default
    return value if valid else default


REGEX_PREVIEW_TIMEOUT_SECONDS = _positive_number_env("LOG_EXTRACTOR_PREVIEW_TIMEOUT_SECONDS", 1.0, float)
REGEX_PREVIEW_MAX_CONCURRENCY = _positive_number_env("LOG_EXTRACTOR_PREVIEW_MAX_CONCURRENCY", 1, int)
# Packetbeat HTTP 采集允许 10 MiB 正文；默认边界保留这一存量合法形态，并给事件元数据留出余量。
REGEX_PREVIEW_MAX_FIELD_BYTES = _positive_number_env("LOG_EXTRACTOR_PREVIEW_MAX_FIELD_BYTES", 10 * 1024 * 1024, int)
REGEX_PREVIEW_MAX_EVENT_BYTES = _positive_number_env("LOG_EXTRACTOR_PREVIEW_MAX_EVENT_BYTES", 12 * 1024 * 1024, int)
_REGEX_PREVIEW_SLOTS = threading.BoundedSemaphore(REGEX_PREVIEW_MAX_CONCURRENCY)


class RuleExecutionTimeoutError(ValueError):
    pass


class RuleExecutionBusyError(ValueError):
    pass


class RuleExecutionLimitError(ValueError):
    pass


def _ensure_event_within_limits(event: dict[str, Any]) -> None:
    total_bytes = 0
    encoder = json.JSONEncoder(ensure_ascii=False, separators=(",", ":"))
    for chunk in encoder.iterencode(event):
        chunk_bytes = len(chunk.encode("utf-8"))
        total_bytes += chunk_bytes
        if total_bytes > REGEX_PREVIEW_MAX_EVENT_BYTES:
            raise RuleExecutionLimitError("正则预览事件大小超过上限")

    pending: list[Any] = [event]
    while pending:
        value = pending.pop()
        if isinstance(value, dict):
            pending.extend(value.keys())
            pending.extend(value.values())
        elif isinstance(value, (list, tuple)):
            pending.extend(value)
        elif isinstance(value, str) and len(value.encode("utf-8")) > REGEX_PREVIEW_MAX_FIELD_BYTES:
            raise RuleExecutionLimitError("正则预览字段大小超过上限")


def _execute_rules_worker(connection, event: dict[str, Any], rules: list["NormalizedRule"]) -> None:
    from apps.log.services.log_extractor.semantics import _execute_rules_inline

    try:
        payload = ("success", _execute_rules_inline(event, rules))
    except Exception as exc:
        logger.exception("正则预览子进程执行失败")
        payload = ("error", type(exc).__name__)
    try:
        connection.send(payload)
    finally:
        connection.close()


def _stop_process(process: multiprocessing.Process) -> None:
    process.join(timeout=0.1)
    if process.is_alive():
        process.kill()
        process.join(timeout=1)
    if process.is_alive():
        raise RuntimeError("正则预览执行进程无法回收")
    process.close()


def _execute_rules_isolated(event: dict[str, Any], rules: list["NormalizedRule"], timeout_seconds: float) -> "ExecutionResult":
    context = multiprocessing.get_context("spawn")
    parent_connection, child_connection = context.Pipe(duplex=False)
    process = context.Process(target=_execute_rules_worker, args=(child_connection, event, rules))
    started = False
    try:
        process.start()
        started = True
        child_connection.close()
        if not parent_connection.poll(timeout_seconds):
            raise RuleExecutionTimeoutError("正则预览执行超时")
        try:
            status, payload = parent_connection.recv()
        except EOFError as exc:
            raise RuntimeError("正则预览执行进程意外退出") from exc
        if status == "error":
            raise RuntimeError(f"正则预览执行失败: {payload}")
        return payload
    finally:
        parent_connection.close()
        child_connection.close()
        if started:
            _stop_process(process)
        else:
            process.close()


def execute_regex_preview(event: dict[str, Any], rules: list["NormalizedRule"], *, timeout_seconds: float | None = None) -> "ExecutionResult":
    _ensure_event_within_limits(event)
    if not _REGEX_PREVIEW_SLOTS.acquire(blocking=False):
        raise RuleExecutionBusyError("正则预览并发已达上限，请稍后重试")
    try:
        timeout = timeout_seconds or REGEX_PREVIEW_TIMEOUT_SECONDS
        return _execute_rules_isolated(event, rules, timeout)
    finally:
        _REGEX_PREVIEW_SLOTS.release()
