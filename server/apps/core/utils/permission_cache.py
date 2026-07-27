"""
权限规则缓存模块

提供用户权限规则的缓存功能，避免每次请求都进行 RPC 调用。

缓存策略：
- 使用较长的 TTL（默认 10 分钟）作为兜底
- 在权限变更事务中推进独立、单调的数据库权限代际，所有权限缓存键均包含该代际
- 事务提交后尽力删除旧缓存，删除失败也不会让旧权限缓存重新生效

键结构（当前）：
  perm_rules:{user_prefix}:{key_hash}
其中 user_prefix = MD5(username:domain)[:8]，用于支持 delete_pattern 按用户清除。
"""

import hashlib
import os
from typing import Any, Dict, List, Optional

from django.apps import apps
from django.core.cache import cache
from django.db import transaction
from django.db.models import F

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
# API Secret 认证后的角色/菜单权限快照
API_TOKEN_PERMISSION_CACHE_PREFIX = "api_token_permissions"
# 不支持 delete_pattern 的缓存后端使用的 API 权限键索引
API_TOKEN_PERMISSION_KEYS_PREFIX = "api_token_permission_keys:"


def get_user_permission_version(username: str, domain: str) -> int:
    """读取数据库中的用户权限代际，作为跨进程权限快照 fencing token。"""
    version_model = apps.get_model("system_mgmt", "UserPermissionVersion")
    version = version_model.objects.filter(username=username, domain=domain).values_list("version", flat=True).first()
    return int(version or 0)


def _advance_user_permission_versions(users: List[Dict]) -> int:
    """在当前数据库事务中推进受影响用户的权限代际。"""
    identities = {(user.get("username"), user.get("domain", "domain.com")) for user in users if user.get("username")}
    if not identities:
        return 0

    usernames_by_domain = {}
    for username, domain in identities:
        usernames_by_domain.setdefault(domain, []).append(username)

    version_model = apps.get_model("system_mgmt", "UserPermissionVersion")
    updated = 0
    for domain, usernames in usernames_by_domain.items():
        for offset in range(0, len(usernames), 1000):
            batch = usernames[offset : offset + 1000]
            version_model.objects.bulk_create(
                [version_model(username=username, domain=domain, version=0) for username in batch],
                ignore_conflicts=True,
                batch_size=1000,
            )
            updated += version_model.objects.filter(
                domain=domain,
                username__in=batch,
            ).update(version=F("version") + 1)
    return updated


def _advance_all_user_permission_versions() -> int:
    """推进全部用户权限代际，用于全量角色/菜单初始化后的统一失效。"""
    user_model = apps.get_model("system_mgmt", "User")
    updated = 0
    users = user_model.objects.values("username", "domain").iterator(chunk_size=1000)
    batch = []
    for user in users:
        batch.append(user)
        if len(batch) == 1000:
            updated += _advance_user_permission_versions(batch)
            batch = []
    if batch:
        updated += _advance_user_permission_versions(batch)
    return updated


def _get_token_info_key(
    username: str,
    domain: str,
    permission_version: Optional[int] = None,
) -> str:
    if permission_version is None:
        permission_version = get_user_permission_version(username, domain)
    return f"{TOKEN_INFO_PREFIX}{username}:{domain}:v{permission_version}"


