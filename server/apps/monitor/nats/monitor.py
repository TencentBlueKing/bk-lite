import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from time import perf_counter
from types import SimpleNamespace
from typing import Optional

from django.db import transaction
from django.db.models import Count, F, Q
from django.utils import timezone
from rest_framework import serializers

import nats_client
from apps.cmdb.services.monitored_host import normalize_zombie_whitelist
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.logger import monitor_logger as monitor_logger
from apps.core.logger import nats_logger as logger
from apps.core.logger import safe_exception_info
from apps.core.utils.current_team_scope import _normalize_organization_ids
from apps.core.utils.loader import LanguageLoader
from apps.core.utils.permission_utils import (
    check_instance_permission,
    get_instance_permissions,
    get_permission_rules,
    get_permissions_rules,
    permission_filter,
)
from apps.core.utils.time_util import format_rfc3339_utc, parse_rfc3339_range_utc, rfc3339_to_timestamp
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
    MonitorInstanceOrganization,
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
from apps.monitor.services.alert_access import filter_alerts_by_organizations, orphaned_monitor_policy_q
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
from apps.monitor.services.metric_query_contract import escape_metric_label_value
from apps.monitor.services.metric_series import (
    DEFAULT_OBJECT_NAMES,
    DEFAULT_RANGE_STEP,
    MetricSeriesQueryError,
    MetricSeriesQueryService,
    build_monitor_instance_rows,
    canonical_dimension_names,
    validate_collect_type,
    validate_instance_id_count,
    validate_limit,
    validate_metric_name,
    validate_mode,
    wrap_avg_over_time,
)
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
from apps.monitor.services.zombie_host_query import ZombieHostQueryError, count_successful_logins, load_hosts_for_systems, load_selected_hosts
from apps.monitor.services.zombie_host_report import (
    FOLD_MAX,
    FOLD_SUM,
    ZOMBIE_METRIC_SPECS,
    apply_thresholds,
    fold_io_max,
    parse_threshold,
    range_window,
    round_display_metrics,
    validate_inst_uuids,
    wrap_max_over_time,
)
from apps.monitor.utils.dimension import parse_instance_id
from apps.monitor.utils.instance_id_keys import resolve_monitor_object_instance_id_keys
from apps.monitor.utils.metric_enum_locale import localize_metric_enum_unit
from apps.monitor.utils.victoriametrics_api import VictoriaMetricsAPI
from apps.monitor.utils.vm_query_batch import run_unique_vm_queries
from apps.rpc.system_mgmt import SystemMgmt

_normalize_bool = normalize_bool

DEFAULT_ZOMBIE_WINDOW_MINUTES = 10080
_ZOMBIE_METRIC_ROW_KEYS = (
    "cpu_avg",
    "cpu_max",
    "mem_avg",
    "mem_max",
    "packets_recv_avg",
    "packets_recv_max",
    "io_max",
    "login_count",
    "login_status",
)
_ZOMBIE_FIELD_BY_METRIC = {
    ("cpu", "avg"): "cpu_avg",
    ("cpu", "max"): "cpu_max",
    ("mem", "avg"): "mem_avg",
    ("mem", "max"): "mem_max",
    ("packets", "avg"): "packets_recv_avg",
    ("packets", "max"): "packets_recv_max",
    ("io", "max"): "io_max",
}


