from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from apps.apm.constants import APM_ALERT_PUSHER
from apps.apm.services.contracts import ApmAlertEvent, PublishResult
from apps.rpc.system_mgmt import SystemMgmt


class SystemMgmtNatsAlertPublisher:
    """通过系统管理的 NATS 通知渠道发送 APM 事件副本。"""

    def __init__(self, *, client=None):
        self.client = client or SystemMgmt()

    def publish(self, events: Sequence[ApmAlertEvent]) -> PublishResult:
        if not events:
            return PublishResult(accepted=0)

        grouped: dict[tuple[int, tuple[str, ...]], list[ApmAlertEvent]] = defaultdict(list)
        for event in events:
            if event.channel_id is None:
                raise ValueError("APM 通知事件缺少 channel_id")
            grouped[(event.channel_id, event.receivers)].append(event)

        accepted = duplicates = 0
        for (channel_id, receivers), grouped_events in grouped.items():
            response = self.client.send_msg_with_channel(
                channel_id,
                "",
                {
                    "source_id": "nats",
                    "pusher": APM_ALERT_PUSHER,
                    "events": [dict(event.payload) for event in grouped_events],
                },
                list(receivers),
            )
            if not isinstance(response, dict):
                raise RuntimeError("APM NATS 通知渠道返回格式无效")
            data = response.get("data") or {}
            ingestion = data.get("ingestion") or {}
            if ingestion:
                batch_accepted = int(ingestion.get("accepted", 0) or 0)
                batch_duplicates = int(ingestion.get("skipped", 0) or 0)
                batch_failed = int(ingestion.get("errored", 0) or 0)
                if batch_failed or batch_accepted + batch_duplicates < len(grouped_events):
                    raise RuntimeError(response.get("message") or "APM NATS 通知渠道未接受完整事件批次")
                accepted += batch_accepted
                duplicates += batch_duplicates
            else:
                if response.get("result") is False:
                    raise RuntimeError(response.get("message") or "APM NATS 通知渠道拒绝事件")
                accepted += len(grouped_events)
        return PublishResult(accepted=accepted, duplicates=duplicates)
