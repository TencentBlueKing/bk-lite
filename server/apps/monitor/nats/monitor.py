import nats_client
from apps.core.utils.time_util import format_time_iso, format_timestamp

from apps.monitor.models import MonitorObject, Metric, MonitorInstance
from apps.monitor.serializers.monitor_object import MonitorObjectSerializer
from apps.monitor.serializers.monitor_metrics import MetricSerializer
from apps.monitor.services.metrics import Metrics
from apps.core.utils.permission_utils import get_permission_rules, permission_filter
from apps.monitor.constants import INSTANCE_MODULE
from apps.monitor.utils.victoriametrics_api import VictoriaMetricsAPI
from apps.core.logger import nats_logger as logger


@nats_client.register
def monitor_objects(*args, **kwargs):
    """查询监控对象列表"""
    logger.info("=== monitor_objects called , args={}, kwargs={}===".format(args, kwargs))
    queryset = MonitorObject.objects.all().order_by('id')
    serializer = MonitorObjectSerializer(queryset, many=True)
    result = {"result": True, "data": serializer.data, "message": ""}
    return result


@nats_client.register
def monitor_metrics(monitor_obj_id: str, *args, **kwargs):
    """查询指标信息"""
    logger.info(
        "=== monitor_metrics called , monitor_obj_id={}, args={}, kwargs={}===".format(monitor_obj_id, args, kwargs))
    try:
        monitor_obj = MonitorObject.objects.get(id=monitor_obj_id)
    except MonitorObject.DoesNotExist:
        return {"result": False, "data": [], "message": "监控对象不存在"}

    # 查询监控对象关联的指标
    metrics = Metric.objects.filter(
        monitor_object=monitor_obj
    ).order_by('metric_group__sort_order', 'sort_order')

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

    # 获取用户在当前组织下的实例权限
    user = user_info.get('user')
    current_team = user_info.get('team')

    if not user or not current_team:
        return {"result": False, "data": [], "message": "缺少用户或组织信息"}

    permission = get_permission_rules(
        user,
        current_team,
        "monitor",
        f"{INSTANCE_MODULE}.{monitor_obj_id}",
    )

    # 使用权限过滤器获取有权限的实例
    qs = permission_filter(
        MonitorInstance,
        permission,
        team_key="monitorinstanceorganization__organization__in",
        id_key="id__in"
    )

    # 过滤指定监控对象的活跃实例
    instances = qs.filter(
        monitor_object=monitor_obj,
        is_deleted=False,
        is_active=True
    ).select_related('monitor_object')

    # 获取实例权限映射
    inst_permission_map = {i["id"]: i["permission"] for i in permission.get("instance", [])}

    # 构建返回数据
    filtered_instances = []
    for instance in instances:
        instance_data = {
            'id': instance.id,
            'name': instance.name,
            'monitor_object_id': instance.monitor_object.id,
            'monitor_object_name': instance.monitor_object.name,
            'interval': instance.interval,
            'is_active': instance.is_active,
            'created_time': instance.created_time.isoformat() if hasattr(instance,
                                                                         'created_time') and instance.created_time else None,
            'updated_time': instance.updated_time.isoformat() if hasattr(instance,
                                                                         'updated_time') and instance.updated_time else None,
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
    required_fields = ['monitor_obj_id', 'metric', 'start', 'end']
    for field in required_fields:
        if field not in query_data:
            return {"result": False, "data": [], "message": f"缺少必要参数: {field}"}

    monitor_obj_id = query_data['monitor_obj_id']
    metric_name = query_data['metric']
    start_time = query_data['start']
    end_time = query_data['end']
    step = query_data.get('step', '5m')
    instance_ids = query_data.get('instance_ids', [])

    user_info = kwargs["user_info"]

    # 获取用户权限
    user = user_info.get('user')
    current_team = user_info.get('team')

    if not user or not current_team:
        return {"result": False, "data": [], "message": "缺少用户或组织信息"}

    try:
        monitor_obj = MonitorObject.objects.get(id=monitor_obj_id)
        metric = Metric.objects.get(
            monitor_object=monitor_obj,
            name=metric_name
        )
    except (MonitorObject.DoesNotExist, Metric.DoesNotExist):
        return {"result": False, "data": [], "message": "监控对象或指标不存在"}

    # 获取用户在当前组织下的实例权限
    permission = get_permission_rules(
        user,
        current_team,
        "monitor",
        f"{INSTANCE_MODULE}.{monitor_obj_id}",
    )

    # 构建查询语句
    query = metric.query
    if not query:
        return {"result": False, "data": [], "message": "指标查询语句为空"}

    # 如果指定了实例ID，需要进行权限验证和过滤
    if instance_ids:
        # 使用权限过滤器验证实例权限
        authorized_qs = permission_filter(
            MonitorInstance,
            permission,
            team_key="monitorinstanceorganization__organization__in",
            id_key="id__in"
        )

        # 获取有权限的实例ID
        authorized_instances = list(
            authorized_qs.filter(
                id__in=instance_ids,
                monitor_object=monitor_obj,
                is_deleted=False
            ).values_list('id', flat=True)
        )

        if not authorized_instances:
            return {"result": False, "data": [], "message": "没有权限访问指定的实例"}

        # 在查询中添加实例过滤条件
        instance_filter = '|'.join(authorized_instances)
        query = f'{query}{{instance_id=~"{instance_filter}"}}'

    try:
        # 执行范围查询
        result = Metrics.get_metrics_range(query, start_time, end_time, step)

        # 数据格式化和权限过滤
        if 'data' in result and 'result' in result['data']:
            # 获取所有有权限的实例ID
            authorized_qs = permission_filter(
                MonitorInstance,
                permission,
                team_key="monitorinstanceorganization__organization__in",
                id_key="id__in"
            )

            authorized_instance_ids = set(
                authorized_qs.filter(
                    monitor_object=monitor_obj,
                    is_deleted=False
                ).values_list('id', flat=True)
            )

            filtered_result = []
            for metric_data in result['data']['result']:
                metric_instance_id = metric_data.get('metric', {}).get('instance_id')

                if metric_instance_id:
                    # 只返回有权限的实例数据
                    if metric_instance_id in authorized_instance_ids:
                        filtered_result.append(metric_data)
                else:
                    # 没有实例ID的指标数据直接返回
                    filtered_result.append(metric_data)

            result['data']['result'] = filtered_result

        return {"result": True, "data": result, "message": ""}

    except Exception as e:
        return {"result": False, "data": [], "message": f"查询指标数据失败: {str(e)}"}


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
