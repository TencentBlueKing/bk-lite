import hashlib
from collections.abc import Iterable

from apps.alerts.action.engine import ActionEngine


def dispatch_alert_lifecycle(
    alert_ids: Iterable[str], event_name: str, *, auto_assign: bool = False
) -> None:
    """统一分发告警生命周期副作用；调用方负责选择事务提交时机。"""
    unique_ids = list(dict.fromkeys(alert_id for alert_id in alert_ids if alert_id))
    if not unique_ids:
        return

    if auto_assign:
        from apps.alerts.service.outbox import enqueue_outbox

        digest = hashlib.sha256("\0".join(unique_ids).encode("utf-8")).hexdigest()
        enqueue_outbox(
            "auto_assignment",
            {"alert_ids": unique_ids},
            f"auto-assignment:{event_name}:{digest}",
        )

    for alert_id in unique_ids:
        ActionEngine.dispatch_async(alert_id, event_name)
