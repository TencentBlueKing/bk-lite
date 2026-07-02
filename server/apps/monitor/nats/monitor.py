import time
from datetime import datetime
from types import SimpleNamespace
from typing import Optional

from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import serializers

import nats_client
from apps.core.logger import nats_logger as logger
from apps.core.utils.loader import LanguageLoader
from apps.core.utils.permission_utils import check_instance_permission, get_permission_rules, get_permissions_rules, permission_filter
from apps.core.utils.time_util import format_timestamp
from apps.monitor.constants.language import LanguageConstants
from apps.monitor.constants.permission import PermissionConstants
from apps.monitor.models import (
    CollectConfig,
    Metric,
    MetricGroup,
    MonitorAlert,
    MonitorAlertMetricSnapshot,
    MonitorEvent,
    MonitorInstance,
    MonitorObject,
    MonitorObjectType,
    MonitorPlugin,
    MonitorPolicy,
    PolicyInstanceBaseline,
)
from apps.monitor.serializers.monitor_metrics import MetricGroupSerializer, MetricSerializer
from apps.monitor.serializers.monitor_object import MonitorObjectSerializer, MonitorObjectTypeSerializer
from apps.monitor.serializers.monitor_policy import MonitorPolicySerializer
from apps.monitor.serializers.plugin import MonitorPluginSerializer
from apps.monitor.services.metrics import Metrics
from apps.monitor.utils.dimension import parse_instance_id
from apps.monitor.utils.instance_id_keys import resolve_monitor_object_instance_id_keys
from apps.monitor.utils.victoriametrics_api import VictoriaMetricsAPI


def _normalize_monitor_query_data(query_data: dict) -> dict:
    normalized = dict(query_data or {})
    if "monitor_obj_id" not in normalized and "monitor_object_id" in normalized:
        normalized["monitor_obj_id"] = normalized["monitor_object_id"]
    if "start" not in normalized and "start_time" in normalized:
        normalized["start"] = normalized["start_time"]
    if "end" not in normalized and "end_time" in normalized:
        normalized["end"] = normalized["end_time"]
    return normalized


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


def _normalize_bool(value, field_name: str):
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return False
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no"}:
            return False
    raise ValueError(f"{field_name} 必须是布尔值")


def _normalize_time_value(value, field_name: str):
    if value in (None, ""):
        raise ValueError(f"{field_name} 不能为空")
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value)
    if isinstance(value, str):
        value = value.strip()
        if value.isdigit():
            return datetime.fromtimestamp(int(value))
        try:
            return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        except ValueError as exc:
            raise ValueError(f"{field_name} 时间格式错误，应为 YYYY-MM-DD HH:MM:SS 或时间戳") from exc
    raise ValueError(f"{field_name} 时间格式错误")


def _normalize_filter_values(value, field_name: str):
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item not in (None, "")]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    raise ValueError(f"{field_name} 必须是字符串或列表")


def _build_vm_query_failure_result(resp: dict, default_message: str):
    error_message = resp.get("error") or resp.get("message") or default_message
    error_type = resp.get("errorType")
    if error_type:
        error_message = f"{error_type}: {error_message}"
    return {"result": False, "data": [], "message": error_message}


def _normalize_step(step):
    if step in (None, ""):
        return "5m"
    Metrics.parse_step_to_seconds(step)
    return step


def _normalize_dimensions(metric, dimensions):
    if dimensions in (None, ""):
        return {}
    if not isinstance(dimensions, dict):
        raise ValueError("dimensions 必须是字典")

    allowed_dimensions = set(metric.instance_id_keys or [])
    for item in metric.dimensions or []:
        if isinstance(item, dict):
            name = item.get("name")
            if name:
                allowed_dimensions.add(name)
        elif item:
            allowed_dimensions.add(item)

    invalid_keys = [key for key in dimensions.keys() if key not in allowed_dimensions]
    if invalid_keys:
        raise ValueError(f"dimensions 包含未定义维度: {', '.join(invalid_keys)}")

    return {str(key): str(value) for key, value in dimensions.items() if value is not None}


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


def _normalize_nats_create_payload(data: dict) -> dict:
    if not isinstance(data, dict):
        raise ValueError("data 必须是字典")
    return dict(data)


def _resolve_nats_actor(user_info: Optional[dict]) -> tuple[str, str]:
    if not isinstance(user_info, dict):
        return "api", "domain.com"

    user = _normalize_permission_user(user_info.get("user"))
    operator = getattr(user, "username", None) or "api"
    domain = user_info.get("domain") or getattr(user, "domain", None) or "domain.com"
    return operator, domain


def _ensure_maintainer_fields(data: dict, operator: str = "api", domain: str = "domain.com") -> dict:
    data.setdefault("created_by", operator)
    data.setdefault("updated_by", operator)
    data.setdefault("domain", domain)
    data.setdefault("updated_by_domain", domain)
    return data


def _flatten_error_message(detail, field_name: str = "") -> list[str]:
    if isinstance(detail, dict):
        items = []
        for key, value in detail.items():
            next_field = f"{field_name}.{key}" if field_name else str(key)
            items.extend(_flatten_error_message(value, next_field))
        return items
    if isinstance(detail, list):
        items = []
        for value in detail:
            items.extend(_flatten_error_message(value, field_name))
        return items
    message = str(detail)
    return [f"{field_name}: {message}" if field_name else message]


