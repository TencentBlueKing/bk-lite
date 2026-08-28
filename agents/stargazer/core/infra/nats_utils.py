# -*- coding: utf-8 -*-
# @File: nats_utils.py
# @Time: 2025/12/16
# @Author: windyzhao
"""
NATS 通用工具方法
提供简洁的 NATS 请求/发布封装，无需手动管理连接。

实现说明（重要）：
    本模块维护一条**进程级共享长连接**，所有 nats_request / nats_publish
    都复用它，而不是每次调用都新建一条 TLS 连接再关闭。

    为什么必须共享长连接：
        stargazer 的每个服务进程使用一个 Sanic 事件循环。遗留同步 SDK 已在
        插件内部包装到 asyncio 默认线程池，但事件循环抖动期间若新建 NATS
        连接，异步 TLS 握手无法被事件循环及时驱动，NATS 服务端在握手超时
        （默认 2s）后会直接 reset，表现为大量 ConnectionResetError，导致
        ansible adhoc 请求发不出去、回调收不到。

        改为一条已建立的长连接后：
        - 不再有“每次操作一次 TLS 握手”，握手只在启动/重连时发生一次；
        - 连接由 nats-py 在后台维护并无限自动重连；
        - 即使事件循环被阻塞数十秒，已建立的连接也不会像 2s 握手那样被打断。
"""

import asyncio
import hashlib
import json
import os
import time
from collections import deque
from collections.abc import Callable
from typing import Any, List, Optional, Sequence

from core.infra.jetstream_publish_window import JetStreamMessage, JetStreamPublishWindow, JetStreamPublishWindowSettings, JetStreamWindowPublishError
from core.infra.nats import NATSConfig
from core.logger import logger
from nats.aio.client import Client as NATS

# 进程级共享连接与连接锁
_shared_nc: Optional[NATS] = None
_metrics_nc: Optional[NATS] = None
_connect_lock: Optional[asyncio.Lock] = None
_metrics_connect_lock: Optional[asyncio.Lock] = None
_metrics_js_window: Optional[JetStreamPublishWindow] = None
_metrics_js_context = None
_metrics_js_connection: Optional[NATS] = None
_metrics_reconnect_total = 0
_metrics_reconnect_started_at: float | None = None
_metrics_reconnect_duration_seconds = 0.0
_metrics_reconnect_durations: deque[float] = deque(maxlen=500)


class NatsLinesPublishError(RuntimeError):
    def __init__(
        self,
        subject: str,
        attempted_count_before_failure: int,
        delivery_detected: bool,
        error: Exception,
        attempted_indices: tuple[int, ...] = (),
        confirmed_indices: tuple[int, ...] = (),
    ):
        self.subject = subject
        self.attempted_count_before_failure = attempted_count_before_failure
        self.delivery_detected = delivery_detected
        self.error = error
        self.attempted_indices = attempted_indices
        self.confirmed_indices = confirmed_indices
        super().__init__(
            f"NATS publish lines failed [{subject}] after writing "
            f"{attempted_count_before_failure} lines before confirmation "
            f"(delivery_detected={delivery_detected}): {type(error).__name__}: {error}"
        )
        self.__cause__ = error


def _get_lock(channel: str = "control") -> asyncio.Lock:
    """惰性创建锁，确保绑定到当前运行的事件循环。"""
    global _connect_lock, _metrics_connect_lock
    if channel == "metrics":
        if _metrics_connect_lock is None:
            _metrics_connect_lock = asyncio.Lock()
        return _metrics_connect_lock
    if _connect_lock is None:
        _connect_lock = asyncio.Lock()
    return _connect_lock


async def _on_error(e: Exception) -> None:
    logger.error(f"[NATS] shared connection error: {type(e).__name__}: {e}")


async def _on_disconnected() -> None:
    logger.warning("[NATS] shared connection disconnected")


async def _on_reconnected() -> None:
    logger.info("[NATS] shared connection reconnected")


async def _on_metrics_disconnected() -> None:
    global _metrics_reconnect_started_at
    if _metrics_reconnect_started_at is None:
        _metrics_reconnect_started_at = time.monotonic()
    await _on_disconnected()


