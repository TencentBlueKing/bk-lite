import uuid
from celery.app import shared_task
from datetime import datetime, timezone, timedelta
from django.db.models import F

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.constants import LEVEL_WEIGHT, THRESHOLD, NO_DATA
from apps.monitor.models import MonitorPolicy, MonitorInstanceOrganization, MonitorAlert, MonitorEvent, MonitorInstance, \
    Metric, MonitorEventRawData, MonitorAlertMetricSnapshot
from apps.monitor.tasks.task_utils.metric_query import format_to_vm_filter
from apps.monitor.tasks.task_utils.policy_calculate import vm_to_dataframe, calculate_alerts
from apps.monitor.utils.system_mgmt_api import SystemMgmtUtils
from apps.monitor.utils.victoriametrics_api import VictoriaMetricsAPI
from apps.core.logger import celery_logger as logger


@shared_task
def scan_policy_task(policy_id):
    """扫描监控策略"""
    logger.info(f"start to update monitor instance grouping rule, [{policy_id}]")

    policy_obj = MonitorPolicy.objects.filter(id=policy_id).select_related("monitor_object").first()
    if not policy_obj:
        raise BaseAppException(f"No MonitorPolicy found with id {policy_id}")

    if policy_obj.enable:
        if not policy_obj.last_run_time:
            policy_obj.last_run_time = datetime.now(timezone.utc)
        policy_obj.last_run_time = datetime.fromtimestamp(policy_obj.last_run_time.timestamp() + period_to_seconds(policy_obj.period), tz=timezone.utc)

        # 如果最后执行时间大于当前时间，将最后执行时间设置为当前时间
        if policy_obj.last_run_time > datetime.now(timezone.utc):
            policy_obj.last_run_time = datetime.now(timezone.utc)
        policy_obj.save()
        MonitorPolicyScan(policy_obj).run()                        # 执行监控策略

    logger.info(f"end to update monitor instance grouping rule, [{policy_id}]")


def _sum(metric_query, start, end, step, group_by):
    query = f"sum({metric_query}) by ({group_by})"
    metrics = VictoriaMetricsAPI().query_range(query, start, end, step)
    return metrics


def _avg(metric_query, start, end, step, group_by):
    query = f"avg({metric_query}) by ({group_by})"
    metrics = VictoriaMetricsAPI().query_range(query, start, end, step)
    return metrics


def _max(metric_query, start, end, step, group_by):
    query = f"max({metric_query}) by ({group_by})"
    metrics = VictoriaMetricsAPI().query_range(query, start, end, step)
    return metrics


def _min(metric_query, start, end, step, group_by):
    query = f"min({metric_query}) by ({group_by})"
    metrics = VictoriaMetricsAPI().query_range(query, start, end, step)
    return metrics


def _count(metric_query, start, end, step, group_by):
    query = f"count({metric_query}) by ({group_by})"
    metrics = VictoriaMetricsAPI().query_range(query, start, end, step)
    return metrics


# def last_over_time(metric_query, start, end, step, group_by):
#     query = f"any(last_over_time({metric_query})) by ({group_by})"
#     metrics = VictoriaMetricsAPI().query_range(query, start, end, step)
#     return metrics

def last_over_time(metric_query, start, end, step, group_by):
    query = f"any(last_over_time({metric_query})) by ({group_by})"
    metrics = VictoriaMetricsAPI().query(query, step, end)
    for data in metrics.get("data", {}).get("result", []):
        data["values"] = [data["value"]]
    return metrics


def max_over_time(metric_query, start, end, step, group_by):
    query = f"any(max_over_time({metric_query})) by ({group_by})"
    metrics = VictoriaMetricsAPI().query_range(query, start, end, step)
    return metrics


def min_over_time(metric_query, start, end, step, group_by):
    query = f"any(min_over_time({metric_query})) by ({group_by})"
    metrics = VictoriaMetricsAPI().query_range(query, start, end, step)
    return metrics


def avg_over_time(metric_query, start, end, step, group_by):
    query = f"any(avg_over_time({metric_query})) by ({group_by})"
    metrics = VictoriaMetricsAPI().query_range(query, start, end, step)
    return metrics


def sum_over_time(metric_query, start, end, step, group_by):
    query = f"any(sum_over_time({metric_query})) by ({group_by})"
    metrics = VictoriaMetricsAPI().query_range(query, start, end, step)
    return metrics


