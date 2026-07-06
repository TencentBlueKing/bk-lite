# -- coding: utf-8 --
# @File: apps.py
# @Time: 2025/5/9 14:51
# @Author: windyzhao
import sys

from django.apps import AppConfig

from apps.core.logger import alert_logger as logger


class AlertsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.alerts"

    def ready(self):
        # 检查是否正在运行迁移命令
        is_running_migrations = 'makemigrations' in sys.argv or 'migrate' in sys.argv
        if not is_running_migrations:
            import apps.alerts.nats.nats  # noqa
            # 注册即时告警策略缓存失效信号
            _register_instant_cache_signals()
            # 注册 Level 模型缓存失效信号
            _register_level_cache_signals()


def _register_instant_cache_signals():
    """注册 AlarmStrategy save/delete 信号 → 失效即时告警策略缓存。

    确保启停 / 编辑 / 删除策略后旁路立即生效，避免最长 60s TTL 窗口内的不一致。
    """
    try:
        from django.db.models.signals import post_save, post_delete
        from apps.alerts.aggregation.processor.instant_dispatcher import InstantStrategyCache
        from apps.alerts.models.alert_operator import AlarmStrategy

        def _invalidate(sender, **kwargs):
            InstantStrategyCache.cache_clear()

        post_save.connect(
            _invalidate,
            sender=AlarmStrategy,
            dispatch_uid="instant_cache_post_save",
            weak=False,
        )
        post_delete.connect(
            _invalidate,
            sender=AlarmStrategy,
            dispatch_uid="instant_cache_post_delete",
            weak=False,
        )
    except Exception as e:  # noqa
        logger.error("[AlertInit] 注册即时告警缓存信号失败: %s", e, exc_info=True)


def _register_level_cache_signals():
    """注册 Level save/delete 信号 → 失效 AlertBuilder 进程级级别缓存。

    Level 配置变更（新增、删除、修改 level_id）后，下轮 Celery Beat 聚合任务
    将重新从 DB 加载有效级别集合，保证映射结果与最新配置一致。
    """
    try:
        from django.db.models.signals import post_save, post_delete
        from apps.alerts.aggregation.builder.alert_builder import AlertBuilder
        from apps.alerts.models.models import Level

        def _invalidate_level_cache(sender, **kwargs):
            AlertBuilder._valid_alert_levels = None
            logger.info("[AlertInit] Level 配置变更，已清除 AlertBuilder 级别缓存")

        post_save.connect(_invalidate_level_cache, sender=Level, dispatch_uid="alert_builder_level_post_save", weak=False)
        post_delete.connect(_invalidate_level_cache, sender=Level, dispatch_uid="alert_builder_level_post_delete", weak=False)
    except Exception as e:  # noqa
        logger.error("[AlertInit] 注册 Level 缓存失效信号失败: %s", e, exc_info=True)
