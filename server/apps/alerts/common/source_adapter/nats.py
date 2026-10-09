# -- coding: utf-8 --
# @File: nats.py
# @Time: 2026/2/10 15:54
# @Author: windyzhao
from abc import ABC
from typing import Any, Dict, List

from apps.alerts.common.source_adapter.base import AlertSourceAdapter
from apps.alerts.utils.permission_scope import normalize_team_ids


class NatsAdapter(AlertSourceAdapter, ABC):
    """Nats告警源适配器"""

    def _resolve_event_team(self, alert: Dict[str, Any]) -> List:
        if self.trusted_internal:
            organizations = normalize_team_ids(alert.get("organizations"))
            if organizations:
                return organizations
        return self.resolved_team

    def fetch_alerts(self) -> List[Dict[str, Any]]:
        pass

    def test_connection(self) -> bool:
        return True

    @staticmethod
    def validate_config(config: Dict[str, Any]) -> bool:
        return True
