# -- coding: utf-8 --
# @File: apps.py
# @Time: 2025/7/14 16:01
# @Author: windyzhao

from django.apps import AppConfig


class AlertsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.operation_analysis"

    def ready(self):
        import apps.operation_analysis.nats.nats  # noqa

