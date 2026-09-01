import time
from types import SimpleNamespace
from typing import Optional

from django.db import transaction
from django.db.models import Count, F, Q
from django.utils import timezone
from rest_framework import serializers

import nats_client
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.logger import nats_logger as logger
from apps.core.utils.current_team_scope import _normalize_organization_ids
from apps.core.utils.loader import LanguageLoader
from apps.core.utils.permission_utils import (
    check_instance_permission,
    get_instance_permissions,
    get_permission_rules,
    get_permissions_rules,
    permission_filter,
)
from apps.core.utils.time_util import parse_rfc3339_range_utc, rfc3339_to_timestamp
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
    PolicyOrganization,
)
from apps.monitor.serializers.monitor_metrics import MetricGroupSerializer, MetricSerializer
from apps.monitor.serializers.monitor_object import MonitorObjectSerializer, MonitorObjectTypeSerializer
from apps.monitor.serializers.monitor_policy import MonitorPolicySerializer
from apps.monitor.serializers.plugin import MonitorPluginSerializer
from apps.monitor.services.authorized_metric_query import AuthorizedMetricQueryError, AuthorizedMetricQueryService
from apps.monitor.services.host_dashboard import (
    HOST_OBJECT_NAME,
    HostMetricRangeService,
    HostResourceSnapshotService,
    build_host_instance_rows,
    empty_host_snapshot,
    validate_range_metric_type,
)
from apps.monitor.services.host_resource_top import HostResourceTopService, validate_metric_type
from apps.monitor.services.interface_metrics_query import InterfaceMetricsQueryError, normalize_instance_ids, query_interface_metric_items
from apps.monitor.services.metrics import Metrics, MetricsQueryBudgetExceeded
from apps.monitor.services.nats_query_contract import build_vm_query_failure_result as _build_vm_query_failure_result
from apps.monitor.services.nats_query_contract import normalize_bool
from apps.monitor.services.nats_query_contract import normalize_dimensions as _normalize_dimensions
from apps.monitor.services.nats_query_contract import normalize_filter_values as _normalize_filter_values
from apps.monitor.services.nats_query_contract import normalize_monitor_query_data as _normalize_monitor_query_data
from apps.monitor.services.nats_query_contract import normalize_positive_int as _normalize_positive_int
from apps.monitor.services.nats_query_contract import normalize_step as _normalize_step
from apps.monitor.services.nats_query_contract import normalize_time_value as _normalize_time_value
from apps.monitor.services.nats_query_contract import paginate_items as _paginate_items
from apps.monitor.services.network_device_resource_top import NetworkDeviceResourceTopService
from apps.monitor.services.network_device_resource_top import validate_metric_type as validate_network_metric_type
from apps.monitor.utils.dimension import parse_instance_id
from apps.monitor.utils.instance_id_keys import resolve_monitor_object_instance_id_keys
from apps.monitor.utils.metric_enum_locale import localize_metric_enum_unit
from apps.monitor.utils.victoriametrics_api import VictoriaMetricsAPI
from apps.monitor.utils.vm_query_batch import run_unique_vm_queries
from apps.rpc.system_mgmt import SystemMgmt

_normalize_bool = normalize_bool


def _build_query_budget_failure(exc: MetricsQueryBudgetExceeded) -> dict:
    return {
        "result": False,
        "data": [],
        "message": exc.message,
        "code": exc.data["code"],
        "budget": exc.data,
    }


def _serialize_metric_plugin(metric: Metric) -> Optional[dict]:
    plugin = metric.monitor_plugin
    if plugin is None:
        return None
    return {
        "id": plugin.id,
        "name": plugin.name,
        "display_name": plugin.display_name,
        "template_id": plugin.template_id,
        "template_type": plugin.template_type,
        "collector": plugin.collector,
        "collect_type": plugin.collect_type,
    }


def _normalize_nats_create_payload(data: dict) -> dict:
    if not isinstance(data, dict):
        raise ValueError("data 必须是字典")
    return dict(data)


def _resolve_nats_actor(user_info: Optional[dict]) -> tuple[str, str]:
    if not isinstance(user_info, dict):
        return "api", "domain.com"

    user = _normalize_permission_user(
        user_info.get("user"),
        domain=user_info.get("domain"),
    )
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


def _nats_caller_org_ids(user_info: Optional[dict]):
    if not isinstance(user_info, dict):
        return frozenset()
    raw = user_info.get("allowed_org_ids") or user_info.get("organization_ids")
    if not raw:
        team = user_info.get("team")
        raw = [team] if team not in (None, "") else []
    try:
        return _normalize_organization_ids(raw)
    except Exception:
        return frozenset()


def _policy_visible_in_orgs(policy: MonitorPolicy, org_ids) -> bool:
    if not org_ids:
        return False
    if PolicyOrganization.objects.filter(policy_id=policy.id, organization__in=list(org_ids)).exists():
        return True
    return bool(set(policy.organizations or []) & set(org_ids))


