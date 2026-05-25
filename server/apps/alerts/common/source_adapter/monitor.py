# -- coding: utf-8 --
# @File: monitor.py
# @Time: 2025/5/14 10:17
# @Author: windyzhao
from abc import ABC
from typing import Dict, Any, List

from apps.alerts.common.source_adapter.base import AlertSourceAdapter


class MonitorAdapter(AlertSourceAdapter, ABC):
    """x-monitor告警源适配器"""

    def fetch_alerts(self) -> List[Dict[str, Any]]:
        pass

    def test_connection(self) -> bool:
        return True

    @staticmethod
    def validate_config(config: Dict[str, Any]) -> bool:
        return True
