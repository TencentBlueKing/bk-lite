import logging
import uuid

from celery.app import shared_task
from datetime import datetime, timezone

from django.db.models import F
from apps.monitor.constants import LEVEL_WEIGHT
from apps.monitor.models import MonitorPolicy, MonitorInstanceOrganization, MonitorAlert, MonitorEvent, MonitorInstance, \
    Metric, MonitorEventRawData
from apps.monitor.tasks.task_utils.policy_calculate import vm_to_dataframe, calculate_alerts
from apps.monitor.utils.system_mgmt_api import SystemMgmtUtils
from apps.monitor.utils.victoriametrics_api import VictoriaMetricsAPI

logger = logging.getLogger("app")


@shared_task
def scan_policy_task(policy_id):
    """扫描监控策略"""
    logger.info(f"start to update monitor instance grouping rule, [{policy_id}]")

    policy_obj = MonitorPolicy.objects.filter(id=policy_id).select_related("monitor_object").first()
    if not policy_obj:
        raise ValueError(f"No MonitorPolicy found with id {policy_id}")

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


def last_over_time(metric_query, start, end, step, group_by):
    query = f"any(last_over_time({metric_query})) by ({group_by})"
    metrics = VictoriaMetricsAPI().query_range(query, start, end, step)
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
        raise ValueError("policy period is empty")
    if period["type"] == "min":
        return period["value"] * 60
    elif period["type"] == "hour":
        return period["value"] * 3600
    elif period["type"] == "day":
        return period["value"] * 86400
    else:
        raise ValueError(f"invalid period type: {period['type']}")


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

    def format_to_vm_filter(self, conditions):
        """
        将纬度条件格式化为 VictoriaMetrics 的标准语法。

        Args:
            conditions (list): 包含过滤条件的字典列表，每个字典格式为：
                {"name": <纬度名称>, "value": <值>, "method": <运算符>}

        Returns:
            str: 格式化后的 VictoriaMetrics 过滤条件语法。
        """
        vm_filters = []
        for condition in conditions:
            name = condition.get("name")
            value = condition.get("value")
            method = condition.get("method")
            vm_filters.append(f'{name}{method}"{value}"')

        # 使用逗号连接多个条件
        return ",".join(vm_filters)

    def for_mat_period(self, period, points=1):
        """格式化周期"""
        if not period:
            raise ValueError("policy period is empty")
        if period["type"] == "min":
            return f'{int(period["value"]/points)}{"m"}'
        elif period["type"] == "hour":
            return f'{int(period["value"]/points)}{"h"}'
        elif period["type"] == "day":
            return f'{int(period["value"]/points)}{"d"}'
        else:
            raise ValueError(f"invalid period type: {period['type']}")

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
            vm_filter_str = self.format_to_vm_filter(_filter)
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
            raise ValueError("invalid algorithm method")
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
                raise ValueError(f"metric does not exist [{self.policy.query_condition['metric_id']}]")

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
            status="recovered", end_event_time=datetime.now(timezone.utc), operator="system")

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
        ).update(status="recovered", end_event_time=datetime.now(timezone.utc), operator="system")

    def create_events(self, events):
        """创建事件"""
        create_events, create_raw_data = [], []
        for event in events:
            event_id = uuid.uuid4().hex
            if event.get("raw_data"):
                create_raw_data.append(
                    MonitorEventRawData(
                        event_id=event_id,
                        data=event["raw_data"],
                    )
                )
            create_events.append(
                MonitorEvent(
                    id=event_id,
                    policy_id=self.policy.id,
                    monitor_instance_id=event["instance_id"],
                    value=event["value"],
                    level=event["level"],
                    content=event["content"],
                    notice_result=True,
                )
            )

        event_objs = MonitorEvent.objects.bulk_create(create_events, batch_size=200)
        MonitorEventRawData.objects.bulk_create(create_raw_data, batch_size=100)
        return event_objs

    def get_users_email(self, usernames):
        """获取用户邮箱"""
        users = SystemMgmtUtils.get_user_all()
        user_email_map = {user_info["username"]: user_info["email"] for user_info in users if user_info.get("email")}

        return {username: user_email_map.get(username) for username in usernames}

    def send_email(self, event_obj):
        """发送邮件"""
        title = f"告警通知：{self.policy.name}"
        content = f"告警内容：{event_obj.content}"
        result = []
        user_email_map = self.get_users_email(self.policy.notice_users)

        for user, email in user_email_map.items():
            if not email:
                result.append({"user": user, "status": "failed", "error": "email not found"})
                continue
            else:
                result.append({"user": user, "status": "success"})

        try:
            send_result = SystemMgmtUtils.send_msg_with_channel(
                self.policy.notice_type_id, title, content, [email for email in user_email_map.values() if email]
            )
            logger.info(f"send email success: {send_result}")
        except Exception as e:
            logger.error(f"send email failed: {e}")

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
            notice_results = self.send_email(event)
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
        self.create_alert(new_alert_events)


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
                    start_event_time=event_obj.created_at,
                    operator="",
                ))

        MonitorAlert.objects.bulk_create(create_alerts, batch_size=200)

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

    def run(self):
        """运行"""
        # 存在source范围并且没有实例，不进行计算
        if self.policy.source and not self.instances_map:
            return

        self.set_monitor_obj_instance_key()

        # 告警事件
        alert_events, info_events = self.alert_event()

        # 正常、异常事件计数
        self.count_events(alert_events, info_events)

        # 无数据事件
        no_data_events = self.no_data_event()

        # 告警恢复
        self.recovery_alert()

        # 无数据告警恢复
        self.recovery_no_data_alert()

        # 告警事件记录
        event_objs = self.create_events(alert_events + no_data_events)
        self.handle_alert_events(event_objs)

        # 事件通知
        self.notice(event_objs)
