"""
权限规则缓存模块

提供用户权限规则的缓存功能，避免每次请求都进行 RPC 调用。

缓存策略：
- 使用较长的 TTL（默认 10 分钟）作为兜底
- 在权限变更时主动清除相关用户的缓存
- 即使遗漏了某个清除点，也能在 TTL 内自动恢复一致性

键结构（当前）：
  perm_rules:{user_prefix}:{key_hash}
其中 user_prefix = MD5(username:domain)[:8]，用于支持 delete_pattern 按用户原子清除，
彻底消除旧版"读-改-写"索引的并发竞态（RMW race）。
"""

import hashlib
import os
from typing import Any, Dict, List, Optional

from django.core.cache import cache
from apps.core.logger import logger

# 缓存过期时间 (秒)，默认 10 分钟，可通过环境变量配置
# 作为兜底机制，确保即使遗漏主动失效也能在 TTL 内恢复一致性
PERMISSION_CACHE_TTL = int(os.getenv("PERMISSION_CACHE_TTL", "600"))

# verify_token 结果缓存 TTL（秒），默认 60 秒，可通过环境变量配置
TOKEN_INFO_CACHE_TTL = int(os.getenv("TOKEN_INFO_CACHE_TTL", "60"))

# 用户权限缓存键前缀（用于按用户清除）
PERM_CACHE_PREFIX = "perm_rules:"
# 用户缓存键索引前缀（旧版兜底，非 Redis 后端使用）
USER_PERM_KEYS_PREFIX = "user_perm_keys:"
# verify_token 结果缓存键前缀
TOKEN_INFO_PREFIX = "token_info:"


def _get_token_info_key(username: str, domain: str) -> str:
    return f"{TOKEN_INFO_PREFIX}{username}:{domain}"


def get_cached_token_info(username: str, domain: str) -> Optional[Dict[str, Any]]:
    return cache.get(_get_token_info_key(username, domain))


def set_cached_token_info(username: str, domain: str, data: Dict[str, Any]) -> None:
    cache.set(_get_token_info_key(username, domain), data, TOKEN_INFO_CACHE_TTL)


def clear_token_info_cache(username: str, domain: str = "domain.com") -> None:
    cache.delete(_get_token_info_key(username, domain))


def _get_user_perm_prefix(username: str, domain: str) -> str:
    """
    生成该用户的权限缓存键前缀（用于 delete_pattern 按用户原子清除）。

    使用 MD5 前 8 位保持键的简短，同时确保不同用户/domain 的前缀互不冲突。
    """
    user_hash = hashlib.md5(f"{username}:{domain}".encode()).hexdigest()[:8]
    return f"{PERM_CACHE_PREFIX}{user_hash}:"


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

    键格式：perm_rules:{user_prefix}:{key_hash}
    其中 user_prefix 嵌入用户标识，支持 delete_pattern 按用户精确清除，
    无需维护可被并发破坏的键索引。

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
    user_prefix = _get_user_perm_prefix(username, domain)
    # 剩余维度继续 MD5 哈希，避免键过长
    key_data = f"{current_team}:{app_name}:{permission_key}:{include_children}"
    key_hash = hashlib.md5(key_data.encode()).hexdigest()
    return f"{user_prefix}{key_hash}"


def _get_user_keys_index(username: str, domain: str) -> str:
    """获取用户缓存键索引的 key（旧版兜底，非 Redis 后端使用）"""
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

    # 支持 delete_pattern 的后端（如 django-redis）：cache_key 已内嵌用户前缀，
    # 清除时直接 delete_pattern(user_prefix + "*")，无需维护键索引，不存在并发 RMW 竞态。
    #
    # 不支持 delete_pattern 的后端（本地内存缓存等）：退化为旧版键索引方案兜底。
    # 此路径下竞态窗口仍存在，但这类后端通常不用于生产环境，
    # 最坏情况是旧权限残留至 TTL（PERMISSION_CACHE_TTL）到期。
    if not hasattr(cache, "delete_pattern"):
        user_keys_index = _get_user_keys_index(username, domain)
        existing_keys = cache.get(user_keys_index) or set()
        existing_keys.add(cache_key)
        cache.set(user_keys_index, existing_keys, PERMISSION_CACHE_TTL + 60)

    logger.debug(f"Permission rules cached: {username}@{app_name}/{permission_key}, TTL={PERMISSION_CACHE_TTL}s")


def clear_user_permission_cache(username: str, domain: str = "domain.com") -> None:
    """
    清除指定用户的所有权限缓存（含 token_info 缓存）

    对支持 delete_pattern 的后端（django-redis）：
      使用 delete_pattern(user_prefix + "*") 原子删除该用户的全部权限缓存键，
      不依赖键索引，彻底规避并发 RMW 竞态导致的漏删问题。

    对不支持 delete_pattern 的后端（本地内存缓存等）：
      回退到旧版键索引方案（同时兼容旧键格式的存量索引）。

    Args:
        username: 用户名
        domain: 用户域，默认 "domain.com"
    """
    if hasattr(cache, "delete_pattern"):
        # 主路径：原子按用户前缀清除，无竞态风险
        user_prefix = _get_user_perm_prefix(username, domain)
        try:
            cache.delete_pattern(f"{user_prefix}*")
            logger.info(f"Cleared permission cache (pattern) for user: {username}")
        except Exception as e:
            logger.warning(f"delete_pattern failed for user {username}, falling back to index: {e}")
            _clear_user_cache_by_index(username, domain)
    else:
        # 降级路径：旧版键索引（非 Redis 后端）
        _clear_user_cache_by_index(username, domain)

    clear_token_info_cache(username, domain)


def _clear_user_cache_by_index(username: str, domain: str) -> None:
    """通过旧版键索引清除用户权限缓存（降级兜底）"""
    user_keys_index = _get_user_keys_index(username, domain)
    cached_keys = cache.get(user_keys_index)

    if cached_keys:
        cache.delete_many(list(cached_keys))
        cache.delete(user_keys_index)
        logger.info(f"Cleared {len(cached_keys)} permission cache entries (index) for user: {username}")
    else:
        logger.debug(f"No permission cache index found for user: {username}")


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
            # 清除所有权限缓存（含新格式 perm_rules:{user_prefix}:* 和旧版索引键）
            cache.delete_pattern(f"{PERM_CACHE_PREFIX}*")
            cache.delete_pattern(f"{USER_PERM_KEYS_PREFIX}*")
            logger.info("All permission rules cache cleared")
        else:
            logger.warning("Cannot clear all permission cache: cache backend does not support pattern delete")
    except Exception as e:
        logger.warning(f"Failed to clear all permission cache: {e}")
