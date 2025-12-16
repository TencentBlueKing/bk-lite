# -- coding: utf-8 --
# @File: base.py
# @Time: 2025/9/19 14:47
# @Author: windyzhao
import uuid
from abc import ABC, abstractmethod
from typing import List, Tuple, Dict, Any
from collections import defaultdict

from django.utils import timezone

from apps.alerts.models import CorrelationRules
from apps.alerts.common.aggregation.alert_processor import AlertProcessor
from apps.core.logger import alert_logger as logger


class BaseWindowProcessor(ABC):
    """窗口处理器基类"""

    def __init__(self, window_size: str = "10min"):
        self.window_size = window_size
        self.processor = AlertProcessor(window_size=window_size)
        self.now = timezone.now()

    @property
    def fields(self):
        data = [
            "event_id", "external_id", "item", "received_at", "status", "level", "source__name",
            "source_id", "title", "rule_id", "description", "resource_id", "resource_type", "resource_name", "value"
        ]
        return data

    @abstractmethod
    def process_rules(self, rules: List[CorrelationRules]) -> Tuple[int, int]:
        """
        处理规则的抽象方法

        Args:
            rules: 要处理的规则列表

        Returns:
            Tuple[int, int]: (新建告警数, 更新告警数)
        """
        pass

    @abstractmethod
    def get_window_type(self) -> str:
        """获取窗口类型"""
        pass

    def _group_rules_by_window_size(self, rules: List[CorrelationRules]) -> Dict[str, List[CorrelationRules]]:
        """
        按窗口大小分组规则

        Args:
            rules: 规则列表

        Returns:
            Dict[str, List[CorrelationRules]]: 按窗口大小分组的规则
        """
        grouped_rules = defaultdict(list)
        for rule in rules:
            # 根据窗口类型获取相应的窗口大小
            if self.get_window_type() == 'session':
                window_size = getattr(rule, 'session_timeout', '10min')
            else:
                window_size = getattr(rule, 'window_size', '10min')
            grouped_rules[window_size].append(rule)
        return dict(grouped_rules)

    def _execute_processing(self, format_alert_list: List[Dict[str, Any]],
                            update_alert_list: List[Dict[str, Any]]) -> Tuple[int, int]:
        """执行告警创建和更新的公共方法"""
        alerts_created = 0
        alerts_updated = len(update_alert_list)

        try:
            if format_alert_list:
                created_ids = self.processor.bulk_create_alerts(alerts=format_alert_list)
                alerts_created = len(created_ids)
                if created_ids:
                    self.processor.alert_auto_assign(alert_id_list=created_ids)

        except Exception as e:  # noqa
            import traceback
            logger.error(f"执行{self.get_window_type()}窗口告警处理新增告警失败: {traceback.format_exc()}")

        try:

            if update_alert_list:
                self.processor.update_alerts(alerts=update_alert_list)
        except Exception as e:  # noqa
            import traceback
            logger.error(f"执行{self.get_window_type()}窗口告警处理更新告警失败: {traceback.format_exc()}")

        return alerts_created, alerts_updated