def _build_validation_message(exc: Exception) -> str:
    detail = getattr(exc, "detail", exc)
    messages = _flatten_error_message(detail)
    return "; ".join(dict.fromkeys(messages)) if messages else str(exc)


def _create_with_serializer(serializer_class, data: dict, operator: str = "api", domain: str = "domain.com"):
    payload = _ensure_maintainer_fields(_normalize_nats_create_payload(data), operator=operator, domain=domain)
    serializer = serializer_class(data=payload)
    serializer.is_valid(raise_exception=True)
    instance = serializer.save()
    return instance, serializer.data


def _create_monitor_object_payload(data: dict, operator: str = "api", domain: str = "domain.com"):
    payload = _ensure_maintainer_fields(_normalize_nats_create_payload(data), operator=operator, domain=domain)
    children = payload.pop("children", [])

    payload["instance_id_keys"] = resolve_monitor_object_instance_id_keys(
        payload.get("instance_id_keys"),
        level=payload.get("level", "base"),
        object_name=payload.get("name", ""),
    )
    if not payload.get("default_metric"):
        payload["default_metric"] = f"any({{instance_type='{payload.get('name', '')}'}}) by (instance_id)"

    serializer = MonitorObjectSerializer(data=payload)
    serializer.is_valid(raise_exception=True)
    parent_obj = serializer.save()

    child_objects = []
    for child in children:
        if child.get("id") and child.get("name"):
            child_objects.append(
                MonitorObject(
                    name=child["id"],
                    display_name=child["name"],
                    icon=payload.get("icon", ""),
                    type_id=payload.get("type"),
                    description="",
                    level="derivative",
                    parent=parent_obj,
                    is_visible=True,
                    instance_id_keys=resolve_monitor_object_instance_id_keys(
                        [],
                        level="derivative",
                        object_name=child["id"],
                    ),
                    default_metric=f"any({{instance_type='{child['id']}'}}) by (instance_id, {child['id']})",
                    created_by=payload["created_by"],
                    updated_by=payload["updated_by"],
                    domain=payload["domain"],
                    updated_by_domain=payload["updated_by_domain"],
                )
            )
    if child_objects:
        MonitorObject.objects.bulk_create(child_objects)

    return parent_obj, serializer.data


def _create_metric_group_payload(data: dict, operator: str = "api", domain: str = "domain.com"):
    payload = _ensure_maintainer_fields(_normalize_nats_create_payload(data), operator=operator, domain=domain)
    payload.setdefault("monitor_plugin", None)
    serializer = MetricGroupSerializer(data=payload)
    serializer.is_valid(raise_exception=True)
    instance = serializer.save()
    return instance, serializer.data


def _create_metric_payload(data: dict, operator: str = "api", domain: str = "domain.com"):
    payload = _ensure_maintainer_fields(_normalize_nats_create_payload(data), operator=operator, domain=domain)
    payload.setdefault("monitor_plugin", None)
    serializer = MetricSerializer(data=payload)
    serializer.is_valid(raise_exception=True)
    instance = serializer.save()
    return instance, serializer.data


def _get_monitor_policy_viewset():
    from apps.monitor.views.monitor_policy import MonitorPolicyViewSet

    return MonitorPolicyViewSet()


def _create_monitor_policy_payload(data: dict, operator: str = "api", domain: str = "domain.com"):
    payload = _ensure_maintainer_fields(_normalize_nats_create_payload(data), operator=operator, domain=domain)
    if not payload.get("schedule"):
        raise ValueError("schedule 不能为空")

    serializer = MonitorPolicySerializer(data=payload)
    serializer.is_valid(raise_exception=True)
    policy = serializer.save()

    view = _get_monitor_policy_viewset()
    view.update_or_create_task(policy.id, payload.get("schedule"))
    view.update_policy_organizations(policy.id, payload.get("organizations", []))
    if view.is_no_data_alert_enabled(policy):
        view.update_policy_baselines(policy.id, policy.enable_alerts)

    return policy, MonitorPolicySerializer(policy).data


def _require_authenticated_actor(user_info: Optional[dict]):
    """写接口身份闸：必须携带可解析的已认证身份才允许写库。

    缺身份时不再回退默认 api/domain.com 账号继续建库——对齐读接口
    _get_monitor_instance_permission 的身份校验（缺用户即拒），消除"写比读松"的鉴权旁路：
    仅凭向 NATS subject 发消息、不带任何身份即可新建监控对象/告警策略的攻击面。
    校验失败时返回与读接口一致的失败结构。
    """
    if not isinstance(user_info, dict) or not _normalize_permission_user(user_info.get("user")):
        return {"result": False, "data": [], "message": "缺少用户或组织信息"}
    return None


def _execute_nats_create(create_func, data: dict, user_info: Optional[dict] = None):
    identity_error = _require_authenticated_actor(user_info)
    if identity_error:
        return identity_error
    try:
        operator, domain = _resolve_nats_actor(user_info)
        _, result_data = create_func(data, operator=operator, domain=domain)
        return {"result": True, "data": result_data, "message": ""}
    except (serializers.ValidationError, ValueError) as exc:
        return {"result": False, "data": [], "message": _build_validation_message(exc)}
    except Exception as exc:
        logger.exception("monitor NATS create failed, error=%s", exc)
        return {"result": False, "data": [], "message": str(exc)}