def _delete_monitor_policy_record(policy: MonitorPolicy, operator: str):
    from django_celery_beat.models import PeriodicTask

    from apps.monitor.services.alert_lifecycle_notify import NOTIFY_SCOPE_ALL_CONFIGURED, AlertLifecycleNotifier
    from apps.monitor.services.policy_baseline import PolicyBaselineService

    policy_id = policy.id
    view = _get_monitor_policy_viewset()
    PolicyBaselineService(policy).clear()
    alerts_to_close = list(MonitorAlert.objects.filter(policy_id=policy_id, status="new"))
    view._close_alerts_in_tx(policy, alerts_to_close, operator, "policy_deleted")
    if alerts_to_close:
        notifier = AlertLifecycleNotifier(policy)
        notifier.enqueue_alert_center_deliveries(
            alerts_to_close,
            "closed",
            operator=operator,
            reason="policy_deleted",
        )
        transaction.on_commit(
            lambda alerts=tuple(alerts_to_close): notifier.notify_alerts(
                alerts,
                action="closed",
                operator=operator,
                reason="policy_deleted",
                notify_scope=NOTIFY_SCOPE_ALL_CONFIGURED,
            )
        )
    PeriodicTask.objects.filter(name=f"scan_policy_task_{policy_id}").delete()
    PolicyOrganization.objects.filter(policy_id=policy_id).delete()
    policy.delete()
    return policy_id


def _require_authenticated_actor(user_info: Optional[dict]):
    """写接口身份闸：必须携带可解析的已认证身份才允许写库。

    缺身份时不再回退默认 api/domain.com 账号继续建库——对齐读接口
    _get_monitor_instance_permission 的身份校验（缺用户即拒），消除"写比读松"的鉴权旁路：
    仅凭向 NATS subject 发消息、不带任何身份即可新建监控对象/告警策略的攻击面。
    校验失败时返回与读接口一致的失败结构。
    """
    if not isinstance(user_info, dict) or not _normalize_permission_user(
        user_info.get("user"),
        domain=user_info.get("domain"),
    ):
        return {"result": False, "data": [], "message": "缺少用户或组织信息"}
    return None


def _execute_nats_create(create_func, data: dict, user_info: Optional[dict] = None):
    identity_error = _require_authenticated_actor(user_info)
    if identity_error:
        return identity_error
    try:
        operator, domain = _resolve_nats_actor(user_info)
        with transaction.atomic():
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
    raw_keys = getattr(metric, "instance_id_keys", None) or getattr(monitor_obj, "instance_id_keys", None) or ["instance_id"]
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

    return [f'{key}=~"{"|".join(_escape_label_value(value) for value in sorted(values))}"' for key, values in values_by_key.items() if values]


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
    user = _normalize_permission_user(
        user_info.get("user"),
        domain=user_info.get("domain"),
    )
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


def _normalize_permission_user(user, domain=None):
    if hasattr(user, "username") and hasattr(user, "domain"):
        return user
    if isinstance(user, str):
        username = user.strip()
        if username:
            return SimpleNamespace(
                username=username,
                domain=domain or "domain.com",
            )
        return user
    return user


def _get_global_monitor_instance_permissions(user_info: dict, scope_ids):
    user = _normalize_permission_user(
        user_info.get("user"),
        domain=user_info.get("domain"),
    )
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
        return {}, list(scope_ids), None
    permission_data = permission_result.get("data", {})
    if not isinstance(permission_data, dict):
        permission_data = {}
    return permission_data, list(scope_ids), None


