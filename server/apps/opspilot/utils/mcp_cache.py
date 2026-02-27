"""
MCP 工具列表缓存模块

提供 MCP 服务器工具列表的缓存功能，避免每次请求都连接 MCP 服务器。
"""

import hashlib
import os
from typing import List, Optional

from django.core.cache import cache

from apps.core.logger import logger

# 缓存过期时间 (秒)，默认 5 分钟，可通过环境变量配置
MCP_TOOLS_CACHE_TTL = int(os.getenv("MCP_TOOLS_CACHE_TTL", "300"))


def _get_cache_key(server_url: str, auth_token: str = "", transport: str = "") -> str:
    """
    生成 MCP 工具列表缓存键

    Args:
        server_url: MCP 服务器地址
        auth_token: 认证 token（不同 token 可能返回不同工具）
        transport: 传输协议（不同 transport 可能返回不同工具）

    Returns:
        缓存键字符串
    """
    # 使用 MD5 哈希避免缓存键过长或包含特殊字符
    key_data = f"{server_url}:{auth_token}:{transport}"
    key_hash = hashlib.md5(key_data.encode()).hexdigest()
    return f"mcp_tools:{key_hash}"


def get_cached_mcp_tools(server_url: str, auth_token: str = "", transport: str = "") -> Optional[List[dict]]:
    """
    获取缓存的 MCP 工具列表

    Args:
        server_url: MCP 服务器地址
        auth_token: 认证 token
        transport: 传输协议

    Returns:
        缓存的工具列表，未命中返回 None
    """
    cache_key = _get_cache_key(server_url, auth_token, transport)
    cached = cache.get(cache_key)
    if cached is not None:
        logger.debug(f"MCP tools cache hit: {server_url}, transport={transport or 'sse'}")
    return cached


def set_cached_mcp_tools(server_url: str, tools: List[dict], auth_token: str = "", transport: str = "") -> None:
    """
    缓存 MCP 工具列表

    Args:
        server_url: MCP 服务器地址
        tools: 工具列表
        auth_token: 认证 token
        transport: 传输协议
    """
    cache_key = _get_cache_key(server_url, auth_token, transport)
    cache.set(cache_key, tools, MCP_TOOLS_CACHE_TTL)
    logger.debug(f"MCP tools cached: {server_url}, transport={transport or 'sse'}, TTL={MCP_TOOLS_CACHE_TTL}s")


def clear_mcp_tools_cache(server_url: Optional[str] = None, auth_token: str = "", transport: str = "") -> None:
    """
    清除 MCP 工具列表缓存

    Args:
        server_url: MCP 服务器地址，None 表示清除所有（需要 cache 支持 pattern delete）
        auth_token: 认证 token
        transport: 传输协议

    注意:
        如果 server_url 为 None，仅当使用支持 pattern delete 的缓存后端（如 Redis）时有效。
        对于本地内存缓存，建议指定具体的 server_url。
    """
    if server_url:
        cache_key = _get_cache_key(server_url, auth_token, transport)
        cache.delete(cache_key)
        logger.info(f"MCP tools cache cleared: {server_url}, transport={transport or 'sse'}")
    else:
        # 尝试使用 Redis 的 pattern delete
        try:
            if hasattr(cache, "delete_pattern"):
                cache.delete_pattern("mcp_tools:*")
                logger.info("All MCP tools cache cleared")
            else:
                logger.warning("Cannot clear all MCP tools cache: cache backend does not support pattern delete")
        except Exception as e:
            logger.warning(f"Failed to clear all MCP tools cache: {e}")
