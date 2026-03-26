from datetime import datetime

import nats_client
from apps.core.utils.time_util import format_time_iso
from apps.core.utils.permission_utils import (
    get_permissions_rules,
    check_instance_permission,
)
from apps.log.constants.permission import PermissionConstants
from apps.log.models.policy import Alert, Policy
from apps.log.utils.query_log import VictoriaMetricsAPI


@nats_client.register
def log_search(query, time_range, limit=10, *args, **kwargs):
    """搜索日志"""
    start_time, end_time = time_range
    start_time = format_time_iso(start_time)
    end_time = format_time_iso(end_time)
    vm_api = VictoriaMetricsAPI()
    data = vm_api.query(query, start_time, end_time, limit)
    return {"result": True, "data": data, "message": ""}


@nats_client.register
def log_hits(query, time_range, field, fields_limit=5, step="5m", *args, **kwargs):
    """搜索日志命中数"""
    start_time, end_time = time_range
    start_time = format_time_iso(start_time)
    end_time = format_time_iso(end_time)
    vm_api = VictoriaMetricsAPI()
    resp = vm_api.hits(query, start_time, end_time, field, fields_limit, step)
    data = []
    for hit_dict in resp["hits"]:
        timestamps = hit_dict.get("timestamps", [])
        values = hit_dict.get("values", [])
        data.extend([{"name": k, "value": v} for k, v in zip(timestamps, values)])

    return {"result": True, "data": data, "message": ""}


def _normalize_positive_int(value, field_name: str, default=None):
    if value in (None, ""):
        return default
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} 必须是整数")
    if normalized < 1:
        raise ValueError(f"{field_name} 必须大于等于 1")
    return normalized


def _normalize_time_value(value, field_name: str):
    if value in (None, ""):
        raise ValueError(f"{field_name} 不能为空")
    if isinstance(value, str):
        value = value.strip()
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    raise ValueError(f"{field_name} 时间格式错误，应为 YYYY-MM-DD HH:MM:SS")


def _normalize_filter_values(value, field_name: str):
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item not in (None, "")]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    raise ValueError(f"{field_name} 必须是字符串或列表")


def _paginate_items(items: list, page, page_size):
    total_count = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    return {
        "count": total_count,
        "page": page,
        "page_size": page_size,
        "items": items[start:end],
    }


def _build_log_alert_segment(alert: Alert) -> dict:
    start_event_time = getattr(alert, "start_event_time", None)
    created_at = getattr(alert, "created_at", None)
    end_event_time = getattr(alert, "end_event_time", None)
    updated_at = getattr(alert, "updated_at", None)

    segment_start = start_event_time or created_at
    segment_end = end_event_time or updated_at or segment_start
    duration_seconds = 0
    if segment_start and segment_end:
        duration_seconds = max(int((segment_end - segment_start).total_seconds()), 0)
    return {
        "id": alert.id,
        "policy_id": getattr(alert, "policy_id", None),
        "collect_type_id": getattr(alert, "collect_type_id", None),
        "source_id": alert.source_id,
        "level": alert.level,
        "value": alert.value,
        "content": alert.content,
        "status": alert.status,
        "start_event_time": segment_start.isoformat() if segment_start else None,
        "end_event_time": segment_end.isoformat() if segment_end else None,
        "duration_seconds": duration_seconds,
        "created_at": created_at.isoformat() if created_at else None,
        "updated_at": updated_at.isoformat() if updated_at else None,
    }


def _get_log_policy_ids(collect_type_id: str, user_info: dict):
    user = user_info.get("user")
    current_team = user_info.get("team")
    include_children = user_info.get("include_children", False)
    if not user or not current_team:
        return [], {"result": False, "data": [], "message": "缺少用户或组织信息"}

    permissions_result = get_permissions_rules(
        user,
        current_team,
        "log",
        PermissionConstants.POLICY_MODULE,
        include_children=include_children,
    )
    if not isinstance(permissions_result, dict):
        permissions_result = {}

    policy_permissions = permissions_result.get("data", {})
    current_teams = permissions_result.get("team", [])
    if not policy_permissions:
        return [], None

    policy_ids = []
    policies = (
        Policy.objects.select_related("collect_type")
        .prefetch_related("policyorganization_set")
        .filter(collect_type_id=collect_type_id)
    )
    for policy_obj in policies:
        teams = {org.organization for org in policy_obj.policyorganization_set.all()}
        if check_instance_permission(
            collect_type_id,
            policy_obj.id,
            teams,
            policy_permissions,
            current_teams,
        ):
            policy_ids.append(policy_obj.id)

    return policy_ids, None


@nats_client.register
def query_log_alert_segments(query_data: dict, *args, **kwargs):
    required_fields = ["collect_type_id", "start", "end"]
    for field in required_fields:
        if field not in query_data:
            return {"result": False, "data": [], "message": f"缺少必要参数: {field}"}

    collect_type_id = str(query_data["collect_type_id"])
    user_info = kwargs.get("user_info", {})

    try:
        start_dt = _normalize_time_value(query_data.get("start"), "start")
        end_dt = _normalize_time_value(query_data.get("end"), "end")
        if start_dt > end_dt:
            raise ValueError("开始时间不能大于结束时间")
        page = _normalize_positive_int(query_data.get("page", 1), "page", default=1)
        page_size = _normalize_positive_int(
            query_data.get("page_size", 100), "page_size", default=100
        )
        if page_size > 500:
            raise ValueError("page_size 不能大于 500")
        source_ids = _normalize_filter_values(query_data.get("source_id"), "source_id")
        status_values = _normalize_filter_values(query_data.get("status"), "status")
        level_values = _normalize_filter_values(query_data.get("level"), "level")
    except ValueError as exc:
        return {"result": False, "data": [], "message": str(exc)}

    policy_ids, error = _get_log_policy_ids(collect_type_id, user_info)
    if error:
        return error

    if not policy_ids:
        return {
            "result": True,
            "data": _paginate_items([], page, page_size),
            "message": "",
        }

    queryset = Alert.objects.filter(
        collect_type_id=collect_type_id, policy_id__in=policy_ids
    )
    queryset = queryset.filter(start_event_time__lte=end_dt, created_at__gte=start_dt)

    if source_ids:
        queryset = queryset.filter(source_id__in=source_ids)

    if status_values:
        queryset = queryset.filter(status__in=status_values)
    if level_values:
        queryset = queryset.filter(level__in=level_values)

    items = [
        _build_log_alert_segment(alert)
        for alert in queryset.order_by("-start_event_time", "-created_at")
    ]
    return {
        "result": True,
        "data": _paginate_items(items, page, page_size),
        "message": "",
    }
