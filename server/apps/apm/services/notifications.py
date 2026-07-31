from __future__ import annotations

from apps.rpc.system_mgmt import SystemMgmt


ALERT_EVENT_METHOD = "receive_alert_events"


class NotificationChannelDirectory:
    """通过 System Management 的公开 RPC 查询 APM 可用的告警事件渠道。"""

    def __init__(self, *, client=None):
        self.client = client or SystemMgmt()

    def list_alert_event_channels(
        self,
        *,
        actor_context: dict,
        organization_id: int,
        include_children: bool,
    ) -> list[dict]:
        response = self.client.search_channel_list_scoped(
            actor_context,
            channel_type="nats",
            teams=[organization_id],
            include_children=include_children,
            channel_method=ALERT_EVENT_METHOD,
        )
        if not isinstance(response, dict) or response.get("result") is False:
            message = response.get("message") if isinstance(response, dict) else "返回格式无效"
            raise RuntimeError(message or "通知渠道目录不可用")
        channels = response.get("data") or []
        return [
            channel
            for channel in channels
            if channel.get("channel_type") == "nats"
        ]
