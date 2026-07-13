"""SSRF 内网白名单缓存。

将 SSRFValidator.validate() 热路径上的白名单查询合并为一次查询并短 TTL 缓存；
管理员增删改白名单后调用 invalidate_network_whitelist_cache() 主动失效。
"""

from django.core.cache import cache

NETWORK_WHITELIST_CACHE_KEY = "system_settings:network_white_list"
NETWORK_WHITELIST_CACHE_TTL = 300  # 5 分钟；写操作主动清除


def get_network_whitelist_cidrs() -> list:
    """返回启用中的规范化 CIDR 字符串列表（缓存字符串，避免跨缓存后端 pickle 问题）。

    任何异常（表不存在 / app 未安装 / DB 异常）都返回空列表（fail-closed，维持严格校验）。
    """
    cached = cache.get(NETWORK_WHITELIST_CACHE_KEY)
    if cached is not None:
        return cached
    try:
        from apps.system_mgmt.models.network_white_list import NetworkWhiteList

        rows = list(NetworkWhiteList.objects.filter(enabled=True).values_list("network", flat=True))
    except Exception:
        rows = []
    cache.set(NETWORK_WHITELIST_CACHE_KEY, rows, NETWORK_WHITELIST_CACHE_TTL)
    return rows


def invalidate_network_whitelist_cache() -> None:
    cache.delete(NETWORK_WHITELIST_CACHE_KEY)
