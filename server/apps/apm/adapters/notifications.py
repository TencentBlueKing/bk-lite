from __future__ import annotations

from apps.apm.services.contracts import (
    NotificationDelivery,
    NotificationDeliveryResult,
)
from apps.rpc.system_mgmt import SystemMgmt


class SystemMgmtNotificationDispatcher:
    """只依赖 System Management 公开投递契约的通用通知 adapter。"""

    def __init__(self, *, client=None):
        self.client = client or SystemMgmt()

    def dispatch(self, delivery: NotificationDelivery) -> NotificationDeliveryResult:
        try:
            response = self.client.dispatch_notification(
                delivery_key=delivery.delivery_key,
                channel_id=delivery.channel_id,
                organization_ids=list(delivery.organization_ids),
                recipients=list(delivery.recipients),
                title=delivery.title,
                body=delivery.body,
                event_payload=dict(delivery.event_payload),
            )
        except Exception:
            return NotificationDeliveryResult(
                delivered=False,
                code="notification_rpc_unavailable",
                retryable=True,
                message="System Management 通知投递接口暂不可用。",
            )
        if not isinstance(response, dict):
            return NotificationDeliveryResult(
                delivered=False,
                code="invalid_dispatch_response",
                retryable=True,
                message="System Management 通知投递返回格式无效。",
            )
        delivered = response.get("result") is True
        return NotificationDeliveryResult(
            delivered=delivered,
            code=str(response.get("code") or ("delivered" if delivered else "delivery_failed"))[:128],
            retryable=False if delivered else bool(response.get("retryable", True)),
            message=str(response.get("message") or ("success" if delivered else "通知投递失败。"))[:512],
        )