async def _on_metrics_reconnected() -> None:
    global _metrics_reconnect_total, _metrics_reconnect_started_at, _metrics_reconnect_duration_seconds
    _metrics_reconnect_total += 1
    if _metrics_reconnect_started_at is not None:
        _metrics_reconnect_duration_seconds = max(0.0, time.monotonic() - _metrics_reconnect_started_at)
        _metrics_reconnect_durations.append(_metrics_reconnect_duration_seconds)
        _metrics_reconnect_started_at = None
    await _on_reconnected()


async def _on_closed() -> None:
    logger.warning("[NATS] shared connection closed")


async def get_shared_nats(channel: str = "control") -> NATS:
    """获取共享的 NATS 长连接（懒加载 + 自动重连）。

    若连接尚未建立或已关闭，则（重新）建立一条连接。并发调用通过锁串行化，
    确保整个进程只维护一条连接。
    """
    global _shared_nc, _metrics_nc

    if channel not in {"control", "metrics"}:
        raise ValueError(f"unsupported NATS channel: {channel}")

    nc = _metrics_nc if channel == "metrics" else _shared_nc
    if nc is not None and (nc.is_connected or (not nc.is_closed and bool(getattr(nc, "is_reconnecting", False)))):
        return nc

    async with _get_lock(channel):
        # 拿到锁后二次确认，避免并发重复建连
        nc = _metrics_nc if channel == "metrics" else _shared_nc
        if nc is not None and (nc.is_connected or (not nc.is_closed and bool(getattr(nc, "is_reconnecting", False)))):
            return nc

        # 清理可能存在的半死连接
        if nc is not None and not nc.is_closed:
            try:
                await nc.close()
            except Exception as close_err:
                logger.debug(f"[NATS] error closing stale connection: {close_err}")
        if channel == "metrics":
            _metrics_nc = None
        else:
            _shared_nc = None

        config = NATSConfig.from_env(service_name=f"stargazer-{channel}")
        options = config.to_connect_options()
        # 长连接：无限重连，避免达到重连上限后被永久关闭
        options["max_reconnect_attempts"] = -1
        options["allow_reconnect"] = True
        options.setdefault("error_cb", _on_error)
        options.setdefault(
            "disconnected_cb",
            _on_metrics_disconnected if channel == "metrics" else _on_disconnected,
        )
        options.setdefault(
            "reconnected_cb",
            _on_metrics_reconnected if channel == "metrics" else _on_reconnected,
        )
        options.setdefault("closed_cb", _on_closed)

        new_nc = NATS()
        await new_nc.connect(**options)
        if channel == "metrics":
            _metrics_nc = new_nc
        else:
            _shared_nc = new_nc
        logger.info(
            f"[NATS] shared connection established: channel={channel}, servers={config.servers}, "
            f"tls={config.tls_enabled}, authentication_configured={bool(config.user)}"
        )
        return new_nc


async def close_shared_nats() -> None:
    """优雅关闭共享连接（供进程退出时调用，可选）。"""
    global _shared_nc, _metrics_nc, _metrics_js_window, _metrics_js_context, _metrics_js_connection
    clients = tuple(client for client in (_shared_nc, _metrics_nc) if client is not None)
    _shared_nc = None
    _metrics_nc = None
    _metrics_js_window = None
    _metrics_js_context = None
    _metrics_js_connection = None
    for nc in clients:
        try:
            if not nc.is_closed:
                await nc.drain()
        except Exception as e:
            logger.debug(f"[NATS] error draining shared connection: {e}")
        finally:
            try:
                if not nc.is_closed:
                    await nc.close()
            except Exception as close_error:
                logger.debug(f"[NATS] error closing shared connection: {close_error}")


