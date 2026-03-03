# -- coding: utf-8 --
# @File: nats.py
# @Time: 2026/2/10 15:54
# @Author: windyzhao
from abc import ABC
from typing import Dict, Any, List

from apps.alerts.common.source_adapter.base import AlertSourceAdapter
from apps.alerts.error import AuthenticationSourceError


class NatsAdapter(AlertSourceAdapter, ABC):
    """Nats告警源适配器"""

    def authenticate(self) -> bool:
        # 这里可以实现一些通用的认证逻辑
        if self.secret == self.alert_source.secret:
            return True
        raise AuthenticationSourceError("Authentication failed")

    def fetch_alerts(self) -> List[Dict[str, Any]]:
        pass

    def test_connection(self) -> bool:
        return True

    @staticmethod
    def validate_config(config: Dict[str, Any]) -> bool:
        return True
