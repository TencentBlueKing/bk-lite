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
            # 注册告警源适配器
            adapters()
            import apps.alerts.nats.nats # noqa
            # 注册即时告警策略缓存失效信号
            _register_instant_cache_signals()


def adapters():
    """注册告警源适配器"""
    try:
        from apps.alerts.common.source_adapter.base import AlertSourceAdapterFactory
        from apps.alerts.common.source_adapter.restful import RestFulAdapter
        from apps.alerts.common.source_adapter.nats import NatsAdapter
        from apps.alerts.common.source_adapter.prometheus import PrometheusAdapter
        from apps.alerts.common.source_adapter.zabbix import ZabbixAdapter

        AlertSourceAdapterFactory.register_adapter('restful', RestFulAdapter)
        AlertSourceAdapterFactory.register_adapter("nats", NatsAdapter)
        AlertSourceAdapterFactory.register_adapter("prometheus", PrometheusAdapter)
        AlertSourceAdapterFactory.register_adapter("zabbix", ZabbixAdapter)
    except Exception as e:
        logger.error(f"Failed to register alert source adapter: {e}", exc_info=True)
        raise


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

        post_save.connect(_invalidate, sender=AlarmStrategy, dispatch_uid="instant_cache_post_save")
        post_delete.connect(_invalidate, sender=AlarmStrategy, dispatch_uid="instant_cache_post_delete")
    except Exception as e:  # noqa
        logger.error(f"Failed to register instant cache signals: {e}", exc_info=True)
