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
            import apps.alerts.nats  # noqa


def adapters():
    """注册告警源适配器"""
    try:
        from apps.alerts.common.source_adapter.base import AlertSourceAdapterFactory
        from apps.alerts.common.source_adapter.restful import RestFulAdapter
        from apps.alerts.common.source_adapter.nats import NatsAdapter
        AlertSourceAdapterFactory.register_adapter('restful', RestFulAdapter)
        AlertSourceAdapterFactory.register_adapter("nats", NatsAdapter)
    except Exception as e:
        logger.error(f"Failed to register alert source adapter: {e}")
        pass
