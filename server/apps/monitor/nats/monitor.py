import time
from datetime import datetime

import nats_client
from django.db.models import Q
from apps.core.utils.time_util import format_timestamp

from apps.monitor.models import MonitorObject, Metric, MonitorInstance, MonitorAlert
from apps.monitor.serializers.monitor_object import MonitorObjectSerializer
from apps.monitor.serializers.monitor_metrics import MetricSerializer
from apps.monitor.services.metrics import Metrics
from apps.core.utils.permission_utils import get_permission_rules, permission_filter
from apps.monitor.constants.permission import PermissionConstants
from apps.monitor.utils.victoriametrics_api import VictoriaMetricsAPI
from apps.core.logger import nats_logger as logger


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
            raise ValueError(
                f"{field_name} 时间格式错误，应为 YYYY-MM-DD HH:MM:SS 或时间戳"
            ) from exc
    raise ValueError(f"{field_name} 时间格式错误")


def _normalize_filter_values(value, field_name: str):
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item not in (None, "")]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    raise ValueError(f"{field_name} 必须是字符串或列表")


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

    return {
        str(key): str(value) for key, value in dimensions.items() if value is not None
    }


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


def _build_metric_label_query(
    metric_query: str, instance_ids=None, dimensions=None
) -> str:
    instance_ids = [
        str(instance_id) for instance_id in (instance_ids or []) if instance_id
    ]
    dimensions = dimensions or {}

    label_conditions = []
    if instance_ids:
        instance_filter = "|".join(
            _escape_label_value(instance_id) for instance_id in instance_ids
        )
        label_conditions.append(f'instance_id=~"{instance_filter}"')

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
        merged_labels = (
            f"{existing_labels}, {labels_str}" if existing_labels else labels_str
        )
        return f"{left}{{{merged_labels}}}{suffix}"

    return f"{metric_query}{{{labels_str}}}"


def _get_monitor_instance_permission(monitor_obj_id: str, user_info: dict):
    user = user_info.get("user")
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
    return {
        item.get("id"): item.get("permission", [])
        for item in instance_items
        if isinstance(item, dict) and item.get("id")
    }


@nats_client.register
def monitor_objects(*args, **kwargs):
    """查询监控对象列表"""
    logger.info(
        "=== monitor_objects called , args={}, kwargs={}===".format(args, kwargs)
    )
    queryset = MonitorObject.objects.all().order_by("id")
    serializer = MonitorObjectSerializer(queryset, many=True)
    result = {"result": True, "data": serializer.data, "message": ""}
    return result


@nats_client.register
def monitor_metrics(monitor_obj_id: str, *args, **kwargs):
    """查询指标信息"""
    logger.info(
        "=== monitor_metrics called , monitor_obj_id={}, args={}, kwargs={}===".format(
            monitor_obj_id, args, kwargs
        )
    )
    try:
        monitor_obj = MonitorObject.objects.get(id=monitor_obj_id)
    except MonitorObject.DoesNotExist:
        return {"result": False, "data": [], "message": "监控对象不存在"}

    # 查询监控对象关联的指标
    metrics = Metric.objects.filter(monitor_object=monitor_obj).order_by(
        "metric_group__sort_order", "sort_order"
    )

    serializer = MetricSerializer(metrics, many=True)
    return {"result": True, "data": serializer.data, "message": ""}


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
    instances = qs.filter(
        monitor_object=monitor_obj, is_deleted=False, is_active=True
    ).select_related("monitor_object")

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
            "created_time": instance.created_time.isoformat()
            if hasattr(instance, "created_time") and instance.created_time
            else None,
            "updated_time": instance.updated_time.isoformat()
            if hasattr(instance, "updated_time") and instance.updated_time
            else None,
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
            authorized_qs.filter(
                id__in=instance_ids, monitor_object=monitor_obj, is_deleted=False
            ).values_list("id", flat=True)
        )

        if not authorized_instances:
            return {"result": False, "data": [], "message": "没有权限访问指定的实例"}
        instance_ids = authorized_instances

    query = _build_metric_label_query(
        query, instance_ids=instance_ids, dimensions=dimensions
    )

    try:
        # 执行范围查询
        result = Metrics.get_metrics_range(query, start_time, end_time, step)

        # 数据格式化和权限过滤
        if "data" in result and "result" in result["data"]:
            # 获取所有有权限的实例ID
            authorized_instance_ids = set(
                authorized_qs.filter(
                    monitor_object=monitor_obj, is_deleted=False
                ).values_list("id", flat=True)
            )

            filtered_result = []
            for metric_data in result["data"]["result"]:
                metric_instance_id = metric_data.get("metric", {}).get("instance_id")

                if metric_instance_id:
                    # 只返回有权限的实例数据
                    if metric_instance_id in authorized_instance_ids:
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

    metrics = (
        Metric.objects.filter(monitor_object=monitor_obj)
        .select_related("metric_group")
        .order_by("metric_group__sort_order", "sort_order")
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
                if not (
                    resp.get("status") == "success"
                    and resp.get("data", {}).get("result")
                ):
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
        page_size = _normalize_positive_int(
            query_data.get("page_size", 100), "page_size", default=100
        )
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
        alert_type_values = _normalize_filter_values(
            query_data.get("alert_type"), "alert_type"
        )
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
        filtered_instance_ids = [
            instance for instance in instance_ids if instance in authorized_instance_ids
        ]
        if not filtered_instance_ids:
            return {"result": False, "data": [], "message": "没有权限访问指定的实例"}
        authorized_instance_ids = set(filtered_instance_ids)

    queryset = MonitorAlert.objects.filter(
        monitor_instance_id__in=authorized_instance_ids
    )
    queryset = queryset.filter(
        Q(start_event_time__lte=end_dt)
        | Q(start_event_time__isnull=True, created_at__lte=end_dt)
    )
    queryset = queryset.filter(
        Q(end_event_time__gte=start_dt)
        | Q(end_event_time__isnull=True, updated_at__gte=start_dt)
    )

    if status_values:
        queryset = queryset.filter(status__in=status_values)
    if level_values:
        queryset = queryset.filter(level__in=level_values)
    if alert_type_values:
        queryset = queryset.filter(alert_type__in=alert_type_values)

    items = [
        _build_monitor_alert_segment(alert)
        for alert in queryset.order_by("-start_event_time", "-created_at")
    ]
    return {
        "result": True,
        "data": _paginate_items(items, page, page_size),
        "message": "",
    }


@nats_client.register
def mm_query_range(query: str, time_range: list, step="5m", *args, **kwargs):
    start_time, end_time = time_range
    start_time = format_timestamp(start_time)
    end_time = format_timestamp(end_time)
    resp = VictoriaMetricsAPI().query_range(query, start_time, end_time, step)
    if resp["status"] == "success":
        _result = resp["data"]["result"]
        if _result:
            values = _result[0].get("values", [])
        else:
            values = []
        # 格式转换给单值
        data = []
        for _value in values:
            data.append({"name": _value[0], "value": _value[1]})
    else:
        data = []
    return {"result": True, "data": data, "message": ""}


@nats_client.register
def mm_query(query: str, step="5m", *args, **kwargs):
    resp = VictoriaMetricsAPI().query(query, step)
    if resp["status"] == "success":
        _result = resp["data"]["result"]
        if _result:
            values = _result[0].get("value", [])
        else:
            values = []
            # 格式转换给单值
        data = []
        if values:
            data.append({"name": values[0], "value": values[-1]})
    else:
        data = []
    return {"result": True, "data": data, "message": ""}
