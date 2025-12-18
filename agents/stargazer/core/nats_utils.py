# -*- coding: utf-8 -*-
# @File: nats_utils.py
# @Time: 2025/12/16
# @Author: windyzhao
"""
NATS 通用工具方法
提供简洁的 NATS 请求封装，无需手动管理连接
"""
import json
from typing import Any
from nats.aio.client import Client as NATS
from sanic.log import logger
from core.nats import NATSConfig


async def nats_request(subject: str, payload: bytes, timeout: float = 30.0) -> dict:
    """
    通用的 NATS 请求方法
    
    自动管理连接生命周期，发送请求并返回响应
    
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
    config = NATSConfig.from_env()
    nc = NATS()

    try:
        # 连接到 NATS 服务器
        await nc.connect(**config.to_connect_options())
        
        # 发送请求并等待响应
        response_msg = await nc.request(subject, payload=payload, timeout=timeout)
        
        # 解析响应数据
        response = json.loads(response_msg.data.decode())
        return response
        
    except Exception as e:
        logger.error(f"NATS request failed: {type(e).__name__}: {e}")
        raise
        
    finally:
        # 确保连接正确关闭
        try:
            if not nc.is_closed:
                await nc.drain()
        except Exception as e:
            logger.error(f"Error closing NATS connection: {e}")


async def nats_publish(subject: str, data: Any) -> None:
    """
    通用的 NATS 发布方法
    
    发布消息到指定主题（无需等待响应）
    
    Args:
        subject: NATS 主题
        data: 要发布的数据（将自动转换为 JSON）
        
    Raises:
        ConnectionError: 连接失败
        Exception: 发布失败
        
    Example:
        >>> await nats_publish("logs.info", {"message": "Task completed"})
    """
    config = NATSConfig.from_env()
    nc = NATS()

    try:
        await nc.connect(**config.to_connect_options())
        payload = json.dumps(data).encode()
        await nc.publish(subject, payload)
        
    except Exception as e:
        logger.error(f"NATS publish failed: {type(e).__name__}: {e}")
        raise
        
    finally:
        try:
            if not nc.is_closed:
                await nc.drain()
        except Exception as e:
            logger.error(f"Error closing NATS connection: {e}")
