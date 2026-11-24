"""监控通用查询 NATS handler。统计在监控模块内完成，不把全量样本交回运营分析。"""

from types import SimpleNamespace

import nats_client
from apps.core.logger import monitor_logger as logger
from apps.monitor.models.monitor_object import MonitorInstance, MonitorObject, MonitorObjectType
from apps.monitor.models.monitor_policy import MonitorAlert, MonitorPolicy
from apps.monitor.nats.monitor import (
    _filter_nats_visible_alerts,
    _get_authorized_instance_queryset,
    _get_monitor_instance_permission,
    _get_nats_accessible_instance_queryset,
    _get_nats_accessible_policy_queryset,
    _get_nats_actor_scope,
)
from apps.monitor.services.authorized_metric_query import (
    GROUPING_INSTANCE,
    AuthorizedMetricQueryError,
    AuthorizedMetricQueryService,
    _instance_lookup_candidates,
    _metric_instance_id_keys,
)
from apps.monitor.services.collection_query import query_collection_rows
from apps.monitor.services.generic_query import (
    ALERT_DISTRIBUTION_FIELDS,
    GenericQueryError,
    _filled,
    _id_list,
    build_metric_result,
    ensure_payload_limit,
    metric_instance_labels,
    query_alert_counts,
    query_alert_details,
    query_alert_distribution,
    query_instance_counts,
    query_instances,
    validate_metric_request,
)
from apps.monitor.services.generic_query_limits import STAT_GROUP_MAX
from apps.monitor.services.instance_distribution import GROUP_BY_OBJECT, GROUP_BY_TYPE, query_instance_distribution
from apps.monitor.services.interface_current import query_interface_current_rows
from apps.monitor.utils.victoriametrics_api import VictoriaMetricsAPI


def _existing_monitor_object_id(monitor_object_id):
    text = str(monitor_object_id).strip()
    if not text.isdigit():
        return None
    object_id = int(text)
    if not MonitorObject.objects.filter(id=object_id).exists():
        return None
    return object_id


def _ok(data) -> dict:
    ensure_payload_limit(data)
    return {"result": True, "data": data, "message": ""}


def _fail(message: str, status: str = "failed") -> dict:
    return {"result": False, "data": {"status": status}, "message": message}