def _build_monitor_alert_segment(alert: MonitorAlert) -> dict:
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
        "id": getattr(alert, "id", None),
        "policy_id": getattr(alert, "policy_id", None),
        "monitor_instance_id": getattr(alert, "monitor_instance_id", None),
        "monitor_instance_name": getattr(alert, "monitor_instance_name", None),
        "metric_instance_id": getattr(alert, "metric_instance_id", None),
        "dimensions": getattr(alert, "dimensions", {}),
        "alert_type": getattr(alert, "alert_type", None),
        "level": getattr(alert, "level", None),
        "value": getattr(alert, "value", None),
        "content": getattr(alert, "content", None),
        "status": getattr(alert, "status", None),
        "start_event_time": segment_start.isoformat() if segment_start else None,
        "end_event_time": segment_end.isoformat() if segment_end else None,
        "duration_seconds": duration_seconds,
        "created_at": created_at.isoformat() if created_at else None,
        "updated_at": updated_at.isoformat() if updated_at else None,
    }


def _escape_label_value(value) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def _normalize_metric_instance_id_keys(metric=None, monitor_obj=None) -> list[str]:
    raw_keys = (
        getattr(metric, "instance_id_keys", None)
        or getattr(monitor_obj, "instance_id_keys", None)
        or ["instance_id"]
    )
    keys = [str(key).strip() for key in raw_keys if key is not None and str(key).strip()]
    return keys or ["instance_id"]


def _build_instance_label_conditions(instance_ids, instance_id_keys: list[str]) -> list[str]:
    """Map stored tuple instance IDs back to the VM label dimensions."""
    values_by_key = {key: set() for key in instance_id_keys}
    for instance_id in instance_ids:
        instance_id_values = parse_instance_id(instance_id)
        for index, key in enumerate(instance_id_keys):
            if index >= len(instance_id_values):
                continue
            value = instance_id_values[index]
            if value in (None, ""):
                continue
            values_by_key[key].add(str(value))

    return [
        f'{key}=~"{"|".join(_escape_label_value(value) for value in sorted(values))}"'
        for key, values in values_by_key.items()
        if values
    ]


def _build_metric_instance_id_candidates(metric_labels: dict, instance_id_keys: list[str]) -> set[str]:
    """Rebuild DB instance IDs from VM labels for permission checks."""
    values = []
    for key in instance_id_keys:
        value = metric_labels.get(key)
        if value in (None, ""):
            return set()
        values.append(value)

    candidates = {str(tuple(values))}
    if len(instance_id_keys) == 1:
        candidates.add(str(values[0]))
    return candidates


def _build_metric_label_query(metric_query: str, instance_ids=None, dimensions=None, instance_id_keys=None) -> str:
    instance_ids = [str(instance_id) for instance_id in (instance_ids or []) if instance_id]
    dimensions = dimensions or {}
    instance_id_keys = instance_id_keys or ["instance_id"]

    label_conditions = []
    if instance_ids:
        label_conditions.extend(_build_instance_label_conditions(instance_ids, instance_id_keys))

    for key, value in dimensions.items():
        if value is None:
            continue
        label_conditions.append(f'{key}="{_escape_label_value(value)}"')

    if not label_conditions:
        return metric_query

    labels_str = ", ".join(label_conditions)

    if "__$labels__" in metric_query:
        return metric_query.replace("__$labels__", labels_str)

    if "{" in metric_query and "}" in metric_query:
        left, right = metric_query.split("{", 1)
        existing_labels, suffix = right.split("}", 1)
        existing_labels = existing_labels.strip()
        merged_labels = f"{existing_labels}, {labels_str}" if existing_labels else labels_str
        return f"{left}{{{merged_labels}}}{suffix}"

    return f"{metric_query}{{{labels_str}}}"


def _get_monitor_instance_permission(monitor_obj_id: str, user_info: dict):
    user = _normalize_permission_user(user_info.get("user"))
    current_team = user_info.get("team")
    include_children = user_info.get("include_children", False)

    if not user or not current_team:
        return None, {"result": False, "data": [], "message": "缺少用户或组织信息"}

    permission = get_permission_rules(
        user,
        current_team,
        "monitor",
        f"{PermissionConstants.INSTANCE_MODULE}.{monitor_obj_id}",
        include_children=include_children,
    )
    return permission, None


def _normalize_permission_user(user):
    if hasattr(user, "username") and hasattr(user, "domain"):
        return user
    if isinstance(user, str):
        username = user.strip()
        if username:
            return SimpleNamespace(username=username, domain="domain.com")
        return user
    return user


def _get_global_monitor_instance_permissions(user_info: dict):
    user = _normalize_permission_user(user_info.get("user"))
    current_team = user_info.get("team")
    include_children = user_info.get("include_children", False)

    if not user or not current_team:
        return None, None, {"result": False, "data": [], "message": "缺少用户或组织信息"}

    permission_result = get_permissions_rules(
        user,
        current_team,
        "monitor",
        PermissionConstants.INSTANCE_MODULE,
        include_children=include_children,
    )
    if not isinstance(permission_result, dict):
        return {}, [], None
    permission_data = permission_result.get("data", {})
    current_teams = permission_result.get("team", [])
    if not isinstance(permission_data, dict):
        permission_data = {}
    if not isinstance(current_teams, list):
        current_teams = []
    return permission_data, current_teams, None


