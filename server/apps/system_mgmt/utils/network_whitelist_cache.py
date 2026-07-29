"""SSRF 出站白名单缓存。

热路径上的白名单查询合并为一次查询并短 TTL 缓存；
管理员增删改白名单后调用 invalidate_network_whitelist_cache() 主动失效。

缓存载荷结构:(cidrs, domains) 元组;cidrs 与 domains 互相独立,空字符串或 None 项被过滤。
"""

from django.core.cache import cache

NETWORK_WHITELIST_CACHE_KEY = "system_settings:network_white_list"
NETWORK_WHITELIST_CACHE_TTL = 300  # 5 分钟；写操作主动清除


def _load_whitelist_from_db() -> tuple[list[str], list[str]]:
    """从 DB 加载启用中的白名单条目。异常时返回 (空, 空)(fail-closed)。"""
    try:
        from apps.system_mgmt.models.network_white_list import NetworkWhiteList

        rows = NetworkWhiteList.objects.filter(enabled=True).values("network", "domain_name")
        cidrs = [r["network"] for r in rows if r.get("network")]
        domains = [r["domain_name"] for r in rows if r.get("domain_name")]
        return cidrs, domains
    except Exception:
        return [], []


def _read_cache() -> tuple[list[str], list[str]] | None:
    """读取缓存;老格式(纯列表)视为缓存未命中,失败-关闭"""
    cached = cache.get(NETWORK_WHITELIST_CACHE_KEY)
    if cached is None:
        return None
    if isinstance(cached, list):
        # 老版载荷结构:仅 cidrs;视为失效,清掉并返回 None
        cache.delete(NETWORK_WHITELIST_CACHE_KEY)
        return None
    if isinstance(cached, tuple) and len(cached) == 2:
        cidrs, domains = cached
        if isinstance(cidrs, list) and isinstance(domains, list):
            return cidrs, domains
    return None


def get_network_whitelist_cidrs() -> list[str]:
    """返回启用中的 CIDR 字符串列表(空字符串已过滤)。fail-closed。"""
    cached = _read_cache()
    if cached is not None:
        return cached[0]
    cidrs, domains = _load_whitelist_from_db()
    cache.set(NETWORK_WHITELIST_CACHE_KEY, (cidrs, domains), NETWORK_WHITELIST_CACHE_TTL)
    return cidrs


def get_network_whitelist_domains() -> list[str]:
    """返回启用中的 domain 字符串列表(小写,空字符串已过滤)。fail-closed。"""
    cached = _read_cache()
    if cached is not None:
        return cached[1]
    cidrs, domains = _load_whitelist_from_db()
    cache.set(NETWORK_WHITELIST_CACHE_KEY, (cidrs, domains), NETWORK_WHITELIST_CACHE_TTL)
    return domains


def invalidate_network_whitelist_cache() -> None:
    cache.delete(NETWORK_WHITELIST_CACHE_KEY)
