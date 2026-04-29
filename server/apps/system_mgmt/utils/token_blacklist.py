"""
JWT Token 黑名单模块

提供 token 撤销功能，使用 Redis（通过 django.core.cache）存储已撤销的 token jti。
Key 格式：jwt:blacklist:{jti}，TTL 为 token 剩余存活秒数，自动过期无需清理。
"""

import time

from django.core.cache import cache

from apps.core.logger import system_mgmt_logger as logger

BLACKLIST_PREFIX = "jwt:blacklist:"


def blacklist_token(jti: str, exp_timestamp: int) -> bool:
    """
    将 token 加入黑名单。

    Args:
        jti: token 的唯一标识符
        exp_timestamp: token 的过期时间（UNIX 时间戳）

    Returns:
        True 表示成功加入黑名单，False 表示 token 已过期无需加入
    """
    remaining = exp_timestamp - int(time.time())
    if remaining <= 0:
        logger.debug(f"Token {jti} already expired, skipping blacklist")
        return False

    cache_key = f"{BLACKLIST_PREFIX}{jti}"
    try:
        cache.set(cache_key, 1, remaining)
    except Exception as e:
        logger.error(f"Failed to blacklist token {jti}: {e}")
        return False
    logger.info(f"Token {jti} blacklisted, TTL={remaining}s")
    return True


def is_blacklisted(jti: str) -> bool:
    """
    检查 token 是否在黑名单中。

    Args:
        jti: token 的唯一标识符

    Returns:
        True 表示 token 已被撤销
    """
    cache_key = f"{BLACKLIST_PREFIX}{jti}"
    return cache.get(cache_key) is not None
