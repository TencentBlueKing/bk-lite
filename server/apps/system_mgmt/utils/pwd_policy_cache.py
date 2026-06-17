"""密码策略配置缓存工具。

将 login 路径中原本分散的多次单键 SystemSettings 查询合并为一次批量查询，
并以短 TTL 缓存，避免暴力破解场景下每次密码错误触发 2-4 次 DB 读取。

管理员通过 update_sys_set 更新 pwd_set_* 配置时应调用 invalidate_pwd_policy_cache()
使缓存立即失效，确保新策略在下次 login 调用时生效。
"""

from django.core.cache import cache

PWD_POLICY_CACHE_KEY = "system_settings:pwd_policy"
PWD_POLICY_CACHE_TTL = 300  # 5 分钟；管理员更新设置时会主动清除

PWD_POLICY_KEYS = [
    "pwd_set_max_retry_count",
    "pwd_set_lock_duration",
    "pwd_set_validity_period",
    "pwd_set_expiry_reminder_days",
]

PWD_POLICY_DEFAULTS = {
    "pwd_set_max_retry_count": 5,
    "pwd_set_lock_duration": 180,
    "pwd_set_validity_period": 90,
    "pwd_set_expiry_reminder_days": 7,
}


def get_pwd_policy_settings():
    """批量读取密码策略配置并缓存，避免 login handler 中多次单键 DB 查询。

    返回 dict，key 为配置名（str），value 为整型值；缺失 key 使用 PWD_POLICY_DEFAULTS 中的默认值。
    结果缓存 PWD_POLICY_CACHE_TTL 秒；管理员更新 pwd_set_* 配置后由 invalidate_pwd_policy_cache() 主动清除。
    """
    cached = cache.get(PWD_POLICY_CACHE_KEY)
    if cached is not None:
        return cached

    # 延迟导入避免循环依赖
    from apps.system_mgmt.models.system_settings import SystemSettings

    rows = SystemSettings.objects.filter(key__in=PWD_POLICY_KEYS).values("key", "value")
    result = dict(PWD_POLICY_DEFAULTS)
    for row in rows:
        try:
            result[row["key"]] = int(row["value"])
        except (TypeError, ValueError):
            pass
    cache.set(PWD_POLICY_CACHE_KEY, result, PWD_POLICY_CACHE_TTL)
    return result


def invalidate_pwd_policy_cache():
    """管理员更新密码策略设置后调用，清除 login 路径缓存使新策略立即生效。"""
    cache.delete(PWD_POLICY_CACHE_KEY)
