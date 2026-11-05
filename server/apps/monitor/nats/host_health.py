"""主机健康快照 NATS handler。未选主机不退化为全量。"""

from __future__ import annotations

import nats_client
from apps.core.logger import nats_logger as logger
from apps.core.logger import safe_exception_info
from apps.monitor.models import MonitorObject
from apps.monitor.services.host_dashboard import (
    HOST_OBJECT_NAME,
    HostHealthSnapshotService,
    empty_host_health_snapshot,
    looks_like_cmdb_instance_locator,
    resolve_instance_storage_ids,
    select_instances_by_ids,
    unresolved_monitor_instance_message,
)
from apps.monitor.utils.dimension import parse_instance_id
from apps.monitor.utils.victoriametrics_api import VictoriaMetricsAPI


def _nm():
    from apps.monitor.nats import monitor as nm

    return nm


def _resolve_selected_host_instances(kwargs, *, empty_data):
    nm = _nm()
    scope = str(kwargs.get("scope") or "").strip().lower()
    user_info = kwargs.get("user_info") or {}
    instance_ids = None
    fleet = getattr(nm, "_HOST_FLEET_SCOPE", "all_authorized")
    if scope != fleet:
        try:
            instance_ids = nm._normalize_filter_values(kwargs.get("instance_ids"), "instance_ids")
        except ValueError as exc:
            return None, None, {"result": False, "data": empty_data, "message": str(exc)}
        if not instance_ids:
            return None, None, {"result": True, "data": empty_data, "message": ""}
    _, _, _, scope_ids, _, error = nm._get_nats_actor_scope(user_info)
    if error:
        return None, None, error
    if scope == fleet:
        host_obj = MonitorObject.objects.filter(name=HOST_OBJECT_NAME).first()
        if host_obj is None:
            return None, None, {"result": True, "data": empty_data, "message": ""}
        authorized_instances, error = nm._get_authorized_monitor_instances(
            user_info,
            scope_ids,
            monitor_obj_id=host_obj.id,
        )
        if error:
            return None, None, error
        instances = list(authorized_instances.values())
        if not instances:
            return None, None, {"result": True, "data": empty_data, "message": ""}
        return instances, scope_ids, None
    authorized_instances, error = nm._get_authorized_monitor_instances(user_info, scope_ids)
    if error:
        return None, None, error
    selected_instances = select_instances_by_ids(authorized_instances, instance_ids)
    if not selected_instances:
        _storage_ids, unresolved = resolve_instance_storage_ids(authorized_instances, instance_ids)
        leftover = unresolved or instance_ids
        if leftover and all(looks_like_cmdb_instance_locator(item) for item in leftover):
            return (
                None,
                None,
                {
                    "result": False,
                    "data": empty_data,
                    "message": unresolved_monitor_instance_message(leftover),
                },
            )
        return None, None, {"result": True, "data": empty_data, "message": ""}
    return selected_instances, scope_ids, None


def _host_alert_query_ids(instances) -> list[str]:
    seen = set()
    query_ids = []
    for instance in instances:
        storage = str(getattr(instance, "id", "") or "")
        parsed = parse_instance_id(storage) if storage else ()
        for token in (storage, str(parsed[0]) if parsed else ""):
            if not token or token in seen:
                continue
            seen.add(token)
            query_ids.append(token)
    return query_ids


def _query_host_health_snapshot(instances, scope_ids, user_info):
    nm = _nm()
    accessible_policy_qs, policy_error = nm._get_nats_accessible_policy_queryset(user_info)
    if policy_error:
        return policy_error
    alerting_map = nm._count_new_monitor_alerts(
        _host_alert_query_ids(instances),
        scope_ids,
        accessible_policy_qs,
    )
    try:
        snapshot = HostHealthSnapshotService(vm_api=VictoriaMetricsAPI()).run(instances, alerting_map.keys())
    except Exception as exc:
        logger.error(
            "event=host_health_snapshot_failed failed_stage=%s error_type=%s",
            "near_realtime_query",
            type(exc).__name__,
            exc_info=safe_exception_info(exc),
        )
        return {"result": False, "data": empty_host_health_snapshot(), "message": "主机健康快照查询失败"}
    return {"result": True, "data": snapshot, "message": ""}


@nats_client.register
def get_host_health_snapshot(*args, **kwargs):
    """按所选主机返回三态健康：正常/异常/无数据。未选主机不退化为全量。"""
    instances, scope_ids, early = _resolve_selected_host_instances(
        kwargs,
        empty_data=empty_host_health_snapshot(),
    )
    if early is not None:
        return early
    return _query_host_health_snapshot(instances, scope_ids, kwargs.get("user_info") or {})