def _filter_nats_visible_alerts(queryset, scope_ids, accessible_policy_qs):
    queryset = filter_alerts_by_organizations(queryset, scope_ids)
    return queryset.filter(Q(policy_id__in=accessible_policy_qs.values("id")) | orphaned_monitor_policy_q())


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
def license_monitor_instance_count(*args, **kwargs):
    """许可管理专用：已启用且属于收费对象目录的监控资产实例数量。"""
    from apps.monitor.constants.license_catalog import MONITOR_LICENSE_OBJECT_NAMES

    queryset = (
        MonitorInstance.objects.filter(
            is_deleted=False,
            is_active=True,
            monitor_object__name__in=MONITOR_LICENSE_OBJECT_NAMES,
        )
        .values("monitor_object__name")
        .annotate(instance_count=Count("id"))
    )
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

    queryset = _filter_nats_visible_alerts(
        MonitorAlert.objects.filter(monitor_instance_id__in=authorized_instance_ids),
        scope_ids,
        accessible_policy_qs,
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

    queryset = _filter_nats_visible_alerts(
        MonitorAlert.objects.filter(
            monitor_instance_id__in=authorized_instance_ids,
            status="new",
        ),
        scope_ids,
        accessible_policy_qs,
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


def _zombie_page_data(items, page, page_size):
    return _paginate_items(items, page, page_size)


def _zombie_empty_success(page, page_size):
    return {"result": True, "data": _zombie_page_data([], page, page_size), "message": ""}


def _zombie_fail(message, page, page_size):
    return {
        "result": False,
        "data": {"items": [], "count": 0, "page": page, "page_size": page_size},
        "message": message,
    }


def _zombie_log_failure(failed_stage: str, exc: BaseException):
    monitor_logger.error(
        "event=zombie_host_report_failed failed_stage=%s error_type=%s",
        failed_stage,
        type(exc).__name__,
        exc_info=safe_exception_info(exc),
    )


def _coerce_selected_hosts(loaded):
    if isinstance(loaded, dict) and isinstance(loaded.get("result"), bool):
        if not loaded["result"]:
            raise ZombieHostQueryError(str(loaded.get("message") or "CMDB 查询失败"))
        loaded = loaded.get("data")
    if loaded is None:
        return []
    if isinstance(loaded, list):
        return [row for row in loaded if isinstance(row, dict)]
    if isinstance(loaded, dict):
        return [row for row in loaded.values() if isinstance(row, dict)]
    raise ZombieHostQueryError("CMDB 查询结果格式错误")


def _filter_zombie_identities(hosts, os_type, zombie_whitelist):
    filtered = list(hosts)
    if os_type not in (None, ""):
        wanted = os_type if isinstance(os_type, (list, tuple)) else [os_type]
        wanted_set = {str(item).strip() for item in wanted if item not in (None, "")}
        if wanted_set:
            filtered = [host for host in filtered if str(host.get("os_type") or "") in wanted_set]
    if zombie_whitelist not in (None, ""):
        wanted_whitelist = normalize_zombie_whitelist(zombie_whitelist)
        filtered = [host for host in filtered if normalize_zombie_whitelist(host.get("zombie_whitelist")) == wanted_whitelist]
    return filtered


def _minutes_to_rfc3339_range(minutes: int):
    if minutes <= 0:
        raise ValueError("time 必须大于 0")
    end = datetime.now(dt_timezone.utc)
    start = end - timedelta(minutes=minutes)
    rfc = [format_rfc3339_utc(start), format_rfc3339_utc(end)]
    return rfc, float(start.timestamp()), float(end.timestamp())


def _parse_zombie_time(time_value):
    if time_value is None or time_value == "":
        return _minutes_to_rfc3339_range(DEFAULT_ZOMBIE_WINDOW_MINUTES)
    if isinstance(time_value, bool):
        raise ValueError("time 格式错误")
    if isinstance(time_value, (int, float)):
        return _minutes_to_rfc3339_range(int(time_value))
    if isinstance(time_value, str) and time_value.strip().isdigit():
        return _minutes_to_rfc3339_range(int(time_value.strip()))
    start_dt, end_dt = parse_rfc3339_range_utc(time_value)
    rfc = [format_rfc3339_utc(start_dt), format_rfc3339_utc(end_dt)]
    return rfc, float(start_dt.timestamp()), float(end_dt.timestamp())


def _logical_monitor_instance_id(value) -> str:
    parsed = parse_instance_id(value)
    if not parsed:
        return "" if value in (None, "") else str(value)
    first = parsed[0]
    if first in (None, ""):
        return ""
    return str(first)


def _instance_id_matcher(instance_ids):
    logical = []
    seen = set()
    for item in instance_ids:
        value = _logical_monitor_instance_id(item)
        if not value or value in seen:
            continue
        seen.add(value)
        logical.append(value)
    escaped = "|".join(escape_metric_label_value(re.escape(str(item))) for item in logical)
    return f'instance_id=~"{escaped}"'


def _finite_metric_number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def _vm_instant_series(resp, authorized_ids):
    if not isinstance(resp, dict) or resp.get("status") != "success":
        message = ""
        if isinstance(resp, dict):
            message = resp.get("error") or resp.get("message") or ""
        raise ZombieHostQueryError(str(message) or "监控指标查询失败")
    data = resp.get("data") if isinstance(resp.get("data"), dict) else {}
    series = []
    for item in data.get("result") or []:
        if not isinstance(item, dict):
            continue
        metric = item.get("metric") if isinstance(item.get("metric"), dict) else {}
        instance_id = _logical_monitor_instance_id(metric.get("instance_id") or metric.get("monitor_id") or "")
        if not instance_id or instance_id not in authorized_ids:
            continue
        value = item.get("value")
        raw = value[1] if isinstance(value, (list, tuple)) and len(value) >= 2 else value
        series.append({"instance_id": instance_id, "device": metric.get("device"), "value": raw})
    return series


def _fold_zombie_series(series, fold):
    if fold == FOLD_MAX:
        return fold_io_max(series)
    folded = {}
    for item in series:
        instance_id = str(item.get("instance_id") or "")
        number = _finite_metric_number(item.get("value"))
        if not instance_id or number is None:
            continue
        if fold == FOLD_SUM:
            folded[instance_id] = folded.get(instance_id, 0.0) + number
        else:
            folded[instance_id] = number
    return folded


def _index_login_rows(rows):
    by_monitor = {}
    by_name = {}
    by_ip = {}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        monitor_id = row.get("monitor_id")
        if monitor_id not in (None, ""):
            by_monitor[str(monitor_id)] = row
        host_name = str(row.get("host_name") or "").strip().lower()
        if host_name:
            by_name[host_name] = row
        ip = str(row.get("ip") or "").strip().lower()
        if ip:
            by_ip[ip] = row
    return by_monitor, by_name, by_ip


def _match_login_row(host, by_monitor, by_name, by_ip):
    monitor_id = host.get("monitor_id")
    if monitor_id not in (None, "") and str(monitor_id) in by_monitor:
        return by_monitor[str(monitor_id)]
    host_name = str(host.get("host_name") or "").strip().lower()
    if host_name and host_name in by_name:
        return by_name[host_name]
    ip = str(host.get("ip") or "").strip().lower()
    if ip and ip in by_ip:
        return by_ip[ip]
    return None


def _assemble_zombie_row(host, metric_maps, login_row):
    monitor_id = str(host.get("monitor_id") or "")
    logical_id = _logical_monitor_instance_id(monitor_id)
    row = {
        "biz_name": host.get("biz_name") or "",
        "host_name": host.get("host_name") or "",
        "os_type_label": host.get("os_type_label") or "",
        "ip": host.get("ip") or "",
        "zombie_whitelist": host.get("zombie_whitelist") or "no",
        "inst_uuid": host.get("inst_uuid"),
        "monitor_id": host.get("monitor_id"),
        "os_type": host.get("os_type"),
        "node_id": host.get("node_id"),
    }
    for key in _ZOMBIE_METRIC_ROW_KEYS:
        row[key] = None
    for (metric_name, window_name), values in metric_maps.items():
        field = _ZOMBIE_FIELD_BY_METRIC.get((metric_name, window_name))
        if field:
            row[field] = values.get(logical_id)
    if login_row:
        row["login_count"] = login_row.get("login_count")
        row["login_status"] = login_row.get("login_status") or "uncollected"
    else:
        row["login_count"] = None
        row["login_status"] = "uncollected"
    return row


def _query_zombie_vm_metrics(matcher, window, end_ts, authorized_id_set):
    vm_api = VictoriaMetricsAPI()
    planned = []
    for metric_name, spec in ZOMBIE_METRIC_SPECS.items():
        labeled = spec["query"].replace("__$labels__", matcher)
        for window_name in spec["windows"]:
            if window_name == "avg":
                query = wrap_avg_over_time(labeled, window)
            else:
                query = wrap_max_over_time(labeled, window)
            planned.append((metric_name, window_name, query, spec["fold"]))
    results, errors = run_unique_vm_queries(
        [item[2] for item in planned],
        lambda query: vm_api.query(query, time=str(int(end_ts))),
    )
    if errors:
        raise next(iter(errors.values()))
    metric_maps = {}
    for metric_name, window_name, query, fold in planned:
        series = _vm_instant_series(results.get(query), authorized_id_set)
        metric_maps[(metric_name, window_name)] = _fold_zombie_series(series, fold)
    return metric_maps


def _query_zombie_logins(hosts, rfc_range, user_info):
    login_result = count_successful_logins(hosts, rfc_range, user_info)
    if isinstance(login_result, dict) and isinstance(login_result.get("result"), bool) and not login_result["result"]:
        raise ZombieHostQueryError(str(login_result.get("message") or "成功登录计数失败"))
    return login_result


@nats_client.register
def get_zombie_host_report(  # noqa: C901
    inst_uuids=None,
    system_uuids=None,
    time=None,
    os_type=None,
    zombie_whitelist=None,
    user_info=None,
    page=1,
    page_size=20,
    **thresholds,
):
    """拼所选应用系统（或主机）下已监控主机的 CPU/内存/IO/入包与成功登录，阈值过滤后分页。"""
    started = perf_counter()
    try:
        page = _normalize_positive_int(page, "page", default=1)
        page_size = _normalize_positive_int(page_size, "page_size", default=20)
    except ValueError as exc:
        return _zombie_fail(str(exc), 1, 20)

    unique_systems = None
    if system_uuids is None:
        try:
            unique_uuids = validate_inst_uuids([] if inst_uuids is None else inst_uuids)
        except (TypeError, ValueError) as exc:
            return _zombie_fail(str(exc), page, page_size)
        if not unique_uuids:
            return _zombie_empty_success(page, page_size)
    elif not isinstance(system_uuids, list):
        return _zombie_fail("system_uuids 必须是列表", page, page_size)
    else:
        unique_systems = []
        seen_systems = set()
        for item in system_uuids:
            if item is None:
                continue
            text = str(item).strip()
            if not text or text in seen_systems:
                continue
            seen_systems.add(text)
            unique_systems.append(text)
        if not unique_systems:
            return _zombie_empty_success(page, page_size)
        unique_uuids = None

    user_info = user_info or {}
    _, _, _, scope_ids, _, scope_error = _get_nats_actor_scope(user_info)
    if scope_error:
        return _zombie_fail(scope_error.get("message") or "缺少用户或组织信息", page, page_size)
    cmdb_user_info = dict(user_info)
    cmdb_user_info["allowed_org_ids"] = list(scope_ids)

    if unique_uuids is None:
        try:
            hosts = _coerce_selected_hosts(load_hosts_for_systems(unique_systems, cmdb_user_info))
        except ValueError as exc:
            return _zombie_fail(str(exc), page, page_size)
        except Exception as exc:
            _zombie_log_failure("load_systems", exc)
            return _zombie_fail(str(exc) if isinstance(exc, ZombieHostQueryError) else "CMDB 应用系统查询失败", page, page_size)
        if not hosts:
            return _zombie_empty_success(page, page_size)
    else:
        try:
            hosts = _coerce_selected_hosts(load_selected_hosts(unique_uuids, cmdb_user_info))
        except Exception as exc:
            _zombie_log_failure("load_hosts", exc)
            return _zombie_fail(str(exc) if isinstance(exc, ZombieHostQueryError) else "CMDB 主机查询失败", page, page_size)

    hosts = _filter_zombie_identities(hosts, os_type, zombie_whitelist)
    identity_count = len(hosts)
    if not hosts:
        return _zombie_empty_success(page, page_size)

    authorized_instances, auth_error = _get_authorized_monitor_instances(user_info, scope_ids)
    if auth_error:
        return _zombie_fail(auth_error.get("message") or "获取监控实例权限失败", page, page_size)

    authorized_ids = {str(item) for item in authorized_instances}
    hosts = [host for host in hosts if str(host.get("monitor_id") or "") in authorized_ids]
    monitor_logger.info(
        "event=zombie_host_report_hosts_filtered identity_count=%s authorized_count=%s",
        identity_count,
        len(hosts),
    )
    if not hosts:
        return _zombie_empty_success(page, page_size)

    try:
        rfc_range, start_ts, end_ts = _parse_zombie_time(time)
        bound = parse_threshold(thresholds)
    except (TypeError, ValueError) as exc:
        return _zombie_fail(str(exc), page, page_size)

    authorized_monitor_ids = [str(host.get("monitor_id")) for host in hosts]
    authorized_id_set = {_logical_monitor_instance_id(item) for item in authorized_monitor_ids}
    authorized_id_set.discard("")
    matcher = _instance_id_matcher(authorized_monitor_ids)
    window = range_window(start_ts, end_ts)
    vm_exc = None
    login_exc = None
    metric_maps = {}
    login_result = None
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            fut_vm = executor.submit(_query_zombie_vm_metrics, matcher, window, end_ts, authorized_id_set)
            fut_login = executor.submit(_query_zombie_logins, hosts, rfc_range, user_info)
            try:
                metric_maps = fut_vm.result()
            except Exception as exc:
                vm_exc = exc
            try:
                login_result = fut_login.result()
            except Exception as exc:
                login_exc = exc
    except Exception as exc:
        vm_exc = exc
    if vm_exc is not None:
        _zombie_log_failure("vm_query", vm_exc)
        return _zombie_fail(str(vm_exc) if isinstance(vm_exc, ZombieHostQueryError) else "监控指标查询失败", page, page_size)
    if login_exc is not None:
        _zombie_log_failure("login_count", login_exc)
        message = str(login_exc) if isinstance(login_exc, ZombieHostQueryError) else "成功登录计数失败"
        return _zombie_fail(message, page, page_size)

    login_rows = login_result.get("data") if isinstance(login_result, dict) else login_result
    if not isinstance(login_rows, list):
        login_rows = []
    by_monitor, by_name, by_ip = _index_login_rows(login_rows)
    rows = [_assemble_zombie_row(host, metric_maps, _match_login_row(host, by_monitor, by_name, by_ip)) for host in hosts]
    filtered_rows = apply_thresholds(rows, bound)
    display_rows = [round_display_metrics(row) for row in filtered_rows]
    monitor_logger.info(
        "event=zombie_host_report_completed identity_count=%s authorized_count=%s result_count=%s elapsed_ms=%s",
        identity_count,
        len(hosts),
        len(filtered_rows),
        int((perf_counter() - started) * 1000),
    )
    return {"result": True, "data": _zombie_page_data(display_rows, page, page_size), "message": ""}


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


def _empty_metric_series(mode: str):
    return {} if mode == "range" else []


def _resolve_metric_series_items(instances, metric_name: str, collect_type: str | None):
    grouped = {}
    for instance in instances:
        monitor_object = getattr(instance, "monitor_object", None)
        object_id = getattr(instance, "monitor_object_id", None)
        if object_id is None:
            object_id = getattr(monitor_object, "id", None)
        if object_id is None:
            continue
        grouped.setdefault(object_id, []).append(instance)

    items = []
    found_metric = False
    for object_id, object_instances in grouped.items():
        metrics = list(Metric.objects.filter(monitor_object_id=object_id, name=metric_name).select_related("monitor_plugin"))
        if metrics:
            found_metric = True
        for metric in metrics:
            plugin = getattr(metric, "monitor_plugin", None)
            plugin_collect_type = str(getattr(plugin, "collect_type", "") or "").strip().lower()
            if collect_type and plugin_collect_type != collect_type:
                continue
            query = str(getattr(metric, "query", "") or "").strip()
            if not query:
                raise ValueError("指标查询语句为空")
            items.append(
                {
                    "query": query,
                    "instance_ids": [str(item.id) for item in object_instances],
                    "instance_id_keys": _normalize_metric_instance_id_keys(metric, object_instances[0].monitor_object),
                    "dimensions": canonical_dimension_names(getattr(metric, "dimensions", None)),
                }
            )
    return found_metric, items


@nats_client.register
def get_monitor_instance_list(*args, **kwargs):
    """Return authorized monitor instances for ops-analysis filter options.

    未传 object_names 时默认网络设备，且必须已启用 Flow 协议。
    显式传入 object_names（如 Cluster）时不再要求 Flow 协议，供 K8S 等对象筛选。
    """
    try:
        protocol = validate_collect_type(kwargs.get("protocol"))
        object_names = _normalize_filter_values(kwargs.get("object_names"), "object_names")
    except ValueError as exc:
        return {"result": False, "data": [], "message": str(exc)}

    explicit_object_names = bool(object_names)
    if not object_names:
        object_names = list(DEFAULT_OBJECT_NAMES)

    user_info = kwargs.get("user_info") or {}
    _, _, _, scope_ids, _, error = _get_nats_actor_scope(user_info)
    if error:
        return error
    authorized_instances, error = _get_authorized_monitor_instances(user_info, scope_ids)
    if error:
        return error
    allowed_names = set(object_names)
    selected = [
        instance
        for instance in authorized_instances.values()
        if str(getattr(getattr(instance, "monitor_object", None), "name", "") or "") in allowed_names
    ]
    return {
        "result": True,
        "data": build_monitor_instance_rows(
            selected,
            protocol=protocol,
            require_enabled_protocols=not explicit_object_names,
        ),
        "message": "",
    }


@nats_client.register
def query_metric_series(*args, **kwargs):
    """Query a registered metric as range series or instant ranking rows."""
    mode = None
    try:
        mode = validate_mode(kwargs.get("mode"))
        metric_name = validate_metric_name(kwargs.get("metric"))
        collect_type = validate_collect_type(kwargs.get("collect_type"))
        limit = validate_limit(kwargs.get("limit"))
        instance_ids = _normalize_filter_values(kwargs.get("instance_ids"), "instance_ids")
        validate_instance_id_count(instance_ids)
    except ValueError as exc:
        return {"result": False, "data": _empty_metric_series(mode or ""), "message": str(exc)}
    empty = _empty_metric_series(mode)
    if not instance_ids:
        return {"result": True, "data": empty, "message": ""}

    try:
        start, end = parse_rfc3339_range_utc(kwargs.get("time"))
        step = _normalize_step(kwargs.get("step") or DEFAULT_RANGE_STEP)
    except ValueError as exc:
        return {"result": False, "data": empty, "message": str(exc)}

    user_info = kwargs.get("user_info") or {}
    _, _, _, scope_ids, _, error = _get_nats_actor_scope(user_info)
    if error:
        return error
    authorized_instances, error = _get_authorized_monitor_instances(user_info, scope_ids)
    if error:
        return error
    selected_instances = [authorized_instances[item] for item in instance_ids if item in authorized_instances]
    if not selected_instances:
        return {"result": True, "data": empty, "message": ""}

    try:
        found_metric, items = _resolve_metric_series_items(selected_instances, metric_name, collect_type)
        if not found_metric:
            return {"result": False, "data": empty, "message": "指标不存在"}
        if not items:
            return {"result": True, "data": empty, "message": ""}
        data = MetricSeriesQueryService(
            vm_api=VictoriaMetricsAPI(),
            build_label_query=_build_metric_label_query,
        ).run(
            mode=mode,
            items=items,
            start_ts=float(rfc3339_to_timestamp(start)),
            end_ts=float(rfc3339_to_timestamp(end)),
            step=step,
            limit=limit,
        )
    except ValueError as exc:
        return {"result": False, "data": empty, "message": str(exc)}
    except MetricSeriesQueryError as exc:
        return {"result": False, "data": empty, "message": str(exc)}
    except Exception:
        logger.exception("metric series query failed metric=%s mode=%s", metric_name, mode)
        return {"result": False, "data": empty, "message": "指标查询失败"}
    return {"result": True, "data": data, "message": ""}


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
    _, _, _, scope_ids, _, scope_error = _get_nats_actor_scope(user_info)
    if scope_error:
        return scope_error
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

    alert_qs = _filter_nats_visible_alerts(MonitorAlert.objects.all(), scope_ids, policy_qs)
    alert_history = alert_qs.count()
    alert_current = alert_qs.filter(status="new").count()
    alert_recovered = alert_qs.filter(status="recovered").count()
    alert_closed = alert_qs.filter(status="closed").count()

    today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    alert_today = alert_qs.filter(created_at__gte=today_start).count()

    event_qs = MonitorEvent.objects.filter(
        Q(alert_id__in=alert_qs.values("id")) | Q(alert__isnull=True, policy_id__in=policy_qs.values("id"))
    ).filter(Q(alert__isnull=True) | Q(alert__policy_id=F("policy_id")))
    event_total = event_qs.count()
    event_today = event_qs.filter(created_at__gte=today_start).count()

    alert_snapshot_total = MonitorAlertMetricSnapshot.objects.filter(
        Q(alert_id__in=alert_qs.values("id")) | Q(policy_id__in=policy_qs.values("id"), alert__policy_id=F("policy_id"))
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


MONITOR_INSTANCE_ALERT_RANKING_MOST = "most_alerts"
MONITOR_INSTANCE_ALERT_RANKING_LEAST = "least_policy_alerts"


def _policy_covered_instance_ids(policy_qs, instance_qs):
    instance_ids = set(instance_qs.values_list("id", flat=True))
    covered = set()
    for policy in policy_qs.filter(enable=True).only("id", "monitor_object_id", "source"):
        source = policy.source if isinstance(policy.source, dict) else {}
        source_type = source.get("type")
        source_values = source.get("values") or []
        if source_type == "instance":
            covered.update(value for value in source_values if value in instance_ids)
            continue
        if source_type == "organization":
            covered.update(
                MonitorInstanceOrganization.objects.filter(
                    monitor_instance__monitor_object_id=policy.monitor_object_id,
                    monitor_instance_id__in=instance_ids,
                    organization__in=source_values,
                ).values_list("monitor_instance_id", flat=True)
            )
            continue
        covered.update(instance_qs.filter(monitor_object_id=policy.monitor_object_id).values_list("id", flat=True))
    return covered


@nats_client.register
def get_monitor_instance_alert_ranking(user_info=None, ranking="most_alerts", limit=10, time=None, **kwargs):
    """监控实例告警排行：告警最多，或已配策略且告警最少（含 0）。"""
    user_info = user_info or {}
    ranking = (ranking or kwargs.get("ranking") or MONITOR_INSTANCE_ALERT_RANKING_MOST).strip()
    if ranking not in {MONITOR_INSTANCE_ALERT_RANKING_MOST, MONITOR_INSTANCE_ALERT_RANKING_LEAST}:
        return {"result": False, "data": [], "message": "ranking 参数无效"}

    policy_qs, policy_error = _get_nats_accessible_policy_queryset(user_info)
    if policy_error:
        return policy_error
    instance_qs, instance_error = _get_nats_accessible_instance_queryset(user_info)
    if instance_error:
        return instance_error

    try:
        start, end = parse_rfc3339_range_utc(time if time is not None else kwargs.get("time"))
    except ValueError as exc:
        return {"result": False, "data": [], "message": str(exc)}

    try:
        limit = int(limit or 10)
    except (TypeError, ValueError):
        limit = 10
    if limit <= 0:
        limit = 10
    if limit > 100:
        limit = 100

    if ranking == MONITOR_INSTANCE_ALERT_RANKING_LEAST:
        candidate_ids = _policy_covered_instance_ids(policy_qs, instance_qs)
    else:
        candidate_ids = set(instance_qs.values_list("id", flat=True))

    if not candidate_ids:
        return {"result": True, "data": [], "message": ""}

    alert_counts = {
        item["monitor_instance_id"]: item["count"]
        for item in MonitorAlert.objects.filter(
            monitor_instance_id__in=candidate_ids,
            created_at__gte=start,
            created_at__lt=end,
        )
        .order_by()
        .values("monitor_instance_id")
        .annotate(count=Count("id"))
    }
    names = dict(instance_qs.filter(id__in=candidate_ids).values_list("id", "name"))
    rows = [
        {
            "instance_id": instance_id,
            "instance_name": names.get(instance_id) or instance_id,
            "count": alert_counts.get(instance_id, 0),
        }
        for instance_id in candidate_ids
    ]
    if ranking == MONITOR_INSTANCE_ALERT_RANKING_MOST:
        rows = [item for item in rows if item["count"] > 0]
        rows.sort(key=lambda item: (-item["count"], item["instance_name"]))
    else:
        rows.sort(key=lambda item: (item["count"], item["instance_name"]))
    return {"result": True, "data": rows[:limit], "message": ""}


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
def query_active_alert_summaries_by_monitor_ids(monitor_ids=None, user_info=None, **kwargs):
    """Batch active-alert summaries for room3D / similar CMDB callers.

    Only status=new alerts under actor-accessible policies; levels critical|error|warning.
    """
    from apps.monitor.services.active_alert_summaries import summarize_active_alerts_by_monitor_ids

    return summarize_active_alerts_by_monitor_ids(monitor_ids, user_info=user_info or {})


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
