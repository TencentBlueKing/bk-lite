"""监控通用查询 NATS handler。统计在监控模块内完成，不把全量样本交回运营分析。"""

from types import SimpleNamespace

import nats_client
from apps.core.logger import monitor_logger as logger
from apps.monitor.models.monitor_object import MonitorInstance, MonitorObject
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
    empty_aggregation_needs_choice,
)
from apps.monitor.services.generic_query import (
    GenericQueryError,
    _id_list,
    build_metric_result,
    ensure_payload_limit,
    metric_instance_labels,
    query_alerts,
    query_instances,
    validate_metric_request,
)
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


def _reject_unsupported_filters(kwargs: dict) -> None:
    filters = kwargs.get("filters") if isinstance(kwargs, dict) else None
    if filters not in (None, "", []):
        raise GenericQueryError("当前查询不支持 filters")


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


def _authorized_instances(user_info, monitor_object_id: str):
    if not monitor_object_id:
        raise GenericQueryError("监控对象不能为空")
    if not MonitorObject.objects.filter(id=monitor_object_id).exists():
        raise GenericQueryError("监控对象不存在或无权访问", status="forbidden")
    _user, _team, _children, scope_ids, is_superuser, scope_error = _get_nats_actor_scope(user_info or {})
    if scope_error:
        raise GenericQueryError(scope_error.get("message") or "无权限", status="forbidden")
    scoped = MonitorInstance.objects.filter(
        monitor_object_id=monitor_object_id,
        is_deleted=False,
        monitorinstanceorganization__organization__in=list(scope_ids),
    )
    if is_superuser:
        return scoped.distinct()
    permission, error = _get_monitor_instance_permission(str(monitor_object_id), user_info or {})
    if error:
        raise GenericQueryError(error.get("message") or "无权限", status="forbidden")
    if not (permission or {}).get("instance") and not (permission or {}).get("team"):
        raise GenericQueryError("无权限", status="forbidden")
    return _get_authorized_instance_queryset(permission, scope_ids).filter(monitor_object_id=monitor_object_id, is_deleted=False).distinct()


def _filters_present(filters) -> bool:
    if filters in (None, "", {}, []):
        return False
    if isinstance(filters, dict) and set(filters) <= {"logic", "items"} and not (filters.get("items") or []):
        return False
    return True


@nats_client.register
@_guard("query_monitor_instances")
def query_monitor_instances(
    monitor_object_id=None,
    analysis_mode=None,
    status=None,
    filter_field=None,
    filter_op=None,
    filter_value=None,
    filters=None,
    instance_ids=None,
    group_by=None,
    order=None,
    page=None,
    page_size=None,
    user_info=None,
    **kwargs,
):
    _reject_unsupported_filters(kwargs)
    del kwargs
    if group_by not in (None, ""):
        raise GenericQueryError("当前查询不支持分组")
    if filter_field not in (None, "") or filter_op not in (None, "") or filter_value not in (None, "") or _filters_present(filters):
        raise GenericQueryError("当前查询不支持属性过滤")
    queryset = _authorized_instances(user_info, monitor_object_id)
    data = query_instances(
        queryset,
        analysis_mode=analysis_mode or "detail",
        status=status,
        filter_field=filter_field,
        filter_op=filter_op,
        filter_value=filter_value,
        filters=filters,
        instance_ids=instance_ids,
        group_by=group_by,
        order=order,
        page=page,
        page_size=page_size,
        locale=(user_info or {}).get("locale"),
    )
    return _ok(data)