def period_to_seconds(period):
    """周期转换为秒"""
    if not period:
        raise BaseAppException("policy period is empty")
    if period["type"] == "min":
        return period["value"] * 60
    elif period["type"] == "hour":
        return period["value"] * 3600
    elif period["type"] == "day":
        return period["value"] * 86400
    else:
        raise BaseAppException(f"invalid period type: {period['type']}")


METHOD = {
    "sum": _sum,
    "avg": _avg,
    "max": _max,
    "min": _min,
    "count": _count,
    "max_over_time": max_over_time,
    "min_over_time": min_over_time,
    "avg_over_time": avg_over_time,
    "sum_over_time": sum_over_time,
    "last_over_time": last_over_time,
}


class MonitorPolicyScan:
    def __init__(self, policy):
        self.policy = policy
        self.instances_map = self.instances_map()
        self.active_alerts = self.get_active_alerts()
        self.instance_id_keys = None
        self.metric = None

    def get_active_alerts(self):
        """获取策略的活动告警"""
        qs = MonitorAlert.objects.filter(policy_id=self.policy.id, status="new")
        # 如果设置了实例范围，只查询实例范围内的告警
        if self.policy.source:
            qs = qs.filter(monitor_instance_id__in=self.instances_map.keys())
        return qs

    def instances_map(self):
        """获取策略适用的实例"""
        if not self.policy.source:
            return {}
        source_type, source_values = self.policy.source["type"], self.policy.source["values"]
        if source_type == "instance":
            instance_list = source_values
        elif source_type == "organization":
            instance_list = list(MonitorInstanceOrganization.objects.filter(monitor_instance__monitor_object_id=self.policy.monitor_object_id, organization__in=source_values).values_list(
                "monitor_instance_id", flat=True
            ))
        else:
            instance_list = []
        objs = MonitorInstance.objects.filter(monitor_object_id=self.policy.monitor_object_id, id__in=instance_list, is_deleted=False)
        return {i.id: i.name for i in objs}

    def for_mat_period(self, period, points=1):
        """格式化周期"""
        if not period:
            raise BaseAppException("policy period is empty")
        if period["type"] == "min":
            return f'{int(period["value"]/points)}{"m"}'
        elif period["type"] == "hour":
            return f'{int(period["value"]/points)}{"h"}'
        elif period["type"] == "day":
            return f'{int(period["value"]/points)}{"d"}'
        else:
            raise BaseAppException(f"invalid period type: {period['type']}")

    def format_pmq(self):
        """格式化PMQ"""

        query_condition = self.policy.query_condition
        _type = query_condition.get("type")
        if _type == "pmq":
            return query_condition.get("query")
        else:
            query = self.metric.query
            # 纬度条件
            _filter = query_condition.get("filter", [])
            vm_filter_str = format_to_vm_filter(_filter)
            vm_filter_str = f"{vm_filter_str}" if vm_filter_str else ""
            # 去掉label尾部多余的逗号
            if vm_filter_str.endswith(","):
                vm_filter_str = vm_filter_str[:-1]
            query = query.replace("__$labels__", vm_filter_str)
            return query

    def query_aggregration_metrics(self, period, points=1):
        """查询指标"""
        end_timestamp = int(self.policy.last_run_time.timestamp())
        period_seconds = period_to_seconds(period)
        start_timestamp = end_timestamp - period_seconds

        query = self.format_pmq()

        step = self.for_mat_period(period, points)
        method = METHOD.get(self.policy.algorithm)
        if not method:
            raise BaseAppException("invalid algorithm method")
        group_by = ",".join(self.instance_id_keys)
        return method(query, start_timestamp, end_timestamp, step, group_by)

    def set_monitor_obj_instance_key(self):
        """获取监控对象实例key"""
        if self.policy.query_condition.get("type") == "pmq":
            if self.policy.collect_type == "trap":
                self.instance_id_keys = ["source"]
                return
            self.instance_id_keys = self.policy.query_condition.get("instance_id_keys", ["instance_id"])
        else:
            self.metric = Metric.objects.filter(id=self.policy.query_condition["metric_id"]).first()
            if not self.metric:
                raise BaseAppException(f"metric does not exist [{self.policy.query_condition['metric_id']}]")

            self.instance_id_keys = self.metric.instance_id_keys

    def format_aggregration_metrics(self, metrics):
        """格式化聚合指标"""
        result = {}
        for metric_info in metrics.get("data", {}).get("result", []):
            instance_id = str(tuple([metric_info["metric"].get(i) for i in self.instance_id_keys]))

            # 过滤不在实例列表中的实例（策略实例范围）
            if self.instances_map and instance_id not in self.instances_map:
                continue
            value = metric_info["values"][-1]
            result[instance_id] = {"value": float(value[1]), "raw_data": metric_info}
        return result

    def alert_event(self):
        """告警事件"""
        vm_data = self.query_aggregration_metrics(self.policy.period)
        df = vm_to_dataframe(vm_data.get("data", {}).get("result", []), self.instance_id_keys)

        # 计算告警
        alert_events, info_events = calculate_alerts(self.policy.alert_name, df, self.policy.threshold)

        # 设置实例范围的需要过滤实例范围外的告警
        if self.policy.source:
            alert_events = [event for event in alert_events if event["instance_id"] in self.instances_map.keys()]
            info_events = [event for event in info_events if event["instance_id"] in self.instances_map.keys()]

        if alert_events:
            logger.info(f"=======alert events: {alert_events}")
            logger.info(f"=======alert events search result: {vm_data}")
            logger.info(f"=======alert events resource scope: {self.instances_map.keys()}")

        return alert_events, info_events

    def no_data_event(self):
        """无数据告警事件"""
        if not self.policy.no_data_period:
            return []

        if not self.policy.source:
            return []

        events = []
        _aggregration_metrics = self.query_aggregration_metrics(self.policy.no_data_period)
        _aggregation_result = self.format_aggregration_metrics(_aggregration_metrics)

        # 计算无数据事件
        for instance_id in self.instances_map.keys():
            if instance_id not in _aggregation_result:
                events.append({
                    "instance_id": instance_id,
                    "value": None,
                    "level": "no_data",
                    "content": "no data",
                })

        if events:
            logger.info(f"-------no data events: {events}")
            logger.info(f"-------no data events search result: {_aggregration_metrics}")
            logger.info(f"-------no data events resource scope: {self.instances_map.keys()}")

        return events

    def recovery_alert(self):
        """告警恢复"""
        if self.policy.recovery_condition <= 0:
            return

        ids = [i.id for i in self.active_alerts if i.alert_type == "alert"]

        MonitorAlert.objects.filter(id__in=ids, info_event_count__gte=self.policy.recovery_condition).update(
            status="recovered", end_event_time=self.policy.last_run_time, operator="system")

    def recovery_no_data_alert(self):
        """无数据告警恢复"""
        if not self.policy.no_data_recovery_period:
            return
        _aggregration_metrics = self.query_aggregration_metrics(self.policy.no_data_recovery_period)
        _aggregation_result = self.format_aggregration_metrics(_aggregration_metrics)
        instance_ids = set(_aggregation_result.keys())
        MonitorAlert.objects.filter(
            policy_id=self.policy.id,
            monitor_instance_id__in=instance_ids,
            alert_type="no_data",
            status="new",
        ).update(status="recovered", end_event_time=self.policy.last_run_time, operator="system")

    def create_events(self, events):
        """创建事件"""
        if not events:
            return []

        create_events = []
        events_with_raw_data = []  # 保存包含原始数据的事件信息

        for event in events:
            event_id = uuid.uuid4().hex
            create_events.append(
                MonitorEvent(
                    id=event_id,
                    policy_id=self.policy.id,
                    monitor_instance_id=event["instance_id"],
                    value=event["value"],
                    level=event["level"],
                    content=event["content"],
                    notice_result=True,
                    event_time=self.policy.last_run_time,
                )
            )
            # 如果有原始数据，保存事件信息以便后续处理
            if event.get("raw_data"):
                events_with_raw_data.append({
                    "original_id": event_id,
                    "raw_data": event["raw_data"],
                    "instance_id": event["instance_id"]
                })

        # 使用 bulk_create 创建事件
        event_objs = MonitorEvent.objects.bulk_create(create_events, batch_size=200)

        # 兼容性处理：如果 bulk_create 没有返回对象（如 MySQL/SQLite），则手动查询
        if not event_objs or not hasattr(event_objs[0], 'id'):
            # 根据策略ID和时间查询刚创建的事件
            event_objs = list(MonitorEvent.objects.filter(
                policy_id=self.policy.id,
                event_time=self.policy.last_run_time
            ).order_by('-created_at')[:len(create_events)])

        # 创建原始数据 - 使用实际的事件对象ID
        if events_with_raw_data and event_objs:
            create_raw_data = []
            # 建立实例ID到事件对象的映射
            event_obj_map = {obj.monitor_instance_id: obj for obj in event_objs}

            for event_info in events_with_raw_data:
                # 根据实例ID找到对应的事件对象
                event_obj = event_obj_map.get(event_info["instance_id"])
                if event_obj:
                    create_raw_data.append(
                        MonitorEventRawData(
                            event_id=event_obj.id,  # 使用实际的事件ID
                            data=event_info["raw_data"],
                        )
                    )

            if create_raw_data:
                MonitorEventRawData.objects.bulk_create(create_raw_data, batch_size=100)

        return event_objs

    def send_notice(self, event_obj):
        """ 发送通知 """
        title = f"告警通知：{self.policy.name}"
        content = f"告警内容：{event_obj.content}"
        result = []

        try:
            send_result = SystemMgmtUtils.send_msg_with_channel(
                self.policy.notice_type_id, title, content, self.policy.notice_users
            )
            logger.info(f"send notice success: {send_result}")
        except Exception as e:
            logger.error(f"send notice failed: {e}")

        return result

    def notice(self, event_objs):
        """通知"""
        for event in event_objs:
            # 非异常事件不通知
            if event.level == "info":
                continue
            if event.level == "no_data":
                # 无数据告警通知为开启，不进行通知
                if self.policy.no_data_alert <= 0:
                    continue
            notice_results = self.send_notice(event)
            event.notice_result = notice_results
        # 批量更新通知结果
        MonitorEvent.objects.bulk_update(event_objs, ["notice_result"], batch_size=200)

    def handle_alert_events(self, event_objs):
        """处理告警事件"""
        new_alert_events, old_alert_events = [], []
        instance_ids = {event.monitor_instance_id for event in self.active_alerts}
        for event_obj in event_objs:
            if event_obj.monitor_instance_id in instance_ids:
                old_alert_events.append(event_obj)
            else:
                new_alert_events.append(event_obj)

        self.update_alert(old_alert_events)
        new_alerts = self.create_alert(new_alert_events)
        return new_alerts


    def update_alert(self, event_objs):
        event_map = {event.monitor_instance_id: event for event in event_objs}
        alert_level_updates = []
        for alert in self.active_alerts:
            event_obj = event_map.get(alert.monitor_instance_id)
            if not event_obj or event_obj.level == "no_data":
                continue
            # 告警等级升级
            if LEVEL_WEIGHT.get(event_obj.level) > LEVEL_WEIGHT.get(alert.level):
                alert.level = event_obj.level
                alert.value = event_obj.value
                alert.content = event_obj.content
                alert_level_updates.append(alert)
        MonitorAlert.objects.bulk_update(alert_level_updates, ["level", "value", "content"], batch_size=200)

    def create_alert(self, event_objs):
        """告警生成处理"""
        if not event_objs:
            return []

        create_alerts = []
        for event_obj in event_objs:
            if event_obj.level != "no_data":
                alert_type = "alert"
                level = event_obj.level
                value = event_obj.value
                content = event_obj.content
            else:
                alert_type = "no_data"
                level = self.policy.no_data_level
                value = None
                content = "no data"
            create_alerts.append(
                MonitorAlert(
                    policy_id=self.policy.id,
                    monitor_instance_id=event_obj.monitor_instance_id,
                    monitor_instance_name=self.instances_map.get(event_obj.monitor_instance_id) or event_obj.monitor_instance_id,
                    alert_type=alert_type,
                    level=level,
                    value=value,
                    content=content,
                    status="new",
                    start_event_time=event_obj.event_time,
                    operator="",
                ))

        # 使用 bulk_create 创建告警
        new_alerts = MonitorAlert.objects.bulk_create(create_alerts, batch_size=200)

        # 兼容性处理：如果 bulk_create 没有返回对象（如 MySQL/SQLite），则手动查询
        if not new_alerts or not hasattr(new_alerts[0], 'id'):
            # 根据事件对象的实例ID和时间范围查询刚创建的告警
            instance_ids = [event_obj.monitor_instance_id for event_obj in event_objs]
            new_alerts = list(MonitorAlert.objects.filter(
                policy_id=self.policy.id,
                monitor_instance_id__in=instance_ids,
                start_event_time=self.policy.last_run_time,
                status="new"
            ).order_by('id'))

        return new_alerts

    def count_events(self, alert_events, info_events):
        """计数事件"""
        alerts_map = {i.monitor_instance_id : i.id for i in self.active_alerts if i.alert_type == "alert"}
        info_alerts = {alerts_map[event["instance_id"]] for event in info_events if event["instance_id"] in alerts_map}
        alert_alerts = {alerts_map[event["instance_id"]] for event in alert_events if event["instance_id"] in alerts_map}
        self.add_count_alert_event(info_alerts)
        self.clear_count_alert_event(alert_alerts)

    def clear_count_alert_event(self, ids):
        """清除计数告警事件"""
        MonitorAlert.objects.filter(id__in=list(ids)).update(info_event_count=0)

    def add_count_alert_event(self, ids):
        """添加计数告警事件"""
        MonitorAlert.objects.filter(id__in=list(ids)).update(info_event_count=F("info_event_count") + 1)

    def query_raw_metrics(self, period, points=1):
        """查询原始指标数据 - 不进行聚合"""
        end_timestamp = int(self.policy.last_run_time.timestamp())
        period_seconds = period_to_seconds(period)
        start_timestamp = end_timestamp - period_seconds

        query = self.format_pmq()
        step = self.for_mat_period(period, points)

        # 直接查询原始数据，不使用聚合函数
        raw_metrics = VictoriaMetricsAPI().query_range(query, start_timestamp, end_timestamp, step)
        return raw_metrics

    def create_metric_snapshots_for_active_alerts(self, info_events=None, event_objs=None, new_alerts=None):
        """为活跃告警创建指标快照 - 直接使用事件的原始数据"""
        # 合并现有活跃告警和新创建的告警
        all_active_alerts = list(self.active_alerts)
        if new_alerts:
            all_active_alerts.extend(new_alerts)

        if not all_active_alerts:
            return

        # 构建实例ID到原始数据的映射
        instance_raw_data_map = {}

        # 从event_objs中获取raw_data（通过MonitorEventRawData关联）
        if event_objs:
            # 批量查询这些事件的原始数据
            event_ids = [event_obj.id for event_obj in event_objs]
            raw_data_objs = MonitorEventRawData.objects.filter(event_id__in=event_ids).select_related('event')

            # 建立实例ID到原始数据的映射
            for raw_data_obj in raw_data_objs:
                instance_id = raw_data_obj.event.monitor_instance_id
                instance_raw_data_map[instance_id] = raw_data_obj.data

        if info_events:
            for event in info_events:
                instance_id = event["instance_id"]
                if event.get("raw_data") and instance_id not in instance_raw_data_map:
                    instance_raw_data_map[instance_id] = event["raw_data"]

        # 建立实例ID到事件对象的映射
        event_map = {}
        if event_objs:
            for event_obj in event_objs:
                event_map[event_obj.monitor_instance_id] = event_obj

        create_snapshots = []

        # 为每个活跃告警记录快照
        for alert in all_active_alerts:
            instance_id = alert.monitor_instance_id

            # 获取对应的事件对象（如果有的话）
            related_event = event_map.get(instance_id)

            # 获取原始数据，优先使用当前周期的数据
            raw_data = instance_raw_data_map.get(instance_id, {})

            # 如果没有当前周期的数据，查询兜底数据（用于历史活跃告警）
            if not raw_data:
                fallback_data = self.query_raw_metrics(self.policy.period)
                for metric_info in fallback_data.get("data", {}).get("result", []):
                    metric_instance_id = str(tuple([metric_info["metric"].get(i) for i in self.instance_id_keys]))
                    if metric_instance_id == instance_id:
                        raw_data = metric_info
                        break

            create_snapshots.append(
                MonitorAlertMetricSnapshot(
                    alert_id=alert.id,
                    event=related_event,  # 关联对应的事件对象
                    policy_id=self.policy.id,
                    monitor_instance_id=instance_id,
                    snapshot_time=self.policy.last_run_time,
                    raw_data=[raw_data] if raw_data else [],  # 转换为列表格式
                )
            )

        if create_snapshots:
            MonitorAlertMetricSnapshot.objects.bulk_create(create_snapshots, batch_size=200)

    def create_pre_alert_snapshots(self, new_alerts):
        """为新产生的告警创建告警前的快照数据"""
        if not new_alerts:
            return

        # 计算前一个周期的时间点
        period_seconds = period_to_seconds(self.policy.period)
        pre_alert_time = datetime.fromtimestamp(
            self.policy.last_run_time.timestamp() - period_seconds,
            tz=timezone.utc
        )

        # 检查时间合理性，避免查询过早的数据
        min_time = datetime.now(timezone.utc) - timedelta(days=7)  # 最多往前查7天
        if pre_alert_time < min_time:
            logger.warning(f"Pre-alert time {pre_alert_time} too early, skipping pre-alert snapshots for policy {self.policy.id}")
            return

        # 查询告警前一个周期的原始数据
        end_timestamp = int(pre_alert_time.timestamp())
        start_timestamp = end_timestamp - period_seconds

        query = self.format_pmq()
        step = self.for_mat_period(self.policy.period)
        method = METHOD.get(self.policy.algorithm)
        if not method:
            return

        group_by = ",".join(self.instance_id_keys)

        try:
            pre_alert_metrics = method(query, start_timestamp, end_timestamp, step, group_by)
        except Exception as e:
            logger.error(f"Failed to query pre-alert metrics for policy {self.policy.id}: {e}")
            return

        # 按实例ID分组原始数据，应用实例范围过滤
        # 保持与正常快照相同的数据格式
        pre_alert_data_map = {}
        for metric_info in pre_alert_metrics.get("data", {}).get("result", []):
            instance_id = str(tuple([metric_info["metric"].get(i) for i in self.instance_id_keys]))
            # 应用实例范围过滤
            if self.instances_map and instance_id not in self.instances_map:
                continue
            pre_alert_data_map[instance_id] = metric_info

        create_snapshots = []

        # 为每个新告警创建告警前快照
        for alert in new_alerts:
            instance_id = alert.monitor_instance_id
            raw_data = pre_alert_data_map.get(instance_id, {})

            create_snapshots.append(
                MonitorAlertMetricSnapshot(
                    alert_id=alert.id,
                    event=None,  # 告警前快照不关联具体事件
                    policy_id=self.policy.id,
                    monitor_instance_id=instance_id,
                    snapshot_time=pre_alert_time,  # 使用告警前的时间点
                    raw_data=[raw_data] if raw_data else [],  # 保持与正常快照相同的格式：转换为列表
                )
            )

        if create_snapshots:
            MonitorAlertMetricSnapshot.objects.bulk_create(create_snapshots, batch_size=200)
            logger.info(f"Created {len(create_snapshots)} pre-alert snapshots for policy {self.policy.id}")

    def run(self):
        """运行"""
        # 存在source范围并且没有实例，不进行计算
        if self.policy.source and not self.instances_map:
            return

        self.set_monitor_obj_instance_key()
        event_objs = []  # 初始化事件对象列表
        new_alerts = []  # 初始化新告警列表
        alert_events, info_events, no_data_events = [], [], []  # 初始化事件数据

        if THRESHOLD in self.policy.enable_alerts:
            # 告警事件
            alert_events, info_events = self.alert_event()
            # 正常、异常事件计数
            self.count_events(alert_events, info_events)
            # 告警恢复
            self.recovery_alert()

        if NO_DATA in self.policy.enable_alerts:
            # 无数据事件
            no_data_events = self.no_data_event()
            # 无数据告警恢复
            self.recovery_no_data_alert()

        events = alert_events + no_data_events

        if events:
            # 告警事件记录
            event_objs = self.create_events(events)
            new_alerts = self.handle_alert_events(event_objs)

            # 事件通知
            if self.policy.notice:
                self.notice(event_objs)

        self.create_metric_snapshots_for_active_alerts(
            info_events=info_events,
            event_objs=event_objs,
            new_alerts=new_alerts
        )

        # 创建新告警的告警前快照
        self.create_pre_alert_snapshots(new_alerts)