def _get_authorized_monitor_instances(user_info: dict, monitor_obj_id: Optional[str] = None):
    instance_permissions, cur_team, error = _get_global_monitor_instance_permissions(user_info)
    if error:
        return {}, error

    instance_queryset = (
        MonitorInstance.objects.filter(is_deleted=False, is_active=True)
        .select_related("monitor_object")
        .prefetch_related("monitorinstanceorganization_set")
    )
    if monitor_obj_id:
        instance_queryset = instance_queryset.filter(monitor_object_id=monitor_obj_id)

    authorized_instances = {}
    for instance in instance_queryset:
        teams = {org.organization for org in instance.monitorinstanceorganization_set.all()}
        if check_instance_permission(
            str(instance.monitor_object_id),
            instance.id,
            teams,
            instance_permissions,
            cur_team,
        ):
            authorized_instances[str(instance.id)] = instance

    return authorized_instances, None


def _get_authorized_instance_queryset(permission):
    return permission_filter(
        MonitorInstance,
        permission,
        team_key="monitorinstanceorganization__organization__in",
        id_key="id__in",
    )


def _get_instance_permission_map(permission) -> dict:
    if not isinstance(permission, dict):
        return {}
    instance_items = permission.get("instance", [])
    if not isinstance(instance_items, list):
        return {}
    return {item.get("id"): item.get("permission", []) for item in instance_items if isinstance(item, dict) and item.get("id")}


@nats_client.register
def create_monitor_object_type(data: dict, *args, **kwargs):
    return _execute_nats_create(
        lambda payload, operator="api", domain="domain.com": _create_with_serializer(
            MonitorObjectTypeSerializer,
            payload,
            operator=operator,
            domain=domain,
        ),
        data,
        user_info=kwargs.get("user_info"),
    )


@nats_client.register
def create_monitor_object(data: dict, *args, **kwargs):
    return _execute_nats_create(_create_monitor_object_payload, data, user_info=kwargs.get("user_info"))


@nats_client.register
def create_monitor_plugin(data: dict, *args, **kwargs):
    return _execute_nats_create(
        lambda payload, operator="api", domain="domain.com": _create_with_serializer(
            MonitorPluginSerializer,
            payload,
            operator=operator,
            domain=domain,
        ),
        data,
        user_info=kwargs.get("user_info"),
    )


@nats_client.register
def create_metric_group(data: dict, *args, **kwargs):
    return _execute_nats_create(_create_metric_group_payload, data, user_info=kwargs.get("user_info"))


@nats_client.register
def create_metric(data: dict, *args, **kwargs):
    return _execute_nats_create(_create_metric_payload, data, user_info=kwargs.get("user_info"))


@nats_client.register
def create_monitor_policy(data: dict, *args, **kwargs):
    return _execute_nats_create(_create_monitor_policy_payload, data, user_info=kwargs.get("user_info"))


@nats_client.register
def monitor_objects(*args, **kwargs):
    """查询监控对象列表"""
    logger.info("=== monitor_objects called , args={}, kwargs={}===".format(args, kwargs))
    queryset = MonitorObject.objects.all().order_by("id")
    serializer = MonitorObjectSerializer(queryset, many=True)
    result = {"result": True, "data": serializer.data, "message": ""}
    return result


@nats_client.register
def monitor_object_instance_count(*args, **kwargs):
    """统计全部监控对象实例数量（不过滤权限）"""
    logger.info(
        "=== monitor_object_instance_count called , args=%s, kwargs=%s===",
        args,
        kwargs,
    )
    queryset = MonitorInstance.objects.filter(is_deleted=False).values("monitor_object__name").annotate(instance_count=Count("id"))
    data = {item["monitor_object__name"]: item["instance_count"] for item in queryset}
    return {"result": True, "data": data, "message": ""}


@nats_client.register
def monitor_metrics(monitor_obj_id: str, *args, **kwargs):
    """查询指标信息"""
    logger.info("=== monitor_metrics called , monitor_obj_id={}, args={}, kwargs={}===".format(monitor_obj_id, args, kwargs))
    try:
        monitor_obj = MonitorObject.objects.get(id=monitor_obj_id)
    except MonitorObject.DoesNotExist:
        return {"result": False, "data": [], "message": "监控对象不存在"}

    # 查询监控对象关联的指标
    metrics = Metric.objects.filter(monitor_object=monitor_obj).order_by("metric_group__sort_order", "sort_order")

    serializer = MetricSerializer(metrics, many=True)
    results = serializer.data
    user_info = kwargs.get("user_info", {}) or {}
    locale = user_info.get("locale", "en")
    lan = LanguageLoader(app=LanguageConstants.APP, default_lang=locale)
    for result in results:
        lan_key = f"{LanguageConstants.MONITOR_OBJECT_METRIC}.{monitor_obj.name}.{result['name']}"
        result["display_name"] = lan.get(f"{lan_key}.name") or result.get("display_name") or result["name"]
        result["display_description"] = lan.get(f"{lan_key}.desc") or result.get("description")
    return {"result": True, "data": results, "message": ""}