def _guard(stage: str):
    def decorate(func):
        def wrapped(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except GenericQueryError as exc:
                return _fail(exc.message, exc.status)
            except AuthorizedMetricQueryError as exc:
                status = "forbidden" if str(exc.code).endswith("forbidden") else "failed"
                return _fail(str(exc), status)
            except Exception as exc:
                logger.exception(
                    "event=monitor_generic_query_failed failed_stage=%s error_type=%s",
                    stage,
                    type(exc).__name__,
                )
                return _fail("查询失败", "failed")

        wrapped.__name__ = func.__name__
        return wrapped

    return decorate


def _metric_condition_filters(filters):
    if filters in (None, "", [], {}):
        return []
    if isinstance(filters, list):
        return filters
    if isinstance(filters, dict) and set(filters) <= {"logic", "items"}:
        items = filters.get("items") or []
        if not isinstance(items, list):
            raise GenericQueryError("filters 必须是条件")
        for item in items:
            if not isinstance(item, dict):
                raise GenericQueryError("filters 必须是条件")
            label = str(item.get("field") or item.get("label") or "").strip()
            value = item.get("value")
            if label == "" and value not in (None, ""):
                raise GenericQueryError("填写了维度值时必须填写维度名")
        return filters
    raise GenericQueryError("filters 必须是条件")


def _require_filter_list(filters) -> list:
    if filters in (None, "", []):
        return []
    if not isinstance(filters, list):
        raise GenericQueryError("filters 必须是列表")
    return list(filters)


def _selected_monitor_object_ids(monitor_object_id):
    if monitor_object_id in (None, "", []):
        return []
    raw = monitor_object_id if isinstance(monitor_object_id, (list, tuple)) else [monitor_object_id]
    object_ids = []
    for item in raw:
        if item in (None, ""):
            continue
        object_id = _existing_monitor_object_id(item)
        if object_id is None:
            raise GenericQueryError("监控对象不存在或无权访问", status="forbidden")
        if object_id not in object_ids:
            object_ids.append(object_id)
    if not object_ids:
        raise GenericQueryError("监控对象不存在或无权访问", status="forbidden")
    return object_ids


def _ensure_monitor_object_accessible(object_id, user_info, policies, is_superuser):
    if is_superuser:
        return
    has_policy = policies.filter(monitor_object_id=object_id).exists()
    permission, error = _get_monitor_instance_permission(str(object_id), user_info or {})
    if error:
        raise GenericQueryError(error.get("message") or "无权限", status="forbidden")
    has_instance = bool((permission or {}).get("instance") or (permission or {}).get("team"))
    if not has_policy and not has_instance:
        raise GenericQueryError("监控对象不存在或无权访问", status="forbidden")


def _authorized_instances(user_info, monitor_object_id):
    object_ids = _selected_monitor_object_ids(monitor_object_id)
    if not object_ids:
        raise GenericQueryError("监控对象不能为空")
    _user, _team, _children, scope_ids, is_superuser, scope_error = _get_nats_actor_scope(user_info or {})
    if scope_error:
        raise GenericQueryError(scope_error.get("message") or "无权限", status="forbidden")
    if is_superuser:
        return MonitorInstance.objects.filter(
            monitor_object_id__in=object_ids,
            is_deleted=False,
            monitorinstanceorganization__organization__in=list(scope_ids),
        ).distinct()
    allowed_ids = []
    for object_id in object_ids:
        permission, error = _get_monitor_instance_permission(str(object_id), user_info or {})
        if error:
            raise GenericQueryError(error.get("message") or "无权限", status="forbidden")
        if not (permission or {}).get("instance") and not (permission or {}).get("team"):
            raise GenericQueryError("无权限", status="forbidden")
        allowed_ids.extend(
            _get_authorized_instance_queryset(permission, scope_ids)
            .filter(monitor_object_id=object_id, is_deleted=False)
            .values_list("id", flat=True)
        )
    return MonitorInstance.objects.filter(id__in=allowed_ids, is_deleted=False).distinct()


@nats_client.register
@_guard("query_monitor_instances")
def query_monitor_instances(
    monitor_object_id=None,
    analysis_mode=None,
    status=None,
    instance_ids=None,
    group_by=None,
    page=None,
    page_size=None,
    user_info=None,
    **kwargs,
):
    if kwargs.get("order_by") not in (None, "") or kwargs.get("order_dir") not in (None, ""):
        raise GenericQueryError("不支持排序")
    del kwargs
    if group_by not in (None, ""):
        raise GenericQueryError("当前查询不支持分组")
    queryset = _authorized_instances(user_info, monitor_object_id)
    data = query_instances(
        queryset,
        analysis_mode=analysis_mode,
        status=status,
        instance_ids=instance_ids,
        group_by=group_by,
        page=page,
        page_size=page_size,
        locale=(user_info or {}).get("locale"),
    )
    return _ok(data)


@nats_client.register
@_guard("query_monitor_instance_counts")
def query_monitor_instance_counts(
    monitor_object_id=None,
    monitor_object_type_ids=None,
    status=None,
    user_info=None,
    **kwargs,
):
    if kwargs.get("page") not in (None, "") or kwargs.get("page_size") not in (None, ""):
        raise GenericQueryError("计数不支持分页")
    if kwargs.get("order_by") not in (None, "") or kwargs.get("order_dir") not in (None, ""):
        raise GenericQueryError("计数不支持排序")
    if kwargs.get("instance_ids") not in (None, "", []):
        raise GenericQueryError("计数不支持实例范围")
    del kwargs
    type_ids = _distribution_type_ids(monitor_object_type_ids)
    object_ids = _selected_monitor_object_ids(monitor_object_id)
    if object_ids and type_ids:
        mismatched = MonitorObject.objects.filter(id__in=object_ids).exclude(type_id__in=type_ids).exists()
        if mismatched:
            raise GenericQueryError("对象不属于所选分类")
    if object_ids:
        queryset = _authorized_instances(user_info, object_ids)
    else:
        queryset, _is_superuser, _scope_ids = _open_distribution_instances(user_info, type_ids)
    return _ok(query_instance_counts(queryset, status=status))


def _scoped_monitor_instances(user_info, monitor_object_id, monitor_object_type_ids):
    type_ids = _distribution_type_ids(monitor_object_type_ids)
    object_ids = _selected_monitor_object_ids(monitor_object_id)
    if object_ids and type_ids:
        mismatched = MonitorObject.objects.filter(id__in=object_ids).exclude(type_id__in=type_ids).exists()
        if mismatched:
            raise GenericQueryError("对象不属于所选分类")
    if object_ids:
        return _authorized_instances(user_info, object_ids)
    queryset, _is_superuser, _scope_ids = _open_distribution_instances(user_info, type_ids)
    return queryset


def _named_instances(queryset, instance_ids):
    if instance_ids in (None, "", []):
        return queryset
    requested = _id_list(instance_ids)
    if not requested:
        return queryset
    found = {str(item) for item in queryset.filter(id__in=requested).values_list("id", flat=True)}
    missing = [item for item in requested if item not in found]
    if missing:
        raise GenericQueryError("监控实例不存在或无权访问", status="forbidden")
    return queryset.filter(id__in=requested)


def _reject_count_controls(kwargs):
    if kwargs.get("page") not in (None, "") or kwargs.get("page_size") not in (None, ""):
        raise GenericQueryError("计数不支持分页")
    if kwargs.get("order_by") not in (None, "") or kwargs.get("order_dir") not in (None, ""):
        raise GenericQueryError("计数不支持排序")


@nats_client.register
@_guard("query_monitor_collection")
def query_monitor_collection(
    monitor_object_id=None,
    monitor_object_type_ids=None,
    status=None,
    report_status=None,
    collect_status=None,
    collect_mode=None,
    order_by=None,
    order_dir=None,
    page=None,
    page_size=None,
    user_info=None,
    **kwargs,
):
    del kwargs
    queryset = _apply_instance_status(
        _scoped_monitor_instances(user_info, monitor_object_id, monitor_object_type_ids),
        status,
    )
    instances = list(queryset.select_related("monitor_object", "monitor_object__type").distinct())
    return _ok(
        query_collection_rows(
            instances,
            report_status=report_status,
            collect_status=collect_status,
            collect_mode=collect_mode,
            order_by=order_by,
            order_dir=order_dir,
            page=page,
            page_size=page_size,
            locale=(user_info or {}).get("locale"),
        )
    )


# 全量排序会连续读取 VictoriaMetrics。留在唯一的 NATS 同步线程上会堵住其他画布。
query_monitor_collection._nats_thread_sensitive = False


@nats_client.register
@_guard("query_monitor_collection_counts")
def query_monitor_collection_counts(
    monitor_object_id=None,
    monitor_object_type_ids=None,
    status=None,
    report_status=None,
    collect_status=None,
    collect_mode=None,
    user_info=None,
    **kwargs,
):
    _reject_count_controls(kwargs)
    del kwargs
    queryset = _apply_instance_status(
        _scoped_monitor_instances(user_info, monitor_object_id, monitor_object_type_ids),
        status,
    )
    instances = list(queryset.select_related("monitor_object", "monitor_object__type").distinct())
    rows = query_collection_rows(
        instances,
        report_status=report_status,
        collect_status=collect_status,
        collect_mode=collect_mode,
        locale=(user_info or {}).get("locale"),
        bounded=False,
    )
    return _ok([{"instance_count": len(rows)}])


query_monitor_collection_counts._nats_thread_sensitive = False


@nats_client.register
@_guard("query_interface_current")
def query_interface_current(
    monitor_object_id=None,
    monitor_object_type_ids=None,
    instance_ids=None,
    interface_match=None,
    order_by=None,
    order_dir=None,
    page=None,
    page_size=None,
    user_info=None,
    **kwargs,
):
    del kwargs
    queryset = _named_instances(
        _scoped_monitor_instances(user_info, monitor_object_id, monitor_object_type_ids),
        instance_ids,
    )
    instances = list(queryset.select_related("monitor_object").distinct())
    return _ok(
        query_interface_current_rows(
            instances,
            interface_match=interface_match,
            order_by=order_by,
            order_dir=order_dir,
            page=page,
            page_size=page_size,
            locale=(user_info or {}).get("locale"),
        )
    )


@nats_client.register
@_guard("query_interface_current_counts")
def query_interface_current_counts(
    monitor_object_id=None,
    monitor_object_type_ids=None,
    instance_ids=None,
    interface_match=None,
    user_info=None,
    **kwargs,
):
    _reject_count_controls(kwargs)
    del kwargs
    queryset = _named_instances(
        _scoped_monitor_instances(user_info, monitor_object_id, monitor_object_type_ids),
        instance_ids,
    )
    instances = list(queryset.select_related("monitor_object").distinct())
    rows = query_interface_current_rows(
        instances,
        interface_match=interface_match,
        locale=(user_info or {}).get("locale"),
        bounded=False,
    )
    return _ok([{"interface_count": len(rows)}])


def _distribution_type_ids(value) -> list[str]:
    if value in (None, "", []):
        return []
    if isinstance(value, str):
        raw = [item.strip() for item in value.split(",") if item.strip()]
    elif isinstance(value, (list, tuple)):
        raw = [str(item).strip() for item in value if str(item).strip()]
    else:
        raise GenericQueryError("分类格式错误")
    type_ids = []
    for item in raw:
        if item not in type_ids:
            type_ids.append(item)
    found = set(MonitorObjectType.objects.filter(id__in=type_ids).values_list("id", flat=True))
    if any(item not in found for item in type_ids):
        raise GenericQueryError("分类不存在")
    return type_ids


def _distribution_page_size(page_size):
    if page_size in (None, ""):
        return None
    message = f"返回条数必须是 1 到 {STAT_GROUP_MAX} 的整数"
    if isinstance(page_size, bool):
        raise GenericQueryError(message)
    try:
        size = int(page_size)
    except (TypeError, ValueError):
        raise GenericQueryError(message)
    if isinstance(page_size, float) and not page_size.is_integer():
        raise GenericQueryError(message)
    if size < 1 or size > STAT_GROUP_MAX:
        raise GenericQueryError(message)
    return size


def _apply_instance_status(queryset, status):
    if status in (None, ""):
        status = "all"
    if status == "all":
        return queryset
    if status == "active":
        return queryset.filter(is_active=True)
    if status == "inactive":
        return queryset.filter(is_active=False)
    raise GenericQueryError("实例状态不受支持")


def _object_count_permission(user_info, object_id):
    permission, error = _get_monitor_instance_permission(str(object_id), user_info or {})
    if error:
        return None
    if not (permission or {}).get("instance") and not (permission or {}).get("team"):
        return None
    return permission


def _open_distribution_instances(user_info, type_ids):
    _user, _team, _children, scope_ids, is_superuser, scope_error = _get_nats_actor_scope(user_info or {})
    if scope_error:
        raise GenericQueryError(scope_error.get("message") or "无权限", status="forbidden")
    queryset = MonitorInstance.objects.filter(
        is_deleted=False,
        monitorinstanceorganization__organization__in=list(scope_ids),
    )
    if type_ids:
        queryset = queryset.filter(monitor_object__type_id__in=type_ids)
    if is_superuser:
        return queryset.distinct(), True, scope_ids
    allowed_ids = []
    for object_id in queryset.values_list("monitor_object_id", flat=True).distinct():
        permission = _object_count_permission(user_info, object_id)
        if permission is None:
            continue
        allowed_ids.extend(
            _get_authorized_instance_queryset(permission, scope_ids)
            .filter(monitor_object_id=object_id, is_deleted=False)
            .values_list("id", flat=True)
        )
    return MonitorInstance.objects.filter(id__in=allowed_ids, is_deleted=False).distinct(), False, scope_ids


def _visible_catalog_object_ids(user_info, object_ids, is_superuser) -> list[int]:
    if is_superuser:
        return list(object_ids)
    return [object_id for object_id in object_ids if _object_count_permission(user_info, object_id) is not None]


@nats_client.register
@_guard("query_monitor_instance_distribution")
def query_monitor_instance_distribution(
    group_by=None,
    monitor_object_type_ids=None,
    monitor_object_ids=None,
    status=None,
    page_size=None,
    user_info=None,
    **kwargs,
):
    if kwargs.get("page") not in (None, ""):
        raise GenericQueryError("分布不支持页码")
    if kwargs.get("order_by") not in (None, "") or kwargs.get("order_dir") not in (None, ""):
        raise GenericQueryError("分布不支持排序参数")
    if kwargs.get("instance_ids") not in (None, "", []):
        raise GenericQueryError("分布不支持实例范围")
    if kwargs.get("analysis_mode") not in (None, ""):
        raise GenericQueryError("分布不支持分析模式")
    del kwargs
    if group_by not in (GROUP_BY_TYPE, GROUP_BY_OBJECT):
        raise GenericQueryError("分布维度必须是分类或对象")
    type_ids = _distribution_type_ids(monitor_object_type_ids)
    object_ids = _selected_monitor_object_ids(monitor_object_ids)
    if object_ids and not type_ids:
        raise GenericQueryError("选择对象时必须先选择分类")
    if object_ids:
        mismatched = MonitorObject.objects.filter(id__in=object_ids).exclude(type_id__in=type_ids).exists()
        if mismatched:
            raise GenericQueryError("对象不属于所选分类")
    limit = _distribution_page_size(page_size)
    if object_ids:
        queryset = _authorized_instances(user_info, object_ids)
        is_superuser = False
    else:
        queryset, is_superuser, _scope_ids = _open_distribution_instances(user_info, type_ids)
    queryset = _apply_instance_status(queryset, status)
    if group_by == GROUP_BY_TYPE:
        zero_type_ids = type_ids or None
        zero_object_ids = None
    elif object_ids:
        zero_type_ids = None
        zero_object_ids = object_ids
    elif type_ids:
        catalog_ids = list(MonitorObject.objects.filter(type_id__in=type_ids).order_by("type__order", "order", "id").values_list("id", flat=True))
        zero_type_ids = None
        zero_object_ids = _visible_catalog_object_ids(user_info, catalog_ids, is_superuser)
    else:
        zero_type_ids = None
        zero_object_ids = None
    rows = query_instance_distribution(
        queryset,
        group_by=group_by,
        zero_type_ids=zero_type_ids,
        zero_object_ids=zero_object_ids,
        locale=(user_info or {}).get("locale"),
        page_size=limit,
    )
    return _ok(rows)


@nats_client.register
@_guard("query_monitor_metric")
def query_monitor_metric(
    monitor_object_id=None,
    metric_id=None,
    instance_ids=None,
    time_range=None,
    step=None,
    aggregation=None,
    filters=None,
    user_info=None,
    **kwargs,
):
    del kwargs
    if metric_id in (None, ""):
        raise GenericQueryError("指标不能为空")
    query_filters = _metric_condition_filters(filters)
    merge_instances = aggregation not in (None, "")
    query_aggregation = str(aggregation).upper() if merge_instances else "AVG"
    query_grouping = GROUPING_INSTANCE if merge_instances else None
    actor, current_team, include_children, scope_ids, is_superuser, scope_error = _get_nats_actor_scope(user_info or {})
    if scope_error:
        raise GenericQueryError(scope_error.get("message") or "无权限", status="forbidden")
    checked = validate_metric_request(
        instance_ids=instance_ids,
        time_range=time_range,
        step=step,
        organization_ids=scope_ids,
    )
    actor = SimpleNamespace(
        username=getattr(actor, "username", ""),
        domain=getattr(actor, "domain", ""),
        is_superuser=bool(is_superuser),
    )
    prepared = AuthorizedMetricQueryService(
        user=actor,
        current_team=current_team,
        include_children=include_children,
        organization_scope=scope_ids,
    ).prepare(
        {
            "monitor_object_id": monitor_object_id,
            "metric_id": metric_id,
            "instance_ids": checked["instance_ids"],
            "start": int(checked["start"].timestamp() * 1000),
            "end": int(checked["end"].timestamp() * 1000),
            "step": checked["step"],
            "aggregation": query_aggregation,
            "filters": query_filters,
            "grouping": query_grouping,
        }
    )
    response = VictoriaMetricsAPI().query_range(
        prepared.query,
        checked["start"].timestamp(),
        checked["end"].timestamp(),
        checked["step"],
    )
    metric = prepared.metric
    unit = getattr(metric, "unit", "") or ""
    labels = metric_instance_labels(prepared.instance_ids)
    for raw_id in checked["instance_ids"]:
        if raw_id in labels:
            continue
        for candidate in _instance_lookup_candidates(raw_id):
            if candidate in labels:
                labels[str(raw_id)] = labels[candidate]
                break
    identity_keys = _metric_instance_id_keys(metric) if metric is not None else []
    data = build_metric_result(
        response=response,
        unit=unit,
        requested_ids=checked["instance_ids"],
        instance_names=labels,
        identity_keys=identity_keys,
    )
    return _ok(data)


def _reject_retired_alert_args(kwargs) -> None:
    if kwargs.get("instance_id") not in (None, "", []):
        raise GenericQueryError("当前查询不支持该实例参数")
    if str(kwargs.get("analysis_mode") or "").strip():
        raise GenericQueryError("当前查询不支持该参数")
    if kwargs.get("group_by") not in (None, ""):
        raise GenericQueryError("当前查询不支持分组")


def _scoped_monitor_alerts(
    user_info,
    monitor_object_id,
    instance_ids,
    *,
    skip_unknown_instances=False,
    monitor_object_type_ids=None,
):
    _user, _team, _children, scope_ids, is_superuser, scope_error = _get_nats_actor_scope(user_info or {})
    if scope_error:
        raise GenericQueryError(scope_error.get("message") or "无权限", status="forbidden")
    policies, policy_error = _get_nats_accessible_policy_queryset(user_info or {})
    if policy_error:
        raise GenericQueryError(policy_error.get("message") or "无权限", status="forbidden")
    alerts = _filter_nats_visible_alerts(MonitorAlert.objects.all(), scope_ids, policies)
    type_ids = _distribution_type_ids(monitor_object_type_ids)
    object_ids = []
    if monitor_object_id not in (None, "", []):
        object_ids = _selected_monitor_object_ids(monitor_object_id)
        if type_ids:
            mismatched = MonitorObject.objects.filter(id__in=object_ids).exclude(type_id__in=type_ids).exists()
            if mismatched:
                raise GenericQueryError("对象不属于所选分类")
        for object_id in object_ids:
            _ensure_monitor_object_accessible(object_id, user_info, policies, is_superuser)
        alerts = alerts.filter(policy_id__in=MonitorPolicy.objects.filter(monitor_object_id__in=object_ids).values("id"))
    elif type_ids:
        alerts = alerts.filter(policy_id__in=MonitorPolicy.objects.filter(monitor_object__type_id__in=type_ids).values("id"))
    requested_ids = _id_list(instance_ids)
    if requested_ids:
        selected_ids = _resolve_requested_alert_instances(
            user_info,
            requested_ids,
            object_ids,
            skip_unknown_instances=skip_unknown_instances,
        )
        if selected_ids:
            alerts = alerts.filter(monitor_instance_id__in=selected_ids)
        else:
            alerts = alerts.none()
        return alerts, selected_ids
    return alerts, requested_ids


def _resolve_requested_alert_instances(user_info, requested_ids, object_ids, *, skip_unknown_instances):
    candidates = []
    seen = set()
    for item in requested_ids:
        for candidate in _instance_lookup_candidates(item):
            if candidate not in seen:
                seen.add(candidate)
                candidates.append(candidate)
    authorized, error = _get_nats_accessible_instance_queryset(user_info or {}, instance_ids=candidates)
    if error:
        raise GenericQueryError(error.get("message") or "无权限", status="forbidden")
    scoped = authorized.filter(monitor_object_id__in=object_ids) if object_ids else authorized
    found = {str(item) for item in scoped.values_list("id", flat=True)}
    resolved = []
    for item in requested_ids:
        match = next((candidate for candidate in _instance_lookup_candidates(item) if candidate in found), None)
        if match and match not in resolved:
            resolved.append(match)
    if skip_unknown_instances:
        return resolved
    missing = []
    foreign = []
    authorized_ids = {str(item) for item in authorized.values_list("id", flat=True)}
    for item in requested_ids:
        match = next((candidate for candidate in _instance_lookup_candidates(item) if candidate in authorized_ids), None)
        if match is None:
            missing.append(item)
        elif object_ids and match not in found:
            foreign.append(item)
    if missing:
        raise GenericQueryError("实例不存在、已删除或无权访问: " + ", ".join(missing), status="forbidden")
    if foreign:
        raise GenericQueryError("实例不属于所选监控对象: " + ", ".join(foreign))
    return resolved


@nats_client.register
@_guard("query_monitor_alerts")
def query_monitor_alerts(
    monitor_object_id=None,
    monitor_object_type_ids=None,
    instance_ids=None,
    level=None,
    status=None,
    alert_type=None,
    time_field=None,
    time_range=None,
    order_by=None,
    order_dir=None,
    page=None,
    page_size=None,
    user_info=None,
    **kwargs,
):
    _reject_retired_alert_args(kwargs)
    del kwargs
    alerts, selected_ids = _scoped_monitor_alerts(
        user_info,
        monitor_object_id,
        instance_ids,
        monitor_object_type_ids=monitor_object_type_ids,
    )
    data = query_alert_details(
        alerts,
        level=level,
        status=status,
        alert_type=alert_type,
        instance_ids=selected_ids,
        time_field=time_field,
        time_range=time_range,
        order_by=order_by,
        order_dir=order_dir,
        page=page,
        page_size=page_size,
        locale=(user_info or {}).get("locale"),
    )
    return _ok(data)


@nats_client.register
@_guard("query_monitor_alert_counts")
def query_monitor_alert_counts(
    monitor_object_id=None,
    monitor_object_type_ids=None,
    instance_ids=None,
    level=None,
    status=None,
    alert_type=None,
    time_field=None,
    time_range=None,
    user_info=None,
    **kwargs,
):
    _reject_retired_alert_args(kwargs)
    if kwargs.get("page") not in (None, "") or kwargs.get("page_size") not in (None, ""):
        raise GenericQueryError("计数不支持分页")
    if kwargs.get("order_by") not in (None, "") or kwargs.get("order_dir") not in (None, ""):
        raise GenericQueryError("计数不支持排序")
    del kwargs
    alerts, selected_ids = _scoped_monitor_alerts(
        user_info,
        monitor_object_id,
        instance_ids,
        monitor_object_type_ids=monitor_object_type_ids,
    )
    data = query_alert_counts(
        alerts,
        level=level,
        status=status,
        alert_type=alert_type,
        instance_ids=selected_ids,
        time_field=time_field,
        time_range=time_range,
    )
    return _ok(data)


@nats_client.register
@_guard("query_monitor_alert_distribution")
def query_monitor_alert_distribution(
    group_by=None,
    monitor_object_id=None,
    monitor_object_type_ids=None,
    instance_ids=None,
    level=None,
    status=None,
    alert_type=None,
    time_field=None,
    time_range=None,
    user_info=None,
    **kwargs,
):
    _reject_retired_alert_args(kwargs)
    if kwargs.get("page") not in (None, "") or kwargs.get("page_size") not in (None, ""):
        raise GenericQueryError("分布不支持分页")
    if kwargs.get("order_by") not in (None, "") or kwargs.get("order_dir") not in (None, ""):
        raise GenericQueryError("分布不支持排序")
    del kwargs
    selected_types = _distribution_type_ids(monitor_object_type_ids)
    selected_objects = _selected_monitor_object_ids(monitor_object_id)
    alerts, selected_ids = _scoped_monitor_alerts(
        user_info,
        monitor_object_id,
        instance_ids,
        skip_unknown_instances=True,
        monitor_object_type_ids=selected_types,
    )
    data = query_alert_distribution(
        alerts,
        group_by=group_by,
        level=level,
        status=status,
        alert_type=alert_type,
        instance_ids=selected_ids,
        time_field=time_field,
        time_range=time_range,
        locale=(user_info or {}).get("locale"),
        selected_object_ids=selected_objects,
        selected_type_ids=selected_types,
    )
    return _ok(data)


@nats_client.register
@_guard("query_cmdb_alert_distribution")
def query_cmdb_alert_distribution(
    uuids=None,
    group_by=None,
    level=None,
    status=None,
    alert_type=None,
    time_field=None,
    time_range=None,
    user_info=None,
    **kwargs,
):
    from apps.monitor.services.cmdb_alert_distribution import fetch_cmdb_monitor_mappings, normalize_cmdb_uuids, select_mapped_monitor_ids

    _reject_retired_alert_args(kwargs)
    if kwargs.get("page") not in (None, "") or kwargs.get("page_size") not in (None, ""):
        raise GenericQueryError("分布不支持分页")
    if kwargs.get("order_by") not in (None, "") or kwargs.get("order_dir") not in (None, ""):
        raise GenericQueryError("分布不支持排序")
    if kwargs.get("monitor_object_id") not in (None, "", []):
        raise GenericQueryError("当前查询不接收监控对象，请只传实例标识")
    if kwargs.get("instance_ids") not in (None, "", []):
        raise GenericQueryError("请传实例标识，不要传监控实例")
    del kwargs
    uuid_list = normalize_cmdb_uuids(uuids)
    if not _filled(group_by):
        raise GenericQueryError("请选择按什么分布")
    if group_by not in ALERT_DISTRIBUTION_FIELDS:
        raise GenericQueryError("分布字段不受支持")
    mapped_ids = select_mapped_monitor_ids(uuid_list, fetch_cmdb_monitor_mappings(uuid_list, user_info))
    if not mapped_ids:
        return _ok([])
    alerts, selected_ids = _scoped_monitor_alerts(
        user_info,
        None,
        mapped_ids,
        skip_unknown_instances=True,
    )
    data = query_alert_distribution(
        alerts,
        group_by=group_by,
        level=level,
        status=status,
        alert_type=alert_type,
        instance_ids=selected_ids,
        time_field=time_field,
        time_range=time_range,
        locale=(user_info or {}).get("locale"),
        include_object_identity=True,
    )
    return _ok(data)
