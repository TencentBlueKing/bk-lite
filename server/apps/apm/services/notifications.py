from __future__ import annotations

from apps.apm.services.contracts import NotificationChannel, NotificationRecipient
from apps.rpc.system_mgmt import SystemMgmt


CHANNEL_DELIVERY_MODES = {"message", "alert_event_copy"}
CHANNEL_RECIPIENT_MODES = {"none", "system_user", "free_text"}
CHANNEL_AVAILABILITY = {"available", "unavailable"}


class NotificationChannelDirectory:
    """通过 System Management 的公开 RPC 查询能力驱动的通知渠道。"""

    def __init__(self, *, client=None):
        self.client = client or SystemMgmt()

    def list_available(
        self,
        *,
        actor_context: dict,
        organization_id: int,
        include_children: bool,
    ) -> list[NotificationChannel]:
        response = self.client.list_notification_channels_scoped(
            actor_context,
            teams=[organization_id],
            include_children=include_children,
        )
        if not isinstance(response, dict) or response.get("result") is False:
            message = response.get("message") if isinstance(response, dict) else "返回格式无效"
            raise RuntimeError(message or "通知渠道目录不可用")
        channels = response.get("data") or []
        if not isinstance(channels, list):
            raise RuntimeError("通知渠道目录返回格式无效")
        result = []
        for channel in channels:
            try:
                item = NotificationChannel(
                    id=int(channel["id"]),
                    name=str(channel["name"]),
                    channel_type=str(channel["channel_type"]),
                    description=str(channel.get("description") or ""),
                    delivery_mode=str(channel["delivery_mode"]),
                    recipient_mode=str(channel["recipient_mode"]),
                    availability=str(channel["availability"]),
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise RuntimeError("通知渠道目录返回格式无效") from exc
            if (
                item.delivery_mode not in CHANNEL_DELIVERY_MODES
                or item.recipient_mode not in CHANNEL_RECIPIENT_MODES
                or item.availability not in CHANNEL_AVAILABILITY
            ):
                raise RuntimeError("通知渠道目录返回未知能力")
            result.append(item)
        return result

    def search_recipients(
        self,
        *,
        actor_context: dict,
        organization_id: int,
        include_children: bool,
        search: str,
        limit: int,
    ) -> list[NotificationRecipient]:
        response = self.client.search_notification_recipients_scoped(
            actor_context,
            teams=[organization_id],
            include_children=include_children,
            search=search,
            limit=limit,
        )
        if not isinstance(response, dict) or response.get("result") is False:
            message = response.get("message") if isinstance(response, dict) else "返回格式无效"
            raise RuntimeError(message or "通知接收人目录不可用")
        recipients = response.get("data") or []
        if not isinstance(recipients, list):
            raise RuntimeError("通知接收人目录返回格式无效")
        try:
            return [
                NotificationRecipient(
                    id=int(recipient["id"]),
                    username=str(recipient["username"]),
                    display_name=str(recipient.get("display_name") or ""),
                )
                for recipient in recipients
            ]
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError("通知接收人目录返回格式无效") from exc
