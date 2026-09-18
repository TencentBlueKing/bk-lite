# -- coding: utf-8 --
# @File: init_alert_rules.py
# @Time: 2026/5/15 11:03
# @Author: windyzhao

from django.core.management.base import BaseCommand

from apps.alerts.models.alert_operator import AlarmStrategy
from apps.alerts.models.alert_source import AlertSource
from apps.core.logger import alert_logger as logger

BUILTIN_RULE_NAME = "内置检测规则"


def _nats_match_rules(nats_source):
    return [[{"key": "source_name", "operator": "any_of", "value": [nats_source.name]}]]


def _is_legacy_source_id_filter(match_rules, nats_source):
    return match_rules == [[{"key": "source_id", "operator": "eq", "value": nats_source.id}]]


class Command(BaseCommand):
    help = "初始化告警聚合规则"

    @property
    def data(self):
        nats_source = AlertSource.objects.get(source_id="nats")
        return {
            "name": BUILTIN_RULE_NAME,
            "strategy_type": "smart_denoise",
            "description": "",
            "team": [1],
            "dispatch_team": [1],
            "match_rules": _nats_match_rules(nats_source),
            "params": {
                "policy": "service",
                "group_by": ["service", "location", "resource_name", "item"],
                "window_size": 2,
                "time_out": False,
            },
            "auto_close": True,
            "close_minutes": 120,
        }

    def handle(self, *args, **options):
        """初始化告警聚合规则"""
        logger.info("===开始初始化告警聚合规则===")
        nats_source = AlertSource.objects.get(source_id="nats")
        builtin = AlarmStrategy.objects.filter(name=BUILTIN_RULE_NAME).first()
        if builtin is None:
            if AlarmStrategy.objects.exists():
                logger.info("[AlertInit] 存在告警聚合规则，跳过初始化")
                return
            AlarmStrategy.objects.create(**self.data)
            logger.info("[AlertInit] 成功初始化内置的告警聚合规则")
            return
        if _is_legacy_source_id_filter(builtin.match_rules, nats_source):
            builtin.match_rules = _nats_match_rules(nats_source)
            builtin.save(update_fields=["match_rules"])
            logger.info("[AlertInit] 已将内置检测规则筛选条件升级为当前集成源契约")
            return
        logger.info("[AlertInit] 存在告警聚合规则，跳过初始化")