def nats_metrics_connection_stats() -> dict[str, float | int]:
    nc = _metrics_nc
    pending_bytes = 0
    if nc is not None:
        try:
            pending_bytes = max(0, int(getattr(nc, "pending_data_size", 0) or 0))
        except (TypeError, ValueError):
            pending_bytes = 0
    ordered_durations = sorted(_metrics_reconnect_durations)
    p99_duration = ordered_durations[int((len(ordered_durations) - 1) * 0.99)] if ordered_durations else 0.0
    window = _metrics_js_window.snapshot() if _metrics_js_window is not None else None
    return {
        "nats_metrics_connected": int(bool(nc is not None and nc.is_connected)),
        "nats_metrics_reconnecting": int(bool(nc is not None and getattr(nc, "is_reconnecting", False))),
        "nats_metrics_reconnect_total": _metrics_reconnect_total,
        "nats_metrics_reconnect_duration_seconds": _metrics_reconnect_duration_seconds,
        "nats_metrics_reconnect_duration_seconds_p99": p99_duration,
        "nats_metrics_pending_bytes": pending_bytes,
        "nats_js_publish_pending_messages": window.pending_messages if window else 0,
        "nats_js_publish_pending_bytes": window.pending_bytes if window else 0,
        "nats_js_publish_pending_messages_peak": window.peak_pending_messages if window else 0,
        "nats_js_publish_pending_bytes_peak": window.peak_pending_bytes if window else 0,
        "nats_js_publish_confirmed_total": window.confirmed_total if window else 0,
        "nats_js_puback_duration_seconds_p95": window.puback_duration_seconds_p95 if window else 0.0,
        "nats_js_puback_duration_seconds_p99": window.puback_duration_seconds_p99 if window else 0.0,
        "nats_js_puback_timeout_total": window.puback_timeout_total if window else 0,
        "nats_js_publish_retry_total": window.retry_total if window else 0,
        "nats_js_publish_rejected_total": window.rejected_total if window else 0,
    }


async def nats_request(subject: str, payload: bytes, timeout: float = 30.0) -> dict:
    """
    通用的 NATS 请求方法（复用共享长连接）

    发送请求并返回响应。连接由共享连接池管理，无需手动建连/关闭。

    Args:
        subject: NATS 主题
        payload: 请求负载（已编码的字节数据）
        timeout: 超时时间（秒），默认 30 秒

    Returns:
        解析后的响应数据（字典格式）

    Raises:
        ConnectionError: 连接失败
        Exception: 请求或响应处理失败

    Example:
        >>> exec_params = {"args": [{"command": "ls"}], "kwargs": {}}
        >>> payload = json.dumps(exec_params).encode()
        >>> response = await nats_request("ssh.execute.node1", payload, timeout=30.0)
    """
    try:
        nc = await get_shared_nats("control")
        response_msg = await nc.request(subject, payload=payload, timeout=timeout)
        return json.loads(response_msg.data.decode())
    except Exception as e:
        logger.error(f"NATS request failed [{subject}]: {type(e).__name__}: {e}")
        raise


async def nats_publish(subject: str, data: Any) -> None:
    """
    通用的 NATS 发布方法（复用共享长连接）

    发布消息到指定主题（无需等待响应）。发布后会 flush，确保数据已写出。

    Args:
        subject: NATS 主题
        data: 要发布的数据（将自动转换为 JSON）

    Raises:
        ConnectionError: 连接失败
        Exception: 发布失败

    Example:
        >>> await nats_publish("logs.info", {"message": "Task completed"})
    """
    nc = await get_shared_nats("control")
    payload = json.dumps(data).encode()
    await nc.publish(subject, payload)
    await nc.flush()


