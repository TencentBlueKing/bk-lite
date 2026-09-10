# -*- coding: utf-8 -*-
"""Attach Monitor active-alert summaries onto room3D device payloads."""

from __future__ import annotations

from typing import Any, Callable

from apps.core.logger import cmdb_logger as logger

MonitorClientFactory = Callable[[], Any]

_ENRICH_RPC_FAIL_TEMPLATE = "room3d device alarm enrich failed monitor_id_count=%s " "failed_stage=monitor_rpc error_type=%s"
_ENRICH_RESULT_SOFT_FAIL_TEMPLATE = "room3d device alarm enrich soft-failed monitor_id_count=%s " "failed_stage=monitor_result error_type=%s"


def _unbound_alarm_fields() -> dict[str, Any]:
    return {
        "monitor_bound": False,
        "alarm_unavailable": False,
        "active_alarm_count": None,
        "highest_severity": None,
    }


def _unavailable_alarm_fields(*, monitor_bound: bool) -> dict[str, Any]:
    return {
        "monitor_bound": monitor_bound,
        "alarm_unavailable": True,
        "active_alarm_count": None,
        "highest_severity": None,
    }


def _bound_alarm_fields(active_alarm_count: int, highest_severity: str | None) -> dict[str, Any]:
    return {
        "monitor_bound": True,
        "alarm_unavailable": False,
        "active_alarm_count": int(active_alarm_count),
        "highest_severity": highest_severity,
    }


def _default_monitor_client():
    from apps.rpc.monitor import Monitor

    # get_room3d_layout is served by nats_listener. Calling Monitor via NATS from
    # inside that handler is a nested request and commonly hits the full RPC
    # timeout (~60s), which then times out the outer get_source_data as well.
    # AppClient still goes through the Monitor NATS handler function as the seam.
    return Monitor(is_local_client=True)


def soft_fail_device_alarm_fields(device: dict[str, Any]) -> None:
    """Strip monitor_id and mark alarm fields for soft-fail / unbound."""
    monitor_id = device.pop("monitor_id", None)
    if monitor_id in (None, ""):
        device.update(_unbound_alarm_fields())
    else:
        device.update(_unavailable_alarm_fields(monitor_bound=True))


def _apply_soft_fail_fields(devices: list[dict[str, Any]], device_monitor_ids: list[str]) -> None:
    for device, monitor_id in zip(devices, device_monitor_ids):
        device.pop("monitor_id", None)
        if not monitor_id:
            device.update(_unbound_alarm_fields())
        else:
            device.update(_unavailable_alarm_fields(monitor_bound=True))


def enrich_room3d_devices_with_alarms(
    racks: list[dict[str, Any]],
    *,
    user_info: dict | None,
    monitor_client_factory: MonitorClientFactory | None = None,
) -> None:
    """Mutate rack devices: strip monitor_id, attach alarm summary fields.

    Soft-fails when Monitor seam errors: bound devices become alarm_unavailable.
    """
    devices: list[dict[str, Any]] = []
    for rack in racks or []:
        for device in rack.get("devices") or []:
            if isinstance(device, dict):
                devices.append(device)

    if not devices:
        return

    monitor_ids: list[str] = []
    seen: set[str] = set()
    device_monitor_ids: list[str] = []
    for device in devices:
        raw = device.get("monitor_id")
        monitor_id = "" if raw in (None, "") else str(raw).strip()
        device_monitor_ids.append(monitor_id)
        if monitor_id and monitor_id not in seen:
            seen.add(monitor_id)
            monitor_ids.append(monitor_id)

    if not monitor_ids:
        for device in devices:
            device.pop("monitor_id", None)
            device.update(_unbound_alarm_fields())
        return

    monitor_id_count = len(monitor_ids)
    factory = monitor_client_factory or _default_monitor_client
    try:
        client = factory()
        response = client.query_active_alert_summaries_by_monitor_ids(
            monitor_ids,
            user_info=user_info or {},
        )
    except Exception as exc:
        logger.exception(
            _ENRICH_RPC_FAIL_TEMPLATE,
            monitor_id_count,
            type(exc).__name__,
        )
        _apply_soft_fail_fields(devices, device_monitor_ids)
        return

    if not isinstance(response, dict) or response.get("result") is not True:
        error_type = "invalid_response" if not isinstance(response, dict) else "result_false"
        logger.warning(
            _ENRICH_RESULT_SOFT_FAIL_TEMPLATE,
            monitor_id_count,
            error_type,
        )
        _apply_soft_fail_fields(devices, device_monitor_ids)
        return

    data = response.get("data")
    items = (data.get("items") if isinstance(data, dict) else None) or []
    by_id: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        monitor_id = str(item.get("monitor_id") or "").strip()
        if not monitor_id:
            continue
        by_id[monitor_id] = item

    for device, monitor_id in zip(devices, device_monitor_ids):
        device.pop("monitor_id", None)
        if not monitor_id:
            device.update(_unbound_alarm_fields())
            continue
        summary = by_id.get(monitor_id)
        if summary is None:
            device.update(_unavailable_alarm_fields(monitor_bound=True))
            continue
        count = summary.get("active_alarm_count")
        severity = summary.get("highest_severity")
        try:
            count_int = int(count)
        except (TypeError, ValueError):
            device.update(_unavailable_alarm_fields(monitor_bound=True))
            continue
        if count_int < 0:
            device.update(_unavailable_alarm_fields(monitor_bound=True))
            continue
        if severity not in (None, "critical", "error", "warning"):
            severity = None
        if count_int <= 0:
            severity = None
        device.update(_bound_alarm_fields(count_int, severity))