def _get_authorized_monitor_instances(
    user_info: dict,
    scope_ids,
    monitor_obj_id: Optional[str] = None,
):
    instance_permissions, cur_team, error = _get_global_monitor_instance_permissions(
        user_info,
        scope_ids,
    )
    if error:
        return {}, error

    instance_queryset = (
        MonitorInstance.objects.filter(
            is_deleted=False,
            is_active=True,
            monitorinstanceorganization__organization__in=list(scope_ids),
        )
        .select_related("monitor_object")
        .prefetch_related("monitorinstanceorganization_set")
        .distinct()
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


def _get_authorized_instance_queryset(permission, scope_ids=None):
    queryset = permission_filter(
        MonitorInstance,
        permission,
        team_key="monitorinstanceorganization__organization__in",
        id_key="id__in",
    )
    if scope_ids is not None:
        queryset = queryset.filter(monitorinstanceorganization__organization__in=list(scope_ids)).distinct()
    return queryset


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
def search_monitor_policies(*args, **kwargs):
    """按名称查询调用方组织范围内的告警策略。

    策略 name 允许重名：可能返回多条（上限 200）。调用方不得假定唯一；
    删除/更新等写操作必须使用返回结果中的 policy id（见 delete_monitor_policy）。
    """
    user_info = kwargs.get("user_info")
    identity_error = _require_authenticated_actor(user_info)
    if identity_error:
        return identity_error
    name = str(kwargs.get("name") or (args[0] if args else "") or "").strip()
    if not name:
        return {"result": False, "data": [], "message": "name 不能为空", "count": 0}
    org_ids = _nats_caller_org_ids(user_info)
    if not org_ids:
        return {"result": False, "data": [], "message": "缺少用户或组织信息", "count": 0}
    queryset = MonitorPolicy.objects.filter(name=name, policyorganization__organization__in=list(org_ids)).distinct().order_by("id")[:200]
    serializer = MonitorPolicySerializer(queryset, many=True)
    data = serializer.data
    count = len(data)
    message_parts = []
    if count > 1:
        message_parts.append(f"同名策略共 {count} 条，请使用 policy_id 操作，勿假定唯一")
    if count >= 200:
        message_parts.append("结果已截断至上限 200 条，请缩小范围或改用 policy_id")
    return {"result": True, "data": data, "message": "；".join(message_parts), "count": count}


@nats_client.register
def delete_monitor_policy(*args, **kwargs):
    """删除调用方组织范围内的一条告警策略及其扫描任务。"""
    user_info = kwargs.get("user_info")
    identity_error = _require_authenticated_actor(user_info)
    if identity_error:
        return identity_error
    raw_policy_id = kwargs.get("policy_id") if "policy_id" in kwargs else (args[0] if args else None)
    try:
        policy_id = int(raw_policy_id)
    except (TypeError, ValueError):
        return {"result": False, "data": [], "message": "policy_id 必须是整数"}
    if policy_id < 1:
        return {"result": False, "data": [], "message": "policy_id 必须大于等于 1"}
    org_ids = _nats_caller_org_ids(user_info)
    if not org_ids:
        return {"result": False, "data": [], "message": "缺少用户或组织信息"}
    try:
        policy = MonitorPolicy.objects.get(id=policy_id)
    except MonitorPolicy.DoesNotExist:
        return {"result": False, "data": [], "message": "策略不存在"}
    if not _policy_visible_in_orgs(policy, org_ids):
        return {"result": False, "data": [], "message": "策略不存在"}
    try:
        operator, _domain = _resolve_nats_actor(user_info)
        with transaction.atomic():
            deleted_id = _delete_monitor_policy_record(policy, operator)
        return {"result": True, "data": {"id": deleted_id}, "message": ""}
    except Exception as exc:
        logger.exception("monitor NATS delete policy failed, error=%s", exc)
        return {"result": False, "data": [], "message": str(exc)}


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
    metrics = Metric.objects.filter(monitor_object=monitor_obj).select_related("monitor_plugin").order_by("metric_group__sort_order", "sort_order")

    serializer = MetricSerializer(metrics, many=True)
    results = serializer.data
    user_info = kwargs.get("user_info", {}) or {}
    locale = user_info.get("locale", "en")
    lan = LanguageLoader(app=LanguageConstants.APP, default_lang=locale)
    for result in results:
        lan_key = f"{LanguageConstants.MONITOR_OBJECT_METRIC}.{monitor_obj.name}.{result['name']}"
        result["display_name"] = lan.get(f"{lan_key}.name") or result.get("display_name") or result["name"]
        result["display_description"] = lan.get(f"{lan_key}.desc") or result.get("description")
        if (result.get("data_type") or "").lower() == "enum":
            result["unit"] = localize_metric_enum_unit(
                result.get("unit") or "",
                enum_translations=lan.get(f"{lan_key}.enum"),
            )
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
    """查询同一监控对象下指定名称的所有插件指标数据。

    匹配到多个插件指标时分别查询并合并 VictoriaMetrics 序列，
    每条序列附加 ``metric_id`` 和 ``monitor_plugin`` 用于区分来源。

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
    instance_ids = list(dict.fromkeys(str(instance_id) for instance_id in instance_ids if instance_id not in (None, "")))
    if not instance_ids:
        return {"result": False, "data": [], "message": "instance_ids 不能为空"}

    user_info = kwargs.get("user_info", {})

    permission, error = _get_monitor_instance_permission(monitor_obj_id, user_info)
    if error:
        return error

    try:
        monitor_obj = MonitorObject.objects.get(id=monitor_obj_id)
    except MonitorObject.DoesNotExist:
        return {"result": False, "data": [], "message": "监控对象或指标不存在"}

    metrics = list(Metric.objects.filter(monitor_object=monitor_obj, name=metric_name).select_related("monitor_plugin").order_by("id"))
    if not metrics:
        return {"result": False, "data": [], "message": "监控对象或指标不存在"}

    try:
        step = _normalize_step(step)
        metric_queries = []
        for metric in metrics:
            dimensions = _normalize_dimensions(metric, raw_dimensions)
            if not metric.query:
                return {"result": False, "data": [], "message": "指标查询语句为空"}
            instance_id_keys = _normalize_metric_instance_id_keys(metric, monitor_obj)
            metric_queries.append((metric, dimensions, instance_id_keys))
    except ValueError as exc:
        return {"result": False, "data": [], "message": str(exc)}

    authorized_qs = _get_authorized_instance_queryset(permission)

    authorized_instances = list(
        authorized_qs.filter(
            id__in=instance_ids,
            monitor_object=monitor_obj,
            is_deleted=False,
        ).values_list("id", flat=True)
    )
    if set(authorized_instances) != set(instance_ids):
        return {"result": False, "data": [], "message": "没有权限访问指定的实例"}
    instance_ids = authorized_instances

    authorized_instance_ids = set(
        authorized_qs.filter(monitor_object=monitor_obj, is_deleted=False).values_list(
            "id",
            flat=True,
        )
    )

    try:
        merged_result = None
        merged_series = []
        start_sec = int(start_time) / 1000
        end_sec = int(end_time) / 1000
        step_seconds = Metrics.parse_step_to_seconds(step)
        for metric, dimensions, instance_id_keys in metric_queries:
            query = _build_metric_label_query(
                metric.query,
                instance_ids=instance_ids,
                dimensions=dimensions,
                instance_id_keys=instance_id_keys,
            )
            result = Metrics.get_metrics_range(
                query,
                start_time,
                end_time,
                step,
                fill_missing=False,
            )
            if merged_result is None:
                merged_result = dict(result)
                merged_data = dict(result.get("data") or {})
                merged_data["result"] = merged_series
                merged_result["data"] = merged_data

            plugin_data = _serialize_metric_plugin(metric)
            for metric_data in (result.get("data") or {}).get("result") or []:
                metric_instance_ids = _build_metric_instance_id_candidates(
                    metric_data.get("metric", {}),
                    instance_id_keys,
                )

                if metric_instance_ids and not metric_instance_ids & authorized_instance_ids:
                    continue

                enriched_metric_data = dict(metric_data)
                enriched_metric_data["metric_id"] = metric.id
                enriched_metric_data["monitor_plugin"] = plugin_data
                merged_series.append(enriched_metric_data)
            Metrics.enforce_fill_budget(start_sec, end_sec, step_seconds, merged_series)

        Metrics.fill_missing_points(start_sec, end_sec, step_seconds, merged_series)

        return {"result": True, "data": merged_result, "message": ""}

    except MetricsQueryBudgetExceeded as exc:
        return _build_query_budget_failure(exc)
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
    if only_with_data:
        total_count = metrics.count()
        start = (page - 1) * page_size
        end = start + page_size
        metrics = metrics[start:end]

    query_by_metric_id = {}
    query_has_data = {}
    query_errors = {}
    if only_with_data:
        metrics = list(metrics)
        lookback_seconds = Metrics.parse_step_to_seconds(lookback)
        end_seconds = int(time.time())
        start_seconds = end_seconds - lookback_seconds
        step_seconds = max(1, min(max(lookback_seconds // 12, 1), 300))
        for metric in metrics:
            if metric.query:
                query_by_metric_id[metric.id] = _build_metric_label_query(
                    metric.query,
                    instance_ids=[instance_id],
                )
        vm_api = VictoriaMetricsAPI()

        def _query_has_data(query):
            response = vm_api.query_range(
                query,
                start_seconds,
                end_seconds,
                str(step_seconds),
            )
            return response.get("status") == "success" and bool(response.get("data", {}).get("result"))

        query_has_data, query_errors = run_unique_vm_queries(
            query_by_metric_id.values(),
            _query_has_data,
        )

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
            query = query_by_metric_id.get(metric.id)
            if not query:
                continue
            if query in query_errors:
                error = query_errors[query]
                logger.warning(
                    "monitor_instance_metrics query failed, instance_id=%s, metric=%s, error=%s",
                    instance_id,
                    metric.name,
                    error,
                    exc_info=(type(error), error, error.__traceback__),
                )
                continue
            if not query_has_data[query]:
                continue

        result_metrics.append(metric_info)

    return {
        "result": True,
        "data": {
            "monitor_obj_id": str(monitor_obj.id),
            "instance_id": instance_id,
            **(
                {
                    "count": total_count,
                    "page": page,
                    "page_size": page_size,
                    "items": result_metrics,
                }
                if only_with_data
                else _paginate_items(result_metrics, page, page_size)
            ),
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

    _, _, _, scope_ids, _, scope_error = _get_nats_actor_scope(user_info)
    if scope_error:
        return scope_error

    permission, error = _get_monitor_instance_permission(monitor_obj_id, user_info)
    if error:
        return error

    authorized_qs = _get_authorized_instance_queryset(
        permission,
        scope_ids,
    ).filter(monitor_object_id=monitor_obj_id, is_deleted=False, is_active=True)
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

    accessible_policy_qs, policy_error = _get_nats_accessible_policy_queryset(user_info)
    if policy_error:
        return policy_error

    queryset = MonitorAlert.objects.filter(
        monitor_instance_id__in=authorized_instance_ids,
        policy_id__in=accessible_policy_qs.values_list("id", flat=True),
    )
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


_MONITOR_ALERT_LEVEL_RANK = {
    "critical": 3,
    "error": 2,
    "warning": 1,
}


def _monitor_alert_level_rank(level) -> int:
    if level in (None, ""):
        return 0
    return _MONITOR_ALERT_LEVEL_RANK.get(str(level).strip().lower(), 1)


def _max_monitor_alert_level(levels) -> Optional[str]:
    best_level = None
    best_rank = 0
    for level in levels:
        rank = _monitor_alert_level_rank(level)
        if rank > best_rank:
            best_rank = rank
            best_level = str(level).strip().lower()
    return best_level


def _parse_latest_active_alerts_query(query_data):
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
    return (
        limit,
        instance_ids,
        _normalize_filter_values(query_data.get("level"), "level"),
        _normalize_filter_values(query_data.get("alert_type"), "alert_type"),
    )


def _resolve_latest_active_alert_instances(monitor_obj_id, user_info, scope_ids):
    if monitor_obj_id:
        try:
            MonitorObject.objects.get(id=monitor_obj_id)
        except MonitorObject.DoesNotExist:
            return None, {"result": False, "data": [], "message": "监控对象不存在"}
        permission, error = _get_monitor_instance_permission(monitor_obj_id, user_info)
        if error:
            return None, error
        authorized_qs = (
            _get_authorized_instance_queryset(permission, scope_ids)
            .filter(
                monitor_object_id=monitor_obj_id,
                is_deleted=False,
                is_active=True,
            )
            .select_related("monitor_object")
        )
        return {str(instance.id): instance for instance in authorized_qs}, None
    return _get_authorized_monitor_instances(user_info, scope_ids)


def _filter_requested_alert_instances(authorized_instances, instance_ids):
    authorized_instance_ids = set(authorized_instances.keys())
    requested_instance_ids = list(dict.fromkeys(instance_ids))
    if requested_instance_ids:
        filtered_instance_ids = [instance for instance in requested_instance_ids if instance in authorized_instance_ids]
        if not filtered_instance_ids:
            return None, None, {"result": False, "data": [], "message": "没有权限访问指定的实例"}
        return set(filtered_instance_ids), filtered_instance_ids, None
    if not authorized_instances:
        return (
            None,
            None,
            {
                "result": True,
                "data": {"count": 0, "max_level": None, "items": [], "instance_summaries": []},
                "message": "",
            },
        )
    return authorized_instance_ids, [], None


def _build_latest_active_alert_items(queryset, authorized_instances, limit):
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
    return items


def _build_active_alert_instance_summaries(queryset, filtered_instance_ids):
    if not filtered_instance_ids:
        return []
    levels_by_instance = {}
    for row in queryset.values("monitor_instance_id", "level"):
        instance_id = str(row["monitor_instance_id"])
        levels_by_instance.setdefault(instance_id, []).append(row["level"])
    return [
        {
            "instance_id": instance_id,
            "count": len(levels_by_instance.get(instance_id, [])),
            "max_level": _max_monitor_alert_level(levels_by_instance.get(instance_id, [])),
        }
        for instance_id in filtered_instance_ids
    ]


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
        limit, instance_ids, level_values, alert_type_values = _parse_latest_active_alerts_query(query_data)
    except ValueError as exc:
        return {"result": False, "data": [], "message": str(exc)}

    _, _, _, scope_ids, _, scope_error = _get_nats_actor_scope(user_info)
    if scope_error:
        return scope_error

    authorized_instances, error = _resolve_latest_active_alert_instances(monitor_obj_id, user_info, scope_ids)
    if error:
        return error

    authorized_instance_ids, filtered_instance_ids, filter_error = _filter_requested_alert_instances(
        authorized_instances,
        instance_ids,
    )
    if filter_error:
        return filter_error

    accessible_policy_qs, policy_error = _get_nats_accessible_policy_queryset(user_info)
    if policy_error:
        return policy_error

    queryset = MonitorAlert.objects.filter(
        monitor_instance_id__in=authorized_instance_ids,
        policy_id__in=accessible_policy_qs.values_list("id", flat=True),
        status="new",
    )
    if level_values:
        queryset = queryset.filter(level__in=level_values)
    if alert_type_values:
        queryset = queryset.filter(alert_type__in=alert_type_values)

    total_count = queryset.count()
    return {
        "result": True,
        "data": {
            "count": total_count,
            "max_level": _max_monitor_alert_level(queryset.values_list("level", flat=True)) if total_count else None,
            "items": _build_latest_active_alert_items(queryset, authorized_instances, limit),
            "instance_summaries": _build_active_alert_instance_summaries(queryset, filtered_instance_ids),
        },
        "message": "",
    }


@nats_client.register
def query_latest_interface_metrics(instance_ids=None, *args, **kwargs):
    """Return latest IF-MIB values per instance_id + ifDescr for authorized instances."""
    user_info = kwargs.get("user_info") or {}
    try:
        requested_ids = normalize_instance_ids(instance_ids)
    except InterfaceMetricsQueryError as exc:
        return {"result": False, "data": {"items": []}, "message": str(exc)}

    if not requested_ids:
        return {"result": True, "data": {"items": []}, "message": ""}

    _, _, _, scope_ids, _, scope_error = _get_nats_actor_scope(user_info)
    if scope_error:
        return scope_error

    authorized_instances, error = _get_authorized_monitor_instances(user_info, scope_ids)
    if error:
        return error

    allowed_ids = [item for item in requested_ids if item in authorized_instances]
    if not allowed_ids:
        return {"result": True, "data": {"items": []}, "message": ""}

    try:
        items = query_interface_metric_items(VictoriaMetricsAPI(), allowed_ids)
    except Exception:
        logger.exception("query_latest_interface_metrics failed")
        return {"result": False, "data": {"items": []}, "message": "接口指标查询失败"}
    return {"result": True, "data": {"items": items}, "message": ""}


@nats_client.register
def query_metric_range_scoped(
    monitor_object_id,
    metric_id,
    instance_ids: list,
    time_range: list,
    step="5m",
    *args,
    **kwargs,
):
    """按 NATS 请求携带的用户态执行受控指标范围查询。"""
    try:
        start_time, end_time = parse_rfc3339_range_utc(time_range)
    except ValueError as exc:
        return {"result": False, "data": [], "message": str(exc)}
    user_info = kwargs.get("user_info") or {}
    user = _normalize_permission_user(
        user_info.get("user"),
        domain=user_info.get("domain"),
    )
    try:
        resp = AuthorizedMetricQueryService(
            user=user,
            current_team=user_info.get("team"),
            include_children=bool(user_info.get("include_children", False)),
        ).query_range(
            {
                "monitor_object_id": monitor_object_id,
                "metric_id": metric_id,
                "instance_ids": instance_ids,
                "start": int(rfc3339_to_timestamp(start_time)) * 1000,
                "end": int(rfc3339_to_timestamp(end_time)) * 1000,
                "step": step,
            }
        )
    except MetricsQueryBudgetExceeded as exc:
        return _build_query_budget_failure(exc)
    except AuthorizedMetricQueryError as exc:
        return {"result": False, "data": [], "message": str(exc)}
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
def get_host_resource_top(metric_type: str, *args, **kwargs):
    """Return the latest authorized host CPU, memory, or disk Top10."""
    try:
        metric_type = validate_metric_type(metric_type)
    except ValueError as exc:
        return {"result": False, "data": [], "message": str(exc)}

    user_info = kwargs.get("user_info") or {}
    _, _, _, scope_ids, _, error = _get_nats_actor_scope(user_info)
    if error:
        return error
    authorized_instances, error = _get_authorized_monitor_instances(user_info, scope_ids)
    if error:
        return error
    if "instance_ids" in kwargs:
        try:
            requested_ids = _normalize_filter_values(kwargs.get("instance_ids"), "instance_ids")
        except ValueError as exc:
            return {"result": False, "data": [], "message": str(exc)}
        selected_instances = [authorized_instances[item] for item in requested_ids if item in authorized_instances]
    else:
        selected_instances = list(authorized_instances.values())
    if not selected_instances:
        return {"result": True, "data": [], "message": ""}

    try:
        rows = HostResourceTopService(vm_api=VictoriaMetricsAPI()).run(
            metric_type,
            selected_instances,
        )
    except Exception:
        logger.exception("host resource top query failed metric_type=%s", metric_type)
        return {"result": False, "data": [], "message": "主机资源指标查询失败"}
    return {"result": True, "data": rows, "message": ""}


@nats_client.register
def get_host_instance_list(*args, **kwargs):
    """Return authorized Host monitor instances for ops-analysis filter options."""
    user_info = kwargs.get("user_info") or {}
    _, _, _, scope_ids, _, error = _get_nats_actor_scope(user_info)
    if error:
        return error
    host_obj = MonitorObject.objects.filter(name=HOST_OBJECT_NAME).first()
    if host_obj is None:
        return {"result": True, "data": [], "message": ""}
    authorized_instances, error = _get_authorized_monitor_instances(
        user_info,
        scope_ids,
        monitor_obj_id=host_obj.id,
    )
    if error:
        return error
    return {
        "result": True,
        "data": build_host_instance_rows(authorized_instances.values()),
        "message": "",
    }


@nats_client.register
def get_host_metric_range(*args, **kwargs):
    """Return one line per selected host for a host dashboard metric."""
    try:
        metric_type = validate_range_metric_type(kwargs.get("metric_type"))
    except ValueError as exc:
        return {"result": False, "data": {}, "message": str(exc)}
    try:
        instance_ids = _normalize_filter_values(kwargs.get("instance_ids"), "instance_ids")
    except ValueError as exc:
        return {"result": False, "data": {}, "message": str(exc)}
    if not instance_ids:
        return {"result": True, "data": {}, "message": ""}

    user_info = kwargs.get("user_info") or {}
    _, _, _, scope_ids, _, error = _get_nats_actor_scope(user_info)
    if error:
        return error
    authorized_instances, error = _get_authorized_monitor_instances(user_info, scope_ids)
    if error:
        return error
    selected_instances = [authorized_instances[item] for item in instance_ids if item in authorized_instances]
    if not selected_instances:
        return {"result": True, "data": {}, "message": ""}

    try:
        data = HostMetricRangeService(vm_api=VictoriaMetricsAPI()).run(
            metric_type=metric_type,
            time_range=kwargs.get("time"),
            instances=selected_instances,
            step=kwargs.get("step") or "5m",
        )
    except ValueError as exc:
        return {"result": False, "data": {}, "message": str(exc)}
    except Exception:
        logger.exception("host metric range query failed metric_type=%s", metric_type)
        return {"result": False, "data": {}, "message": "主机指标查询失败"}
    return {"result": True, "data": data, "message": ""}


@nats_client.register
def get_host_resource_snapshot(*args, **kwargs):
    """Return avg/max resource snapshot for selected authorized hosts."""
    try:
        instance_ids = _normalize_filter_values(kwargs.get("instance_ids"), "instance_ids")
    except ValueError as exc:
        return {"result": False, "data": empty_host_snapshot(), "message": str(exc)}
    if not instance_ids:
        return {"result": True, "data": empty_host_snapshot(), "message": ""}

    user_info = kwargs.get("user_info") or {}
    _, _, _, scope_ids, _, error = _get_nats_actor_scope(user_info)
    if error:
        return error
    authorized_instances, error = _get_authorized_monitor_instances(user_info, scope_ids)
    if error:
        return error
    selected_instances = [authorized_instances[item] for item in instance_ids if item in authorized_instances]
    if not selected_instances:
        return {"result": True, "data": empty_host_snapshot(), "message": ""}

    try:
        snapshot = HostResourceSnapshotService(vm_api=VictoriaMetricsAPI()).run(selected_instances)
    except Exception:
        logger.exception("host resource snapshot query failed")
        return {"result": False, "data": empty_host_snapshot(), "message": "主机资源快照查询失败"}
    return {"result": True, "data": snapshot, "message": ""}


@nats_client.register
def get_network_device_resource_top(metric_type: str, *args, **kwargs):
    """Return the latest authorized network-device CPU, memory, or traffic Top10."""
    try:
        metric_type = validate_network_metric_type(metric_type)
    except ValueError as exc:
        return {"result": False, "data": [], "message": str(exc)}
    try:
        limit = int(kwargs.get("limit", 10))
        if not 1 <= limit <= 100:
            raise ValueError
    except (TypeError, ValueError):
        return {"result": False, "data": [], "message": "limit 必须是 1-100 的整数"}

    user_info = kwargs.get("user_info") or {}
    _, _, _, scope_ids, _, error = _get_nats_actor_scope(user_info)
    if error:
        return error
    authorized_instances, error = _get_authorized_monitor_instances(user_info, scope_ids)
    if error:
        return error
    if not authorized_instances:
        return {"result": True, "data": [], "message": ""}

    try:
        rows = NetworkDeviceResourceTopService(vm_api=VictoriaMetricsAPI()).run(
            metric_type,
            list(authorized_instances.values()),
            limit=limit,
        )
    except Exception:
        logger.exception("network device resource top query failed metric_type=%s", metric_type)
        return {"result": False, "data": [], "message": "网络设备资源指标查询失败"}
    return {"result": True, "data": rows, "message": ""}


def _get_nats_actor_scope(user_info):
    """经 Task1 RPC 认证 NATS 用户的 current_team 数据范围。"""
    if not isinstance(user_info, dict):
        return None, None, None, None, None, {"result": False, "data": {}, "message": "缺少用户或组织信息"}

    user = _normalize_permission_user(
        user_info.get("user"),
        domain=user_info.get("domain"),
    )
    include_children = user_info.get("include_children", False)
    username = getattr(user, "username", None)
    domain = getattr(user, "domain", None)
    if (
        not isinstance(username, str)
        or not username.strip()
        or not isinstance(domain, str)
        or not domain.strip()
        or type(include_children) is not bool
    ):
        return None, None, None, None, None, {"result": False, "data": {}, "message": "缺少用户或组织信息"}

    try:
        current_team = next(iter(_normalize_organization_ids([user_info.get("team")])))
    except BaseAppException:
        return None, None, None, None, None, {"result": False, "data": {}, "message": "current_team 参数非法"}

    actor_context = {
        "username": username,
        "domain": domain,
        "current_team": current_team,
    }
    try:
        scope_result = SystemMgmt().get_authorized_groups_scoped(
            actor_context,
            include_children=include_children,
        )
    except Exception:
        return None, None, None, None, None, {"result": False, "data": {}, "message": "获取 current_team 权限范围失败"}

    if (
        not isinstance(scope_result, dict)
        or not scope_result.get("result")
        or not isinstance(scope_result.get("data"), list)
        or type(scope_result.get("is_superuser")) is not bool
    ):
        return None, None, None, None, None, {"result": False, "data": {}, "message": "获取 current_team 权限范围失败"}
    try:
        scope_ids = _normalize_organization_ids(scope_result["data"])
    except BaseAppException:
        return None, None, None, None, None, {"result": False, "data": {}, "message": "获取 current_team 权限范围失败"}
    if current_team not in scope_ids:
        return None, None, None, None, None, {"result": False, "data": {}, "message": "获取 current_team 权限范围失败"}

    return user, current_team, include_children, scope_ids, scope_result["is_superuser"], None


def _get_nats_permission_context(user_info, permission_module):
    """解析用户 NATS 请求的 current_team 和对象权限，任一异常均 fail closed。"""
    user, current_team, include_children, scope_ids, is_superuser, error = _get_nats_actor_scope(user_info)
    if error:
        return None, None, None, error

    permissions_result = get_permissions_rules(
        user,
        current_team,
        "monitor",
        permission_module,
        include_children=include_children,
    )
    if not isinstance(permissions_result, dict):
        return None, None, None, {"result": False, "data": {}, "message": "获取对象权限失败"}

    permission_data = permissions_result.get("data")
    if not isinstance(permission_data, dict):
        return None, None, None, {"result": False, "data": {}, "message": "获取对象权限失败"}
    return permission_data, scope_ids, is_superuser, None


def _get_nats_accessible_policy_queryset(user_info):
    permissions, scope_ids, is_superuser, error = _get_nats_permission_context(
        user_info,
        PermissionConstants.POLICY_MODULE,
    )
    if error:
        return MonitorPolicy.objects.none(), error

    queryset = (
        MonitorPolicy.objects.filter(policyorganization__organization__in=list(scope_ids)).prefetch_related("policyorganization_set").distinct()
    )
    if is_superuser:
        return queryset, None

    authorized_ids = []
    for policy in queryset:
        organizations = {item.organization for item in policy.policyorganization_set.all()}
        if get_instance_permissions(
            str(policy.monitor_object_id),
            policy.id,
            organizations,
            permissions,
            list(scope_ids),
        ):
            authorized_ids.append(policy.id)
    return queryset.filter(id__in=authorized_ids), None


def _get_nats_accessible_instance_queryset(user_info):
    permissions, scope_ids, is_superuser, error = _get_nats_permission_context(
        user_info,
        PermissionConstants.INSTANCE_MODULE,
    )
    if error:
        return MonitorInstance.objects.none(), error

    queryset = (
        MonitorInstance.objects.filter(
            is_deleted=False,
            monitorinstanceorganization__organization__in=list(scope_ids),
        )
        .prefetch_related("monitorinstanceorganization_set")
        .distinct()
    )
    if is_superuser:
        return queryset, None

    authorized_ids = []
    for instance in queryset:
        organizations = {item.organization for item in instance.monitorinstanceorganization_set.all()}
        if get_instance_permissions(
            str(instance.monitor_object_id),
            instance.id,
            organizations,
            permissions,
            list(scope_ids),
        ):
            authorized_ids.append(instance.id)
    return queryset.filter(id__in=authorized_ids), None


@nats_client.register
def get_monitor_statistics(user_info=None, **kwargs):
    """监控中心总览统计

    返回资源/能力/告警三大维度全部计数指标，供 operation_analysis
    内置仪表盘以 single 值卡片渲染（按 selectedFields 取字段）。

    Args:
        user_info: { team: int, user, is_superuser: bool, ... } 由 operation_analysis 注入

    Returns:
        { "result": True, "data": { 各项计数 ... }, "message": "" }
    """
    user_info = user_info or {}
    policy_qs, policy_error = _get_nats_accessible_policy_queryset(user_info)
    if policy_error:
        return policy_error
    instance_qs, instance_error = _get_nats_accessible_instance_queryset(user_info)
    if instance_error:
        return instance_error

    # ============ 资源概览 ============
    # 监控对象/对象类型属平台级目录（各组织一致），非租户数据，不做组织收窄
    monitor_object_total = MonitorObject.objects.count()
    monitor_object_visible = MonitorObject.objects.filter(is_visible=True).count()
    monitor_object_category = MonitorObjectType.objects.count()

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
    # 采集配置跟随受限实例权限根。
    collect_config_total = CollectConfig.objects.filter(monitor_instance_id__in=instance_qs.values_list("id", flat=True)).count()

    # ============ 告警概览 ============
    # 下游 alert/event/snapshot/baseline 全部继承受限策略权限根。
    policy_total = policy_qs.count()
    policy_enabled = policy_qs.filter(enable=True).count()
    policy_disabled = policy_qs.filter(enable=False).count()
    # 阈值策略：有 threshold 配置 / 无数据策略：no_data_level 非空
    policy_threshold = policy_qs.exclude(threshold=[]).count()
    policy_no_data = policy_qs.exclude(no_data_level="").count()

    alert_qs = MonitorAlert.objects.filter(policy_id__in=policy_qs.values_list("id", flat=True))
    alert_history = alert_qs.count()
    alert_current = alert_qs.filter(status="new").count()
    alert_recovered = alert_qs.filter(status="recovered").count()
    alert_closed = alert_qs.filter(status="closed").count()

    today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    alert_today = alert_qs.filter(created_at__gte=today_start).count()

    event_qs = MonitorEvent.objects.filter(policy_id__in=policy_qs.values_list("id", flat=True)).filter(
        Q(alert__isnull=True) | Q(alert__policy_id=F("policy_id"))
    )
    event_total = event_qs.count()
    event_today = event_qs.filter(created_at__gte=today_start).count()

    alert_snapshot_total = MonitorAlertMetricSnapshot.objects.filter(
        policy_id__in=policy_qs.values_list("id", flat=True),
        alert__policy_id=F("policy_id"),
    ).count()

    no_data_baseline_total = PolicyInstanceBaseline.objects.filter(policy_id__in=policy_qs.values_list("id", flat=True)).count()

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


def _resolve_monitor_ingest_allowed_org_ids(params):
    """解析跨模块 ingest 的组织授权范围；不得从 raw.organization 反推。"""
    if "allowed_org_ids" in (params or {}):
        return _normalize_organization_ids(params.get("allowed_org_ids"))

    for scope_key in ("service_scope", "scope"):
        scope = (params or {}).get(scope_key)
        if isinstance(scope, dict) and "allowed_org_ids" in scope:
            return _normalize_organization_ids(scope.get("allowed_org_ids"))

    user_info = (params or {}).get("user_info")
    if isinstance(user_info, dict):
        team = user_info.get("team")
        if team not in (None, ""):
            return _normalize_organization_ids([team] if not isinstance(team, (list, tuple)) else team)

    raise ValueError("authorization scope is required for monitor ingest")


@nats_client.register
def monitor_ingest_from_source(params):
    """跨模块推送写入监控（node_id → cmdb_id → ip+cloud）。

    params 为 IngestEnvelope 扩展字段，另需授权上下文之一：
      allowed_org_ids / service_scope.allowed_org_ids / user_info.team

    NATS 方法名带 monitor_ 前缀，避免与 CMDB.ingest_from_source 冲突。
    """
    from apps.monitor.services.module_ingest import MonitorModuleIngestService

    params = dict(params or {})
    params["allowed_org_ids"] = _resolve_monitor_ingest_allowed_org_ids(params)
    return MonitorModuleIngestService.ingest(params)