async def nats_publish_lines(
    subject: str,
    lines: List[str],
    *,
    before_publish: Callable[[int], bool] | None = None,
    message_ids: Sequence[str] | None = None,
) -> int:
    """
    批量发布多行文本到指定主题（复用共享长连接）。

    用于指标上报（InfluxDB Line Protocol，每行一条消息），逐行 publish 后统一
    flush，避免每条指标都新建连接。

    Args:
        subject: NATS 主题
        lines: 文本行列表（每行将单独发布一条消息）

    Returns:
        成功发布的行数
    """
    if not lines:
        return 0

    if message_ids is not None and len(message_ids) != len(lines):
        raise ValueError("message_ids length must match lines length")
    if _read_bool_env("NATS_METRICS_JETSTREAM_ENABLED", False):
        return await _nats_publish_lines_jetstream(
            subject,
            lines,
            before_publish=before_publish,
            message_ids=message_ids,
        )

    attempted_indices: list[int] = []
    delivery_timeout = float(os.getenv("PUBLISH_DELIVERY_TIMEOUT", os.getenv("PUBLISH_TIMEOUT", "30")))
    try:
        async with asyncio.timeout(delivery_timeout):
            nc = await get_shared_nats("metrics")
            for index, line in enumerate(lines):
                if before_publish is not None and not before_publish(index):
                    continue
                attempted_indices.append(index)
                await nc.publish(subject, line.encode("utf-8"))
            if attempted_indices:
                await nc.flush(timeout=delivery_timeout)
    except Exception as e:
        raise NatsLinesPublishError(
            subject=subject,
            attempted_count_before_failure=len(attempted_indices),
            delivery_detected=bool(attempted_indices),
            error=e,
            attempted_indices=tuple(attempted_indices),
        ) from e
    return len(attempted_indices)


def _read_bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _jetstream_message_id(subject: str, index: int, payload: bytes) -> str:
    digest = hashlib.sha256()
    digest.update(subject.encode("utf-8"))
    digest.update(b"\0")
    digest.update(str(index).encode("ascii"))
    digest.update(b"\0")
    digest.update(payload)
    return digest.hexdigest()


async def _get_metrics_jetstream():
    global _metrics_js_context, _metrics_js_connection
    nc = await get_shared_nats("metrics")
    if _metrics_js_context is None or _metrics_js_connection is not nc:
        _metrics_js_context = nc.jetstream(publish_async_max_pending=int(os.getenv("NATS_JS_PUBLISH_MAX_PENDING", "1024")))
        _metrics_js_connection = nc
    return _metrics_js_context


def _get_metrics_js_window() -> JetStreamPublishWindow:
    global _metrics_js_window
    if _metrics_js_window is None:
        _metrics_js_window = JetStreamPublishWindow(
            _get_metrics_jetstream,
            settings=JetStreamPublishWindowSettings(
                max_pending_messages=int(os.getenv("NATS_JS_PUBLISH_MAX_PENDING", "1024")),
                max_pending_bytes=int(os.getenv("NATS_JS_PUBLISH_MAX_PENDING_BYTES", str(128 * 1024 * 1024))),
                puback_timeout_seconds=float(
                    os.getenv(
                        "NATS_JS_PUBACK_TIMEOUT",
                        os.getenv("PUBLISH_DELIVERY_TIMEOUT", os.getenv("PUBLISH_TIMEOUT", "30")),
                    )
                ),
                max_attempts=int(os.getenv("NATS_JS_PUBLISH_MAX_ATTEMPTS", "2")),
                expected_stream=os.getenv("NATS_JS_STREAM_NAME", "CMDB_METRICS"),
            ),
        )
    return _metrics_js_window


async def _nats_publish_lines_jetstream(
    subject: str,
    lines: List[str],
    *,
    before_publish: Callable[[int], bool] | None,
    message_ids: Sequence[str] | None,
) -> int:
    payloads = tuple(line.encode("utf-8") for line in lines)
    messages = tuple(
        JetStreamMessage(
            payload=payload,
            message_id=(str(message_ids[index]) if message_ids is not None else _jetstream_message_id(subject, index, payload)),
        )
        for index, payload in enumerate(payloads)
    )
    try:
        return await _get_metrics_js_window().publish(
            subject,
            messages,
            before_publish=before_publish,
        )
    except JetStreamWindowPublishError as error:
        raise NatsLinesPublishError(
            subject=subject,
            attempted_count_before_failure=len(error.attempted_indices),
            delivery_detected=bool(error.attempted_indices),
            error=error.error if isinstance(error.error, Exception) else RuntimeError(type(error.error).__name__),
            attempted_indices=error.attempted_indices,
            confirmed_indices=error.confirmed_indices,
        ) from error
