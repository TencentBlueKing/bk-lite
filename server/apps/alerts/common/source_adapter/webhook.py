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

            # 路由到批量丰富路径（与主流程 create_events 保持一致）
            saved_batches = self.create_events([data])
            # saved_batches 是 [[Event, ...], ...] 的分批列表；取第一个事件返回
            for batch in saved_batches:
                if batch:
                    return batch[0]
            return None
        except Exception as e:
            logger.error("[AlertSource] 处理 webhook 请求失败: %s", e, exc_info=True)
            raise

    def test_connection(self) -> bool:
        # Webhook不需要主动连接测试
        return True

    @staticmethod
    def validate_config(config: Dict[str, Any]) -> bool:
        # Webhook通常只需要验证是否有必要的认证配置
        return True
