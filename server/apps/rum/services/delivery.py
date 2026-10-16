from __future__ import annotations

PRODUCER = "lite-rum"


class SystemMgmtAlertDispatcher:
    """以 lite-rum 身份把投递箱记录交给系统管理的公开投递契约。"""

    def __init__(self, *, client=None):
        self.client = client

    def dispatch(self, delivery: dict) -> dict:
        client = self.client
        if client is None:
            from apps.rpc.system_mgmt import SystemMgmt

            client = SystemMgmt()
        payload = dict(delivery.get("payload") or {})
        try:
            response = client.dispatch_notification(
                delivery_key=delivery.get("deliveryKey") or "",
                channel_id=delivery.get("channelId"),
                organization_ids=list(payload.get("organizations") or []),
                recipients=list(delivery.get("recipients") or []),
                title=delivery.get("title") or "",
                body=delivery.get("body") or "",
                event_payload=payload,
                producer=PRODUCER,
                internal_caller=PRODUCER,
            )
        except Exception:
            return {
                "delivered": False,
                "retryable": True,
                "code": "notification_rpc_unavailable",
                "message": "通知投递接口暂不可用。",
            }
        if not isinstance(response, dict):
            return {
                "delivered": False,
                "retryable": True,
                "code": "invalid_dispatch_response",
                "message": "通知投递返回格式无效。",
            }
        delivered = response.get("result") is True
        return {
            "delivered": delivered,
            "code": str(response.get("code") or ("delivered" if delivered else "delivery_failed"))[:128],
            "retryable": False if delivered else bool(response.get("retryable", True)),
            "message": str(response.get("message") or ("success" if delivered else "通知投递失败。"))[:512],
        }
