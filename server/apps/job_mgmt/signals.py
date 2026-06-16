"""job_mgmt 信号处理：规则变更时主动失效缓存。"""

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.job_mgmt.models import DangerousPath, DangerousRule
from apps.job_mgmt.services.dangerous_checker import (
    _CMD_RULES_CACHE_KEY,
    _PATH_RULES_CACHE_KEY,
)


@receiver([post_save, post_delete], sender=DangerousRule)
def invalidate_cmd_rules_cache(sender, **kwargs):
    """DangerousRule 新增/修改/删除时失效命令规则缓存。"""
    from django.core.cache import cache

    cache.delete(_CMD_RULES_CACHE_KEY)


@receiver([post_save, post_delete], sender=DangerousPath)
def invalidate_path_rules_cache(sender, **kwargs):
    """DangerousPath 新增/修改/删除时失效路径规则缓存。"""
    from django.core.cache import cache

    cache.delete(_PATH_RULES_CACHE_KEY)