@nats_client.register
@_guard("query_monitor_metric")
def query_monitor_metric(
    monitor_object_id=None,
    metric_id=None,
    instance_ids=None,
    time_range=None,
    step=None,
    analysis_mode=None,
    aggregation=None,
    filters=None,
    user_info=None,
    **kwargs,
):
    _reject_unsupported_filters(kwargs)
    del kwargs
    mode = str(analysis_mode or "series")
    if mode not in {"series", "value", "latest"}:
        raise GenericQueryError("分析方式不受支持")
    if metric_id in (None, ""):
        raise GenericQueryError("指标不能为空")
    if mode == "value" and aggregation in (None, ""):
        raise GenericQueryError("聚合方式不能为空")
    query_filters = _metric_condition_filters(filters)
    checked = validate_metric_request(instance_ids=instance_ids, time_range=time_range, step=step)
    actor, current_team, include_children, scope_ids, is_superuser, scope_error = _get_nats_actor_scope(user_info or {})
    if scope_error:
        raise GenericQueryError(scope_error.get("message") or "无权限", status="forbidden")
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
            "aggregation": str(aggregation).upper() if aggregation else None,
            "filters": query_filters,
            "grouping": GROUPING_INSTANCE,
        }
    )
    if (
        mode in {"series", "latest"}
        and aggregation in (None, "")
        and prepared.metric is not None
        and empty_aggregation_needs_choice(prepared.metric, query_filters)
    ):
        raise GenericQueryError("这个指标在同一时间点可能有多个数，请选择聚合方式，或用维度过滤指定其中某一个。")
    response = VictoriaMetricsAPI().query_range(
        prepared.query,
        checked["start"].timestamp(),
        checked["end"].timestamp(),
        checked["step"],
    )
    metric = prepared.metric
    unit = getattr(metric, "unit", "") or ""
    reported_aggregation = str(aggregation or "")
    if reported_aggregation == "":
        reported_aggregation = "avg"
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
        mode=mode,
        response=response,
        unit=unit,
        aggregation=reported_aggregation,
        requested_ids=checked["instance_ids"],
        instance_names=labels,
        identity_keys=identity_keys,
    )
    return _ok(data)


@nats_client.register
@_guard("query_monitor_alerts")
def query_monitor_alerts(
    monitor_object_id=None,
    analysis_mode=None,
    instance_ids=None,
    level=None,
    status=None,
    alert_type=None,
    time_field=None,
    time_range=None,
    group_by=None,
    order=None,
    page=None,
    page_size=None,
    user_info=None,
    **kwargs,
):
    if _filters_present(kwargs.get("filters")):
        raise GenericQueryError("当前查询不支持条件过滤")
    if kwargs.get("instance_id") not in (None, "", []):
        raise GenericQueryError("当前查询不支持该实例参数")
    del kwargs
    _user, _team, _children, scope_ids, is_superuser, scope_error = _get_nats_actor_scope(user_info or {})
    if scope_error:
        raise GenericQueryError(scope_error.get("message") or "无权限", status="forbidden")
    policies, policy_error = _get_nats_accessible_policy_queryset(user_info or {})
    if policy_error:
        raise GenericQueryError(policy_error.get("message") or "无权限", status="forbidden")
    alerts = _filter_nats_visible_alerts(MonitorAlert.objects.all(), scope_ids, policies)
    object_id = None
    if monitor_object_id not in (None, ""):
        object_id = _existing_monitor_object_id(monitor_object_id)
        if object_id is None:
            raise GenericQueryError("监控对象不存在或无权访问", status="forbidden")
        if not is_superuser:
            has_policy = policies.filter(monitor_object_id=object_id).exists()
            permission, error = _get_monitor_instance_permission(str(object_id), user_info or {})
            if error:
                raise GenericQueryError(error.get("message") or "无权限", status="forbidden")
            has_instance = bool((permission or {}).get("instance") or (permission or {}).get("team"))
            if not has_policy and not has_instance:
                raise GenericQueryError("监控对象不存在或无权访问", status="forbidden")
        alerts = alerts.filter(policy_id__in=MonitorPolicy.objects.filter(monitor_object_id=object_id).values("id"))
    selected_ids = _id_list(instance_ids)
    if selected_ids:
        authorized, error = _get_nats_accessible_instance_queryset(user_info or {}, instance_ids=selected_ids)
        if error:
            raise GenericQueryError(error.get("message") or "无权限", status="forbidden")
        found = {str(item) for item in authorized.values_list("id", flat=True)}
        missing = [item for item in selected_ids if item not in found]
        if missing:
            raise GenericQueryError("实例不存在、已删除或无权访问: " + ", ".join(missing), status="forbidden")
        if object_id is not None:
            foreign = [str(item) for item in authorized.exclude(monitor_object_id=object_id).values_list("id", flat=True) if str(item) in found]
            if foreign:
                raise GenericQueryError("实例不属于所选监控对象: " + ", ".join(foreign))
        alerts = alerts.filter(monitor_instance_id__in=selected_ids)
    data = query_alerts(
        alerts,
        analysis_mode=analysis_mode or "detail",
        level=level,
        status=status,
        alert_type=alert_type,
        instance_ids=selected_ids,
        time_field=time_field,
        time_range=time_range,
        group_by=group_by,
        order=order,
        page=page,
        page_size=page_size,
        locale=(user_info or {}).get("locale"),
    )
    return _ok(data)
