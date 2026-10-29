from __future__ import annotations

from typing import Any, Awaitable, Callable, Mapping

PublishFn = Callable[[dict[str, Any]], Awaitable[None] | None]


class MemoryScanPublisher:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def publish(self, event: Mapping[str, Any]) -> None:
        self.events.append(dict(event))


class NatsScanPublisher:
    """把扫描阶段事件发到已登记的 control 回调，不走 metrics 流。"""

    def __init__(self, subject: str = "receive_scan_credential_result") -> None:
        self._subject = str(subject or "receive_scan_credential_result").strip() or "receive_scan_credential_result"

    async def publish(self, event: Mapping[str, Any]) -> None:
        from core.infra.control_transport import get_control_transport

        await get_control_transport().publish_collection_callback(self._subject, dict(event))


def scan_done_event(*, execution_id, status: str = "success", error_code: str = "") -> dict[str, Any]:
    payload = {
        "collect_task_id": execution_id,
        "stage": "done",
        "status": status,
    }
    if error_code:
        payload["error_code"] = error_code
    return payload


def scan_event(
    *,
    execution_id,
    host: str,
    port: int,
    target_type: str,
    stage: str,
    status: str = "success",
    credential_id: str = "",
    error_code: str = "",
    snapshot: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "collect_task_id": execution_id,
        "host": host,
        "port": int(port or 0),
        "target_type": target_type,
        "stage": stage,
        "status": status,
        "credential_id": credential_id,
        "snapshot": dict(snapshot or {"host": host, "port": int(port or 0)}),
    }
    if error_code:
        payload["error_code"] = error_code
    return payload