def get_cached_token_info(
    username: str,
    domain: str,
    permission_version: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    if permission_version is None:
        permission_version = get_user_permission_version(username, domain)
    cached = cache.get(_get_token_info_key(username, domain, permission_version))
    if cached is not None and get_user_permission_version(username, domain) == permission_version:
        return cached
    return None


def set_cached_token_info(
    username: str,
    domain: str,
    data: Dict[str, Any],
    permission_version: Optional[int] = None,
) -> bool:
    if permission_version is None:
        permission_version = get_user_permission_version(username, domain)
    if get_user_permission_version(username, domain) != permission_version:
        return False
    cache.set(
        _get_token_info_key(username, domain, permission_version),
        data,
        TOKEN_INFO_CACHE_TTL,
    )
    return get_user_permission_version(username, domain) == permission_version


def clear_token_info_cache(username: str, domain: str = "domain.com") -> None:
    permission_version = get_user_permission_version(username, domain)
    cache.delete_many(
        [
            f"{TOKEN_INFO_PREFIX}{username}:{domain}",
            _get_token_info_key(username, domain, permission_version),
        ]
    )


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
    permission_version: Optional[int] = None,
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
    if permission_version is None:
        permission_version = get_user_permission_version(username, domain)
    user_prefix = _get_user_perm_prefix(username, domain)
    # 剩余维度继续 MD5 哈希，避免键过长
    key_data = f"v{permission_version}:{current_team}:{app_name}:{permission_key}:{include_children}"
    key_hash = hashlib.md5(key_data.encode()).hexdigest()
    return f"{user_prefix}{key_hash}"


def _get_user_keys_index(username: str, domain: str) -> str:
    """获取用户缓存键索引的 key（旧版兜底，非 Redis 后端使用）"""
    return f"{USER_PERM_KEYS_PREFIX}{username}:{domain}"


def _get_api_token_permission_prefix(username: str, domain: str) -> str:
    """返回指定用户全部 API Token 权限快照的键前缀。"""
    return f"{API_TOKEN_PERMISSION_CACHE_PREFIX}:{username}:{domain}:"


def _get_api_token_keys_index(username: str, domain: str) -> str:
    """返回非 pattern 缓存后端使用的 API Token 权限键索引。"""
    return f"{API_TOKEN_PERMISSION_KEYS_PREFIX}{username}:{domain}"


def register_api_token_permission_cache_key(
    username: str,
    domain: str,
    cache_key: str,
    ttl: int,
) -> None:
    """登记 API Token 快照键用于物理清理；权限正确性不依赖该索引。"""
    index_key = _get_api_token_keys_index(username, domain)
    cached_keys = cache.get(index_key) or set()
    cached_keys.add(cache_key)
    cache.set(index_key, cached_keys, ttl + 60)


def clear_api_token_permission_cache(username: str, domain: str) -> None:
    """清除指定用户在所有团队下的 API Token 权限快照。"""
    if hasattr(cache, "delete_pattern"):
        try:
            cache.delete_pattern(f"{_get_api_token_permission_prefix(username, domain)}*")
            cache.delete(_get_api_token_keys_index(username, domain))
            return
        except Exception as e:
            logger.warning(
                "Failed to clear API token permission cache by pattern for %s, falling back to index: %s",
                username,
                e,
            )

    index_key = _get_api_token_keys_index(username, domain)
    cached_keys = cache.get(index_key)
    if cached_keys:
        cache.delete_many(list(cached_keys))
    cache.delete(index_key)


def get_cached_permission_rules(
    username: str,
    domain: str,
    current_team: int,
    app_name: str,
    permission_key: str,
    include_children: bool = False,
    permission_version: Optional[int] = None,
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
    if permission_version is None:
        permission_version = get_user_permission_version(username, domain)
    cache_key = _get_cache_key(
        username,
        domain,
        current_team,
        app_name,
        permission_key,
        include_children,
        permission_version,
    )
    cached = cache.get(cache_key)
    if cached is not None and get_user_permission_version(username, domain) == permission_version:
        logger.debug(f"Permission rules cache hit: {username}@{app_name}/{permission_key}")
        return cached
    return None


def set_cached_permission_rules(
    username: str,
    domain: str,
    current_team: int,
    app_name: str,
    permission_key: str,
    permission_data: Dict,
    include_children: bool = False,
    permission_version: Optional[int] = None,
) -> bool:
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
    if permission_version is None:
        permission_version = get_user_permission_version(username, domain)
    if get_user_permission_version(username, domain) != permission_version:
        return False
    cache_key = _get_cache_key(
        username,
        domain,
        current_team,
        app_name,
        permission_key,
        include_children,
        permission_version,
    )
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
    return get_user_permission_version(username, domain) == permission_version


def _clear_user_permission_cache_entries(username: str, domain: str) -> None:
    """尽力清除缓存条目；权限正确性不依赖本操作成功。"""
    try:
        if hasattr(cache, "delete_pattern"):
            user_prefix = _get_user_perm_prefix(username, domain)
            try:
                cache.delete_pattern(f"{user_prefix}*")
                logger.info(f"Cleared permission cache (pattern) for user: {username}")
            except Exception as e:
                logger.warning(
                    "Failed to clear permission cache by pattern for %s, falling back to index: %s",
                    username,
                    e,
                )
                _clear_user_cache_by_index(username, domain)
        else:
            _clear_user_cache_by_index(username, domain)

        clear_api_token_permission_cache(username, domain)
        clear_token_info_cache(username, domain)
    except Exception as e:
        logger.warning("Failed to clean permission cache entries for %s@%s: %s", username, domain, e)


def clear_user_permission_cache(username: str, domain: str = "domain.com") -> None:
    """
    失效指定用户的权限缓存（含 token_info 与 API Secret 快照）。

    数据库代际在调用方事务内推进，跨 Worker 的权限读取立即改用新键；
    旧缓存条目在事务提交后尽力清理，清理失败不影响撤权正确性。
    """
    users = [{"username": username, "domain": domain}]
    _advance_user_permission_versions(users)
    transaction.on_commit(lambda: _clear_user_permission_cache_entries(username, domain))


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
    identities = {(user.get("username"), user.get("domain", "domain.com")) for user in users if user.get("username")}
    normalized_users = [{"username": username, "domain": domain} for username, domain in sorted(identities)]
    _advance_user_permission_versions(normalized_users)

    def clear_entries():
        for user in normalized_users:
            _clear_user_permission_cache_entries(user["username"], user["domain"])

    transaction.on_commit(clear_entries)


def clear_all_permission_cache() -> None:
    """
    推进所有用户权限代际，并在提交后尽力清除全部权限缓存。

    不支持 pattern delete 的后端无法物理删除全部条目，但旧权限缓存因代际变化已不可达。
    """
    _advance_all_user_permission_versions()

    def clear_entries():
        try:
            if hasattr(cache, "delete_pattern"):
                # 清除所有权限缓存（含新格式 perm_rules:{user_prefix}:* 和旧版索引键）
                cache.delete_pattern(f"{PERM_CACHE_PREFIX}*")
                cache.delete_pattern(f"{USER_PERM_KEYS_PREFIX}*")
                cache.delete_pattern(f"{TOKEN_INFO_PREFIX}*")
                cache.delete_pattern(f"{API_TOKEN_PERMISSION_CACHE_PREFIX}:*")
                cache.delete_pattern(f"{API_TOKEN_PERMISSION_KEYS_PREFIX}*")
                logger.info("All permission rules cache cleared")
            else:
                logger.warning("Cannot clear all permission cache: cache backend does not support pattern delete")
        except Exception as e:
            logger.warning(f"Failed to clear all permission cache: {e}")

    transaction.on_commit(clear_entries)
