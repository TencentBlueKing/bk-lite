# -- coding: utf-8 --
# @File: init_alert_rules.py
# @Time: 2026/5/15 11:03
# @Author: windyzhao

from django.core.management.base import BaseCommand
from apps.core.logger import alert_logger as logger
from apps.alerts.models.alert_operator import AlarmStrategy
from apps.alerts.models.alert_source import AlertSource


class Command(BaseCommand):
    help = "初始化告警聚合规则"

    @property
    def data(self):

        nats_source = AlertSource.objects.get(source_id="nats")

        data = {
            "name": "内置检测规则",
            "strategy_type": "smart_denoise",
            "description": "",
            "team": [1],
            "dispatch_team": [1],
            "match_rules": [[{"key": "source_id", "operator": "eq", "value": nats_source.id}]],
            "params": {
                "policy": "service",
                "group_by": ["service", "location", "resource_name", "item"],
                "window_size": 2,
                "time_out": False
            },
            "auto_close": True,
            "close_minutes": 120
        }
        return data

    def handle(self, *args, **options):
        """初始化告警聚合规则"""
        logger.info("===开始初始化告警聚合规则===")

        instance_count = AlarmStrategy.objects.all().count()
        if not instance_count:
            AlarmStrategy.objects.create(**self.data)
            logger.info("[AlertInit] 成功初始化内置的告警聚合规则")
        else:
            logger.info("[AlertInit] 存在告警聚合规则，跳过初始化")
