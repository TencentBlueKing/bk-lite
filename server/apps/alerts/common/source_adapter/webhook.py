# -- coding: utf-8 --
# @File: webhook.py
# @Time: 2025/5/13 15:59
# @Author: windyzhao
import json

from typing import Dict, Any, List

from django.http import HttpRequest

from apps.alerts.common.source_adapter.base import AlertSourceAdapter

from apps.alerts.models.models import Event
from apps.alerts.common.source_adapter import logger


class WebhookAdapter(AlertSourceAdapter):
    """Webhook告警源适配器"""

    def fetch_alerts(self) -> List[Dict[str, Any]]:
        # Webhook通常是推送模式，所以fetch方法可能返回空列表
        return []

    def process_webhook_request(self, request: HttpRequest) -> Event:
        """处理Webhook请求"""
        try:
            if request.content_type == 'application/json':
                data = json.loads(request.body)
            else:
                data = request.POST.dict()

            return self._transform_alert_to_event(data)
        except Exception as e:
            logger.error(f"Failed to process webhook request: {e}")
            raise

    def test_connection(self) -> bool:
        # Webhook不需要主动连接测试
        return True

    @staticmethod
    def validate_config(config: Dict[str, Any]) -> bool:
        # Webhook通常只需要验证是否有必要的认证配置
        return True
