"""从事件快照归并 Alert 关联的监控对象集合。"""

from collections.abc import Iterable


def _normalize(value):
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def resolve_monitor_objects(events: Iterable) -> list[dict]:
    """按事件首次出现顺序，以显式 monitor_id 去重对象快照。"""
    objects = []
    objects_by_monitor_id = {}
    for event in events:
        monitor_id = _normalize(getattr(event, "monitor_id", None))
        if not monitor_id:
            continue
        snapshot = {
            "monitor_id": monitor_id,
            "cmdb_id": _normalize(getattr(event, "cmdb_id", None)),
            "resource_type": _normalize(getattr(event, "resource_type", None)),
            "resource_name": _normalize(getattr(event, "resource_name", None)),
        }
        existing = objects_by_monitor_id.get(monitor_id)
        if existing is None:
            objects_by_monitor_id[monitor_id] = snapshot
            objects.append(snapshot)
            continue
        for field in ("cmdb_id", "resource_type", "resource_name"):
            if existing[field] is None and snapshot[field] is not None:
                existing[field] = snapshot[field]
    return objects
