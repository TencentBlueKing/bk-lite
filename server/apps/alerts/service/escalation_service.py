# -- coding: utf-8 --
import logging
from datetime import timedelta
from typing import Any, Dict, List, Optional

from django.db import connection, transaction
from django.utils import timezone

from apps.alerts.constants.constants import AlertStatus, SessionStatus
from apps.alerts.models.alert_operator import (
    AlertAssignment,
    AlertEscalationTask,
    AlertReminderTask,
)
from apps.alerts.models.models import Alert

logger = logging.getLogger(__name__)

VALID_MODES = ("append", "replace")


class EscalationService:
    EXPIRED_DAYS = 30

    @staticmethod
    def parse_escalation_config(config: Optional[dict]) -> Optional[dict]:
        """解析并规范化升级链配置。无效或未启用返回 None。"""
        if not config:
            return None
        block = config.get("escalation") if isinstance(config, dict) else None
        if not block or not block.get("enabled"):
            return None
        mode = block.get("mode")
        if mode not in VALID_MODES:
            logger.warning("升级链模式非法: mode=%s", mode)
            return None
        raw_layers = block.get("layers") or []
        if not isinstance(raw_layers, list) or len(raw_layers) == 0:
            return None
        layers: List[dict] = []
        for idx, layer in enumerate(raw_layers):
            personnel = layer.get("personnel") or []
            if not isinstance(personnel, list) or len(personnel) == 0:
                logger.warning("升级链第 %s 层缺少处理人", idx)
                return None
            try:
                wait_minutes = int(layer.get("wait_minutes", 0) or 0)
            except (TypeError, ValueError):
                return None
            if wait_minutes <= 0:
                logger.warning("升级链第 %s 层等待时长非法: %s", idx, layer.get("wait_minutes"))
                return None
            layers.append({
                "personnel": list(dict.fromkeys(personnel)),
                "wait_minutes": wait_minutes,
                "notify_channels": layer.get("notify_channels") or [],
            })
        return {"mode": mode, "layers": layers}

    @staticmethod
    def compute_roster(layers: List[dict], current_index: int, mode: str) -> List[str]:
        """当前在岗集合（去重保序）。replace=本层；append=0..current 并集。"""
        if mode == "replace":
            source = layers[current_index].get("personnel", [])
        else:
            source = []
            for layer in layers[: current_index + 1]:
                source.extend(layer.get("personnel", []))
        return list(dict.fromkeys(source))