@nats_client.register
def monitor_object_instances(monitor_obj_id: str, *args, **kwargs):
    """查询监控对象实例列表
    monitor_obj_id: 监控对象ID
    user_info: {
        team: 当前组织ID
        user: 用户对象或用户名
    }
    """
    try:
        monitor_obj = MonitorObject.objects.get(id=monitor_obj_id)
    except MonitorObject.DoesNotExist:
        return {"result": False, "data": [], "message": "监控对象不存在"}

    user_info = kwargs["user_info"]

    permission, error = _get_monitor_instance_permission(monitor_obj_id, user_info)
    if error:
        return error

    # 使用权限过滤器获取有权限的实例
    qs = _get_authorized_instance_queryset(permission)

    # 过滤指定监控对象的活跃实例
    instances = qs.filter(monitor_object=monitor_obj, is_deleted=False, is_active=True).select_related("monitor_object")

    # 获取实例权限映射
    inst_permission_map = _get_instance_permission_map(permission)

    # 构建返回数据
    filtered_instances = []
    for instance in instances:
        instance_data = {
            "id": instance.id,
            "name": instance.name,
            "monitor_object_id": instance.monitor_object.id,
            "monitor_object_name": instance.monitor_object.name,
            "interval": instance.interval,
            "is_active": instance.is_active,
            "created_time": instance.created_time.isoformat() if hasattr(instance, "created_time") and instance.created_time else None,
            "updated_time": instance.updated_time.isoformat() if hasattr(instance, "updated_time") and instance.updated_time else None,
        }

        # 添加权限信息
        if instance.id in inst_permission_map:
            instance_data["permission"] = inst_permission_map[instance.id]

        filtered_instances.append(instance_data)

    return {"result": True, "data": filtered_instances, "message": ""}


@nats_client.register
def query_monitor_data_by_metric(query_data: dict, *args, **kwargs):
    """查询指标数据
    query_data: {
        monitor_obj_id: 监控对象ID
        metric: 指标名称
        start: 开始时间（utc时间戳）
        end: 结束时间（utc时间戳）
        step: 指标采集间隔（eg: 5s）
        instance_ids: [实例ID1, 实例ID2, ...]
    },
    user_info: {
        team: 当前组织ID
        user: 用户对象或用户名
    }
    """
    # 参数验证
    query_data = _normalize_monitor_query_data(query_data)

    required_fields = ["monitor_obj_id", "metric", "start", "end"]
    for field in required_fields:
        if field not in query_data:
            return {"result": False, "data": [], "message": f"缺少必要参数: {field}"}

    monitor_obj_id = query_data["monitor_obj_id"]
    metric_name = query_data["metric"]
    start_time = query_data["start"]
    end_time = query_data["end"]
    step = query_data.get("step", "5m")
    instance_ids = query_data.get("instance_ids", [])
    raw_dimensions = query_data.get("dimensions", {})

    if not isinstance(instance_ids, list):
        return {"result": False, "data": [], "message": "instance_ids 必须是列表"}

    user_info = kwargs.get("user_info", {})

    permission, error = _get_monitor_instance_permission(monitor_obj_id, user_info)
    if error:
        return error

    try:
        monitor_obj = MonitorObject.objects.get(id=monitor_obj_id)
        metric = Metric.objects.get(monitor_object=monitor_obj, name=metric_name)
    except (MonitorObject.DoesNotExist, Metric.DoesNotExist):
        return {"result": False, "data": [], "message": "监控对象或指标不存在"}

    try:
        step = _normalize_step(step)
        dimensions = _normalize_dimensions(metric, raw_dimensions)
    except ValueError as exc:
        return {"result": False, "data": [], "message": str(exc)}

    # 构建查询语句
    query = metric.query
    if not query:
        return {"result": False, "data": [], "message": "指标查询语句为空"}

    authorized_qs = _get_authorized_instance_queryset(permission)

    # 如果指定了实例ID，需要进行权限验证和过滤
    if instance_ids:
        # 获取有权限的实例ID
        authorized_instances = list(
            authorized_qs.filter(id__in=instance_ids, monitor_object=monitor_obj, is_deleted=False).values_list("id", flat=True)
        )

        if not authorized_instances:
            return {"result": False, "data": [], "message": "没有权限访问指定的实例"}
        instance_ids = authorized_instances

    instance_id_keys = _normalize_metric_instance_id_keys(metric, monitor_obj)
    query = _build_metric_label_query(
        query,
        instance_ids=instance_ids,
        dimensions=dimensions,
        instance_id_keys=instance_id_keys,
    )

    try:
        # 执行范围查询
        result = Metrics.get_metrics_range(query, start_time, end_time, step)

        # 数据格式化和权限过滤
        if "data" in result and "result" in result["data"]:
            # 获取所有有权限的实例ID
            authorized_instance_ids = set(authorized_qs.filter(monitor_object=monitor_obj, is_deleted=False).values_list("id", flat=True))

            filtered_result = []
            for metric_data in result["data"]["result"]:
                metric_instance_ids = _build_metric_instance_id_candidates(
                    metric_data.get("metric", {}),
                    instance_id_keys,
                )

                if metric_instance_ids:
                    # 只返回有权限的实例数据
                    if metric_instance_ids & authorized_instance_ids:
                        filtered_result.append(metric_data)
                else:
                    # 没有实例ID的指标数据直接返回
                    filtered_result.append(metric_data)

            result["data"]["result"] = filtered_result

        return {"result": True, "data": result, "message": ""}

    except Exception as e:
        return {"result": False, "data": [], "message": f"查询指标数据失败: {str(e)}"}


