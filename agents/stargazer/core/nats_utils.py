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
        stargazer 是单线程单事件循环（arq + sanic）。采集插件中存在阻塞型
        调用（SNMP/SSH/子进程），会短时间占满事件循环。如果此时去新建 NATS
        连接，异步 TLS 握手无法被事件循环及时驱动，NATS 服务端在握手超时
        （默认 2s）后会直接 reset，表现为大量 ConnectionResetError，导致
        ansible adhoc 请求发不出去、回调收不到。

        改为一条已建立的长连接后：
        - 不再有“每次操作一次 TLS 握手”，握手只在启动/重连时发生一次；
        - 连接由 nats-py 在后台维护并无限自动重连；
        - 即使事件循环被阻塞数十秒，已建立的连接也不会像 2s 握手那样被打断。
"""
import asyncio
import json
from typing import Any, List, Optional

from nats.aio.client import Client as NATS
from sanic.log import logger

from core.nats import NATSConfig


# 进程级共享连接与连接锁
_shared_nc: Optional[NATS] = None
_connect_lock: Optional[asyncio.Lock] = None


def _get_lock() -> asyncio.Lock:
    """惰性创建锁，确保绑定到当前运行的事件循环。"""
    global _connect_lock
    if _connect_lock is None:
        _connect_lock = asyncio.Lock()
    return _connect_lock


async def _on_error(e: Exception) -> None:
    logger.error(f"[NATS] shared connection error: {type(e).__name__}: {e}")


async def _on_disconnected() -> None:
    logger.warning("[NATS] shared connection disconnected")


async def _on_reconnected() -> None:
    logger.info("[NATS] shared connection reconnected")


async def _on_closed() -> None:
    logger.warning("[NATS] shared connection closed")


async def get_shared_nats() -> NATS:
    """获取共享的 NATS 长连接（懒加载 + 自动重连）。

    若连接尚未建立或已关闭，则（重新）建立一条连接。并发调用通过锁串行化，
    确保整个进程只维护一条连接。
    """
    global _shared_nc

    nc = _shared_nc
    if nc is not None and nc.is_connected:
        return nc

    async with _get_lock():
        # 拿到锁后二次确认，避免并发重复建连
        nc = _shared_nc
        if nc is not None and nc.is_connected:
            return nc

        # 清理可能存在的半死连接
        if nc is not None and not nc.is_closed:
            try:
                await nc.close()
            except Exception as close_err:
                logger.debug(f"[NATS] error closing stale connection: {close_err}")
        _shared_nc = None

        config = NATSConfig.from_env()
        options = config.to_connect_options()
        # 长连接：无限重连，避免达到重连上限后被永久关闭
        options["max_reconnect_attempts"] = -1
        options["allow_reconnect"] = True
        options.setdefault("error_cb", _on_error)
        options.setdefault("disconnected_cb", _on_disconnected)
        options.setdefault("reconnected_cb", _on_reconnected)
        options.setdefault("closed_cb", _on_closed)

        new_nc = NATS()
        await new_nc.connect(**options)
        _shared_nc = new_nc
        logger.info(
            f"[NATS] shared connection established: servers={config.servers}, "
            f"tls={config.tls_enabled}, user={config.user}"
        )
        return new_nc


async def close_shared_nats() -> None:
    """优雅关闭共享连接（供进程退出时调用，可选）。"""
    global _shared_nc
    nc = _shared_nc
    _shared_nc = None
    if nc is None:
        return
    try:
        if not nc.is_closed:
            await nc.drain()
    except Exception as e:
        logger.debug(f"[NATS] error draining shared connection: {e}")


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
        nc = await get_shared_nats()
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
    try:
        nc = await get_shared_nats()
        payload = json.dumps(data).encode()
        await nc.publish(subject, payload)
        await nc.flush()
    except Exception as e:
        logger.error(f"NATS publish failed [{subject}]: {type(e).__name__}: {e}")
        raise


async def nats_publish_lines(subject: str, lines: List[str]) -> int:
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

    nc = await get_shared_nats()
    count = 0
    for line in lines:
        await nc.publish(subject, line.encode("utf-8"))
        count += 1
    await nc.flush()
    return count
