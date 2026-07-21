from datetime import datetime
from types import SimpleNamespace

import nats_client
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.utils.current_team_scope import _normalize_organization_ids
from apps.core.utils.permission_utils import check_instance_permission, get_permission_rules, get_permissions_rules, permission_filter
from apps.core.utils.time_util import format_time_iso
from apps.log.constants.permission import PermissionConstants
from apps.log.constants.victoriametrics import VictoriaLogsConstants
from apps.log.models.log_group import LogGroup
from apps.log.models.policy import Alert, Policy
from apps.log.utils.log_group import LogGroupQueryBuilder
from apps.log.utils.query_log import VictoriaMetricsAPI
from apps.rpc.system_mgmt import SystemMgmt


def _normalize_bounded_int(value, field_name: str, default, max_value: int):
    return VictoriaLogsConstants.normalize_bounded_int(value, field_name, default, max_value)


def _resolve_log_group_scope(user_info):
    """从 user_info 中解析当前用户可访问的日志分组，返回受限 LogGroup 对象列表。

    复用 LogAccessScopeService 的权限模型：
    1. 通过 get_permission_rules 获取用户在 log_group 模块的权限规则
    2. 通过 permission_filter 过滤出可访问的 LogGroup 对象
    """
    if not isinstance(user_info, dict):
        return []

    username = user_info.get("user")
    domain = user_info.get("domain")
    current_team = user_info.get("team")
    include_children = user_info.get("include_children", False)
    is_superuser = user_info.get("is_superuser", False)

    if (
        not isinstance(username, str)
        or not username.strip()
        or not isinstance(domain, str)
        or not domain.strip()
        or type(include_children) is not bool
        or type(is_superuser) is not bool
    ):
        return []

    try:
        current_team = next(iter(_normalize_organization_ids([current_team])))
    except BaseAppException:
        return []

    actor_context = {
        "username": username,
        "domain": domain,
        "current_team": current_team,
        "is_superuser": is_superuser,
    }
    try:
        scope_result = SystemMgmt().get_authorized_groups_scoped(
            actor_context,
            include_children=include_children,
        )
    except Exception:
        return []
    if not isinstance(scope_result, dict) or not scope_result.get("result") or not isinstance(scope_result.get("data"), list):
        return []
    try:
        scope_ids = _normalize_organization_ids(scope_result["data"])
    except BaseAppException:
        return []
    if current_team not in scope_ids:
        return []

    if is_superuser:
        queryset = LogGroup.objects.filter(loggrouporganization__organization__in=list(scope_ids)).distinct()
        return list(queryset.only("id", "name", "rule"))

    # 构造与 get_permission_rules 兼容的 user 对象
    user_obj = SimpleNamespace(username=username, domain=domain)

    permission = get_permission_rules(
        user_obj,
        current_team,
        "log",
        PermissionConstants.LOG_GROUP_MODULE,
        include_children=include_children,
    )
    if not isinstance(permission, dict):
        permission = {}

    queryset = (
        permission_filter(
            LogGroup,
            permission,
            team_key="loggrouporganization__organization__in",
            id_key="id__in",
        )
        .filter(loggrouporganization__organization__in=list(scope_ids))
        .distinct()
    )

    accessible_groups = list(queryset.only("id", "name", "rule"))
    return accessible_groups


def _apply_log_group_scope(query, user_info):
    """对查询语句应用日志分组权限限制，返回改写后的 query。

    如果无法解析权限（缺少 user_info），返回拒绝所有结果的查询。
    超级管理员同样必须使用明确的日志分组范围。
    """
    if not user_info:
        # 未提供身份信息，拒绝所有查询
        return LogGroupQueryBuilder.DENY_ALL_QUERY

    accessible_groups = _resolve_log_group_scope(user_info)

    if not accessible_groups:
        # 无可访问分组，拒绝所有查询
        return LogGroupQueryBuilder.DENY_ALL_QUERY

    log_group_ids = [group.id for group in accessible_groups]
    final_query, _ = LogGroupQueryBuilder.build_query_with_groups(query, log_group_ids, resolved_groups=accessible_groups)
    return final_query


@nats_client.register
def log_search(query, time_range, limit=10, *args, **kwargs):
    """搜索日志"""
    user_info = kwargs.get("user_info")
    query = _apply_log_group_scope(query, user_info)

    start_time, end_time = time_range
    start_time = format_time_iso(start_time)
    end_time = format_time_iso(end_time)
    try:
        limit = VictoriaLogsConstants.normalize_query_limit(limit, default=10)
    except ValueError as exc:
        return {"result": False, "data": [], "message": str(exc)}
    vm_api = VictoriaMetricsAPI()
    data = vm_api.query(query, start_time, end_time, limit)
    return {"result": True, "data": data, "message": ""}


@nats_client.register
def log_hits(query, time_range, field, fields_limit=5, step="5m", *args, **kwargs):
    """搜索日志命中数"""
    user_info = kwargs.get("user_info")
    query = _apply_log_group_scope(query, user_info)

    start_time, end_time = time_range
    start_time = format_time_iso(start_time)
    end_time = format_time_iso(end_time)
    try:
        fields_limit = VictoriaLogsConstants.normalize_hits_fields_limit(fields_limit, default=5)
    except ValueError as exc:
        return {"result": False, "data": [], "message": str(exc)}
    vm_api = VictoriaMetricsAPI()
    resp = vm_api.hits(query, start_time, end_time, field, fields_limit, step)
    data = []
    for hit_dict in resp["hits"]:
        timestamps = hit_dict.get("timestamps", [])
        values = hit_dict.get("values", [])
        data.extend([{"name": k, "value": v} for k, v in zip(timestamps, values)])

    return {"result": True, "data": data, "message": ""}


@nats_client.register
def get_vmlogs_disk_usage(*args, **kwargs):
    """获取 VictoriaLogs 已占用磁盘容量。"""
    vm_api = VictoriaMetricsAPI()
    data = vm_api.get_disk_usage()
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


def _build_paginated_alert_segments(queryset, page, page_size):
    total_count = queryset.count()
    start = (page - 1) * page_size
    end = start + page_size
    paged_alerts = queryset.order_by("-start_event_time", "-created_at")[start:end]
    return {
        "count": total_count,
        "page": page,
        "page_size": page_size,
        "items": [_build_log_alert_segment(alert) for alert in paged_alerts],
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
    policies = Policy.objects.select_related("collect_type").prefetch_related("policyorganization_set").filter(collect_type_id=collect_type_id)
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
        page_size = _normalize_positive_int(query_data.get("page_size", 100), "page_size", default=100)
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

    queryset = Alert.objects.filter(collect_type_id=collect_type_id, policy_id__in=policy_ids)
    queryset = queryset.filter(start_event_time__lte=end_dt, created_at__gte=start_dt)

    if source_ids:
        queryset = queryset.filter(source_id__in=source_ids)

    if status_values:
        queryset = queryset.filter(status__in=status_values)
    if level_values:
        queryset = queryset.filter(level__in=level_values)

    return {
        "result": True,
        "data": _build_paginated_alert_segments(queryset, page, page_size),
        "message": "",
    }