@nats_client.register
def monitor_instance_metrics(query_data: dict, *args, **kwargs):
    query_data = _normalize_monitor_query_data(query_data)
    required_fields = ["monitor_obj_id", "instance_id"]
    for field in required_fields:
        if field not in query_data:
            return {"result": False, "data": [], "message": f"缺少必要参数: {field}"}

    monitor_obj_id = query_data["monitor_obj_id"]
    instance_id = str(query_data["instance_id"])
    only_with_data = query_data.get("only_with_data", False)
    lookback = query_data.get("lookback", "1h")
    page = query_data.get("page", 1)
    page_size = query_data.get("page_size", 100)
    user_info = kwargs.get("user_info", {})

    try:
        page = _normalize_positive_int(page, "page", default=1)
        page_size = _normalize_positive_int(page_size, "page_size", default=100)
        if page_size > 500:
            raise ValueError("page_size 不能大于 500")
        lookback = _normalize_step(lookback)
    except ValueError as exc:
        return {"result": False, "data": [], "message": str(exc)}

    permission, error = _get_monitor_instance_permission(monitor_obj_id, user_info)
    if error:
        return error

    try:
        monitor_obj = MonitorObject.objects.get(id=monitor_obj_id)
    except MonitorObject.DoesNotExist:
        return {"result": False, "data": [], "message": "监控对象不存在"}

    authorized_qs = _get_authorized_instance_queryset(permission)
    instance = (
        authorized_qs.filter(
            id=instance_id,
            monitor_object=monitor_obj,
            is_deleted=False,
            is_active=True,
        )
        .select_related("monitor_object")
        .first()
    )
    if not instance:
        return {"result": False, "data": [], "message": "没有权限访问指定的实例"}

    metrics = Metric.objects.filter(monitor_object=monitor_obj).select_related("metric_group").order_by("metric_group__sort_order", "sort_order")

    result_metrics = []
    for metric in metrics:
        metric_info = {
            "metric_group": {
                "id": metric.metric_group_id,
                "name": metric.metric_group.name if metric.metric_group else "",
            },
            "metric": metric.name,
            "display_name": metric.display_name,
            "dimensions": metric.dimensions,
            "instance_id_keys": metric.instance_id_keys,
            "unit": metric.unit,
            "data_type": metric.data_type,
            "description": metric.description,
        }

        if only_with_data:
            if not metric.query:
                continue
            query = _build_metric_label_query(
                metric.query,
                instance_ids=[instance_id],
            )
            try:
                lookback_seconds = Metrics.parse_step_to_seconds(lookback)
                end_seconds = int(time.time())
                start_seconds = end_seconds - lookback_seconds
                step_seconds = max(1, min(max(lookback_seconds // 12, 1), 300))
                resp = VictoriaMetricsAPI().query_range(
                    query,
                    start_seconds,
                    end_seconds,
                    str(step_seconds),
                )
                if not (resp.get("status") == "success" and resp.get("data", {}).get("result")):
                    continue
            except Exception as exc:
                logger.warning(
                    "monitor_instance_metrics query failed, instance_id=%s, metric=%s, error=%s",
                    instance_id,
                    metric.name,
                    exc,
                )
                continue

        result_metrics.append(metric_info)

    return {
        "result": True,
        "data": {
            "monitor_obj_id": str(monitor_obj.id),
            "instance_id": instance_id,
            **_paginate_items(result_metrics, page, page_size),
        },
        "message": "",
    }


@nats_client.register
def query_monitor_alert_segments(query_data: dict, *args, **kwargs):
    query_data = _normalize_monitor_query_data(query_data)
    required_fields = ["monitor_obj_id", "start", "end"]
    for field in required_fields:
        if field not in query_data:
            return {"result": False, "data": [], "message": f"缺少必要参数: {field}"}

    monitor_obj_id = str(query_data["monitor_obj_id"])
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
        instance_ids = query_data.get("instance_ids", [])
        if instance_ids in (None, ""):
            instance_ids = []
        if not isinstance(instance_ids, list):
            raise ValueError("instance_ids 必须是列表")
        instance_ids = [str(instance_id) for instance_id in instance_ids if instance_id]
        instance_id = query_data.get("instance_id")
        if instance_id:
            instance_ids.append(str(instance_id))
        status_values = _normalize_filter_values(query_data.get("status"), "status")
        level_values = _normalize_filter_values(query_data.get("level"), "level")
        alert_type_values = _normalize_filter_values(query_data.get("alert_type"), "alert_type")
    except ValueError as exc:
        return {"result": False, "data": [], "message": str(exc)}

    permission, error = _get_monitor_instance_permission(monitor_obj_id, user_info)
    if error:
        return error

    authorized_qs = _get_authorized_instance_queryset(permission).filter(
        monitor_object_id=monitor_obj_id,
        is_deleted=False,
        is_active=True,
    )
    authorized_instance_ids = set(authorized_qs.values_list("id", flat=True))
    if not authorized_instance_ids:
        return {
            "result": True,
            "data": _paginate_items([], page, page_size),
            "message": "",
        }

    if instance_ids:
        filtered_instance_ids = [instance for instance in instance_ids if instance in authorized_instance_ids]
        if not filtered_instance_ids:
            return {"result": False, "data": [], "message": "没有权限访问指定的实例"}
        authorized_instance_ids = set(filtered_instance_ids)

    queryset = MonitorAlert.objects.filter(monitor_instance_id__in=authorized_instance_ids)
    queryset = queryset.filter(Q(start_event_time__lte=end_dt) | Q(start_event_time__isnull=True, created_at__lte=end_dt))
    queryset = queryset.filter(Q(end_event_time__gte=start_dt) | Q(end_event_time__isnull=True, updated_at__gte=start_dt))

    if status_values:
        queryset = queryset.filter(status__in=status_values)
    if level_values:
        queryset = queryset.filter(level__in=level_values)
    if alert_type_values:
        queryset = queryset.filter(alert_type__in=alert_type_values)

    ordered_queryset = queryset.order_by("-start_event_time", "-created_at")
    total_count = ordered_queryset.count()
    start = (page - 1) * page_size
    end = start + page_size
    items = [_build_monitor_alert_segment(alert) for alert in ordered_queryset[start:end]]
    return {
        "result": True,
        "data": {
            "count": total_count,
            "page": page,
            "page_size": page_size,
            "items": items,
        },
        "message": "",
    }


@nats_client.register
def query_latest_active_alerts(query_data: Optional[dict] = None, *args, **kwargs):
    if query_data is None:
        query_data = {key: value for key, value in kwargs.items() if key not in {"user_info", "_timeout"}}
    query_data = _normalize_monitor_query_data(query_data)
    monitor_obj_id = query_data.get("monitor_obj_id")
    if monitor_obj_id not in (None, ""):
        monitor_obj_id = str(monitor_obj_id)
    else:
        monitor_obj_id = None
    user_info = kwargs.get("user_info", {})

    try:
        limit = _normalize_positive_int(query_data.get("limit", 10), "limit", default=10)
        if limit > 100:
            raise ValueError("limit 不能大于 100")
        instance_ids = query_data.get("instance_ids", [])
        if instance_ids in (None, ""):
            instance_ids = []
        if not isinstance(instance_ids, list):
            raise ValueError("instance_ids 必须是列表")
        instance_ids = [str(instance_id) for instance_id in instance_ids if instance_id]
        instance_id = query_data.get("instance_id")
        if instance_id:
            instance_ids.append(str(instance_id))
        level_values = _normalize_filter_values(query_data.get("level"), "level")
        alert_type_values = _normalize_filter_values(query_data.get("alert_type"), "alert_type")
    except ValueError as exc:
        return {"result": False, "data": [], "message": str(exc)}

    if monitor_obj_id:
        try:
            MonitorObject.objects.get(id=monitor_obj_id)
        except MonitorObject.DoesNotExist:
            return {"result": False, "data": [], "message": "监控对象不存在"}

    if monitor_obj_id:
        permission, error = _get_monitor_instance_permission(monitor_obj_id, user_info)
        if error:
            return error
        authorized_qs = (
            _get_authorized_instance_queryset(permission)
            .filter(
                monitor_object_id=monitor_obj_id,
                is_deleted=False,
                is_active=True,
            )
            .select_related("monitor_object")
        )
        authorized_instances = {str(instance.id): instance for instance in authorized_qs}
    else:
        authorized_instances, error = _get_authorized_monitor_instances(user_info)
        if error:
            return error

    if not authorized_instances:
        return {
            "result": True,
            "data": {"count": 0, "items": []},
            "message": "",
        }

    authorized_instance_ids = set(authorized_instances.keys())
    if instance_ids:
        filtered_instance_ids = [instance for instance in instance_ids if instance in authorized_instance_ids]
        if not filtered_instance_ids:
            return {"result": False, "data": [], "message": "没有权限访问指定的实例"}
        authorized_instance_ids = set(filtered_instance_ids)

    queryset = MonitorAlert.objects.filter(
        monitor_instance_id__in=authorized_instance_ids,
        status="new",
    )

    if level_values:
        queryset = queryset.filter(level__in=level_values)
    if alert_type_values:
        queryset = queryset.filter(alert_type__in=alert_type_values)

    items = []
    for alert in queryset.order_by("-start_event_time", "-created_at")[:limit]:
        item = _build_monitor_alert_segment(alert)
        instance = authorized_instances.get(str(alert.monitor_instance_id))
        item["monitor_obj_id"] = str(instance.monitor_object_id) if instance else None
        item["monitor_object_name"] = (
            (instance.monitor_object.display_name or instance.monitor_object.name) if instance and instance.monitor_object else None
        )
        item["end_event_time"] = None
        items.append(item)
    return {
        "result": True,
        "data": {
            "count": len(items),
            "items": items,
        },
        "message": "",
    }


@nats_client.register
def mm_query_range(query: str, time_range: list, step="5m", *args, **kwargs):
    start_time, end_time = time_range
    start_time = format_timestamp(start_time)
    end_time = format_timestamp(end_time)
    resp = VictoriaMetricsAPI().query_range(query, start_time, end_time, step)
    if resp.get("status") == "success":
        _result = resp["data"]["result"]
        if _result:
            values = _result[0].get("values", [])
        else:
            values = []
        # 格式转换给单值
        data = []
        for _value in values:
            data.append({"name": _value[0], "value": _value[1]})
        return {"result": True, "data": data, "message": ""}
    return _build_vm_query_failure_result(resp, "查询时间范围指标数据失败")


@nats_client.register
def mm_query(query: str, step="5m", *args, **kwargs):
    resp = VictoriaMetricsAPI().query(query, step)
    if resp.get("status") == "success":
        _result = resp["data"]["result"]
        if _result:
            values = _result[0].get("value", [])
        else:
            values = []
            # 格式转换给单值
        data = []
        if values:
            data.append({"name": values[0], "value": values[-1]})
        return {"result": True, "data": data, "message": ""}
    return _build_vm_query_failure_result(resp, "查询单个指标数据失败")


def _scope_count_queryset(qs, *, is_superuser: bool, team, org_field: str):
    """总览计数的统一 scope 口径：超管→全量；非超管→必须按 team 收窄。

    非超管且无 team 视为**零授权**，返回空集（qs.none()）而非全量——
    否则会把全平台跨组织计数泄露给一个没有任何组织归属的普通用户。
    """
    if is_superuser:
        return qs
    if not team:
        return qs.none()
    return qs.filter(**{org_field: team}).distinct()


@nats_client.register
def get_monitor_statistics(user_info=None, **kwargs):
    """监控中心总览统计

    返回资源/能力/告警三大维度全部计数指标，供 operation_analysis
    内置仪表盘以 single 值卡片渲染（按 selectedFields 取字段）。

    Args:
        user_info: { team: int, is_superuser: bool, ... } 由 operation_analysis 注入

    Returns:
        { "result": True, "data": { 各项计数 ... }, "message": "" }
    """
    user_info = user_info or {}
    team = user_info.get("team")
    is_superuser = bool(user_info.get("is_superuser"))

    # ============ 资源概览 ============
    # 监控对象/对象类型属平台级目录（各组织一致），非租户数据，不做组织收窄
    monitor_object_total = MonitorObject.objects.count()
    monitor_object_visible = MonitorObject.objects.filter(is_visible=True).count()
    monitor_object_category = MonitorObjectType.objects.count()

    instance_qs = _scope_count_queryset(
        MonitorInstance.objects.filter(is_deleted=False),
        is_superuser=is_superuser,
        team=team,
        org_field="monitorinstanceorganization__organization",
    )
    monitor_instance_total = instance_qs.count()
    monitor_instance_active = instance_qs.filter(is_active=True).count()
    monitor_instance_inactive = instance_qs.filter(is_active=False).count()

    # ============ 能力概览 ============
    # 插件/指标/指标分组同属平台级目录，不做组织收窄
    plugin_total = MonitorPlugin.objects.count()
    plugin_builtin = MonitorPlugin.objects.filter(is_pre=True).count()
    plugin_custom = MonitorPlugin.objects.filter(is_pre=False).count()
    metric_total = Metric.objects.count()
    metric_group_total = MetricGroup.objects.count()
    # 采集配置按实例归属收窄：超管→全量；非超管→跟随 instance_qs（无 team 时为空集→0）
    collect_config_total = (
        CollectConfig.objects.count()
        if is_superuser
        else CollectConfig.objects.filter(monitor_instance_id__in=instance_qs.values_list("id", flat=True)).count()
    )

    # ============ 告警概览 ============
    # 策略按组织收窄；下游 alert/event/snapshot/baseline 均以 policy_qs 的 id 集合间接收窄，
    # 故非超管且无 team 时 policy_qs 为空集，所有告警类计数随之归零
    policy_qs = _scope_count_queryset(
        MonitorPolicy.objects.all(),
        is_superuser=is_superuser,
        team=team,
        org_field="policyorganization__organization",
    )
    policy_total = policy_qs.count()
    policy_enabled = policy_qs.filter(enable=True).count()
    policy_disabled = policy_qs.filter(enable=False).count()
    # 阈值策略：有 threshold 配置 / 无数据策略：no_data_level 非空
    policy_threshold = policy_qs.exclude(threshold=[]).count()
    policy_no_data = policy_qs.exclude(no_data_level="").count()

    alert_qs = MonitorAlert.objects.filter(policy_id__in=policy_qs.values_list("id", flat=True)) if not is_superuser else MonitorAlert.objects.all()
    alert_history = alert_qs.count()
    alert_current = alert_qs.filter(status="new").count()
    alert_recovered = alert_qs.filter(status="recovered").count()
    alert_closed = alert_qs.filter(status="closed").count()

    today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    alert_today = alert_qs.filter(created_at__gte=today_start).count()

    event_qs = MonitorEvent.objects.filter(policy_id__in=policy_qs.values_list("id", flat=True)) if not is_superuser else MonitorEvent.objects.all()
    event_total = event_qs.count()
    event_today = event_qs.filter(created_at__gte=today_start).count()

    alert_snapshot_total = (
        MonitorAlertMetricSnapshot.objects.filter(policy_id__in=policy_qs.values_list("id", flat=True)).count()
        if not is_superuser
        else MonitorAlertMetricSnapshot.objects.count()
    )

    no_data_baseline_total = (
        PolicyInstanceBaseline.objects.filter(policy_id__in=policy_qs.values_list("id", flat=True)).count()
        if not is_superuser
        else PolicyInstanceBaseline.objects.count()
    )

    return {
        "result": True,
        "data": {
            # 资源
            "monitor_object_total": monitor_object_total,
            "monitor_object_visible": monitor_object_visible,
            "monitor_object_category": monitor_object_category,
            "monitor_instance_total": monitor_instance_total,
            "monitor_instance_active": monitor_instance_active,
            "monitor_instance_inactive": monitor_instance_inactive,
            # 能力
            "plugin_total": plugin_total,
            "plugin_builtin": plugin_builtin,
            "plugin_custom": plugin_custom,
            "metric_total": metric_total,
            "metric_group_total": metric_group_total,
            "collect_config_total": collect_config_total,
            # 告警
            "policy_total": policy_total,
            "policy_enabled": policy_enabled,
            "policy_disabled": policy_disabled,
            "alert_current": alert_current,
            "alert_history": alert_history,
            "alert_today": alert_today,
            "alert_recovered": alert_recovered,
            "alert_closed": alert_closed,
            "policy_threshold": policy_threshold,
            "policy_no_data": policy_no_data,
            "event_total": event_total,
            "event_today": event_today,
            "alert_snapshot_total": alert_snapshot_total,
            "no_data_baseline_total": no_data_baseline_total,
        },
        "message": "",
    }
