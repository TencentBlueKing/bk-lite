from __future__ import annotations

from copy import deepcopy
from collections.abc import Sequence

from apps.apm.constants import APM_ALERT_PUSHER, APM_ALERT_SOURCE_ID
from apps.apm.services.contracts import ApmAlertEvent, PublishResult
from apps.rpc.base import RpcClient


class AlertsNatsPublisher:
    """通过 Alerts 的标准 NATS 接入契约发布 APM 生命周期事件。"""

    def __init__(self, *, client=None):
        self.client = client or RpcClient()

    def publish(self, events: Sequence[ApmAlertEvent]) -> PublishResult:
        if not events:
            return PublishResult(accepted=0)
        response = self.client.run(
            "receive_alert_events",
            source_id=APM_ALERT_SOURCE_ID,
            pusher=APM_ALERT_PUSHER,
            events=[dict(event.payload) for event in events],
        )
        if not isinstance(response, dict):
            raise RuntimeError("Alerts 返回格式无效")
        data = response.get("data") or {}
        ingestion = data.get("ingestion") or {}
        accepted = int(ingestion.get("accepted", data.get("processed_events", 0)) or 0)
        errored = int(ingestion.get("errored", 0) or 0)
        skipped = int(ingestion.get("skipped", 0) or 0)
        if errored or (response.get("result") is False and accepted + skipped < len(events)):
            raise RuntimeError(response.get("message") or "Alerts 拒绝 APM 事件")
        # APM 只会发送自身构造的完整 payload；无转换错误时，skipped 表示接入幂等键已存在。
        return PublishResult(accepted=accepted, duplicates=skipped)


def reconcile_apm_alert_source():
    """运行期幂等声明 APM 专属 NATS source，不作为 Server 启动门禁。"""

    from apps.alerts.common.source_adapter.constants import DEFAULT_SOURCE_CONFIG
    from apps.alerts.constants.constants import AlertAccessType, AlertsSourceTypes
    from apps.alerts.models.alert_source import AlertSource

    defaults = {
        "name": "BK-Lite APM",
        "source_type": AlertsSourceTypes.NATS,
        "config": deepcopy(DEFAULT_SOURCE_CONFIG),
        "access_type": AlertAccessType.BUILT_IN,
        "is_active": True,
        "is_effective": True,
        "is_delete": False,
        "description": "APM 策略通过 NATS 推送的内置告警源",
    }
    source, created = AlertSource.all_objects.update_or_create(
        source_id=APM_ALERT_SOURCE_ID,
        defaults=defaults,
    )
    return source, created
