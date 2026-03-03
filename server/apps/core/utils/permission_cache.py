"""
权限规则缓存模块

提供用户权限规则的缓存功能，避免每次请求都进行 RPC 调用。

缓存策略：
- 使用较长的 TTL（默认 10 分钟）作为兜底
- 在权限变更时主动清除相关用户的缓存
- 即使遗漏了某个清除点，也能在 TTL 内自动恢复一致性
"""

import hashlib
import os
from typing import Dict, List, Optional

from django.core.cache import cache

from apps.core.logger import logger

# 缓存过期时间 (秒)，默认 10 分钟，可通过环境变量配置
# 作为兜底机制，确保即使遗漏主动失效也能在 TTL 内恢复一致性
PERMISSION_CACHE_TTL = int(os.getenv("PERMISSION_CACHE_TTL", "600"))

# 用户权限缓存键前缀（用于按用户清除）
PERM_CACHE_PREFIX = "perm_rules:"
# 用户缓存键索引前缀（记录用户的所有缓存键）
USER_PERM_KEYS_PREFIX = "user_perm_keys:"


def _get_cache_key(
    username: str,
    domain: str,
    current_team: int,
    app_name: str,
    permission_key: str,
    include_children: bool = False,
) -> str:
    """
    生成权限规则缓存键

    Args:
        username: 用户名
        domain: 用户域
        current_team: 当前团队 ID
        app_name: 应用名称
        permission_key: 权限键
        include_children: 是否包含子组

    Returns:
        缓存键字符串
    """
    # 使用 MD5 哈希避免缓存键过长
    key_data = f"{username}:{domain}:{current_team}:{app_name}:{permission_key}:{include_children}"
    key_hash = hashlib.md5(key_data.encode()).hexdigest()
    return f"{PERM_CACHE_PREFIX}{key_hash}"


def _get_user_keys_index(username: str, domain: str) -> str:
    """获取用户缓存键索引的 key"""
    return f"{USER_PERM_KEYS_PREFIX}{username}:{domain}"


def get_cached_permission_rules(
    username: str,
    domain: str,
    current_team: int,
    app_name: str,
    permission_key: str,
    include_children: bool = False,
) -> Optional[Dict]:
    """
    获取缓存的权限规则

    Args:
        username: 用户名
        domain: 用户域
        current_team: 当前团队 ID
        app_name: 应用名称
        permission_key: 权限键
        include_children: 是否包含子组

    Returns:
        缓存的权限规则，未命中返回 None
    """
    cache_key = _get_cache_key(username, domain, current_team, app_name, permission_key, include_children)
    cached = cache.get(cache_key)
    if cached is not None:
        logger.debug(f"Permission rules cache hit: {username}@{app_name}/{permission_key}")
    return cached


def set_cached_permission_rules(
    username: str,
    domain: str,
    current_team: int,
    app_name: str,
    permission_key: str,
    permission_data: Dict,
    include_children: bool = False,
) -> None:
    """
    缓存权限规则

    Args:
        username: 用户名
        domain: 用户域
        current_team: 当前团队 ID
        app_name: 应用名称
        permission_key: 权限键
        permission_data: 权限数据
        include_children: 是否包含子组
    """
    cache_key = _get_cache_key(username, domain, current_team, app_name, permission_key, include_children)
    cache.set(cache_key, permission_data, PERMISSION_CACHE_TTL)

    # 记录该用户的缓存键，便于后续按用户清除
    user_keys_index = _get_user_keys_index(username, domain)
    existing_keys = cache.get(user_keys_index) or set()
    existing_keys.add(cache_key)
    cache.set(user_keys_index, existing_keys, PERMISSION_CACHE_TTL + 60)  # 索引 TTL 略长于缓存

    logger.debug(f"Permission rules cached: {username}@{app_name}/{permission_key}, TTL={PERMISSION_CACHE_TTL}s")


def clear_user_permission_cache(username: str, domain: str = "domain.com") -> None:
    """
    清除指定用户的所有权限缓存

    Args:
        username: 用户名
        domain: 用户域，默认 "domain.com"
    """
    user_keys_index = _get_user_keys_index(username, domain)
    cached_keys = cache.get(user_keys_index)

    if cached_keys:
        # 批量删除用户的所有权限缓存
        cache.delete_many(list(cached_keys))
        cache.delete(user_keys_index)
        logger.info(f"Cleared {len(cached_keys)} permission cache entries for user: {username}")
    else:
        logger.debug(f"No permission cache found for user: {username}")


def clear_users_permission_cache(users: List[Dict]) -> None:
    """
    批量清除多个用户的权限缓存

    Args:
        users: 用户列表，每个元素为 {"username": str, "domain": str} 或 {"username": str}
    """
    for user in users:
        username = user.get("username")
        domain = user.get("domain", "domain.com")
        if username:
            clear_user_permission_cache(username, domain)


def clear_all_permission_cache() -> None:
    """
    清除所有权限规则缓存

    注意:
        仅当使用支持 pattern delete 的缓存后端（如 Redis）时有效。
        对于本地内存缓存，只能等待 TTL 过期。
    """
    try:
        if hasattr(cache, "delete_pattern"):
            cache.delete_pattern(f"{PERM_CACHE_PREFIX}*")
            cache.delete_pattern(f"{USER_PERM_KEYS_PREFIX}*")
            logger.info("All permission rules cache cleared")
        else:
            logger.warning("Cannot clear all permission cache: cache backend does not support pattern delete")
    except Exception as e:
        logger.warning(f"Failed to clear all permission cache: {e}")
