import uuid
from datetime import datetime, timezone, timedelta
from django.db.models import F

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.constants.alert_policy import AlertConstants
from apps.monitor.constants.database import DatabaseConstants
from apps.monitor.models import MonitorInstanceOrganization, MonitorAlert, MonitorEvent, MonitorInstance, Metric, MonitorEventRawData, MonitorAlertMetricSnapshot
from apps.monitor.tasks.utils.metric_query import format_to_vm_filter
from apps.monitor.tasks.utils.policy_calculate import vm_to_dataframe, calculate_alerts
from apps.monitor.tasks.utils.policy_methods import METHOD, period_to_seconds
from apps.monitor.utils.system_mgmt_api import SystemMgmtUtils
from apps.monitor.utils.victoriametrics_api import VictoriaMetricsAPI
from apps.core.logger import celery_logger as logger


class MonitorPolicyScan:
    """监控策略扫描执行器"""

    def __init__(self, policy):
        self.policy = policy
        self.instances_map = self._build_instances_map()
        self.active_alerts = self._get_active_alerts()
        self.instance_id_keys = None
        self.metric = None

    def _get_active_alerts(self):
        """获取策略的活动告警

        Returns:
            QuerySet: 活动告警查询集
        """
        qs = MonitorAlert.objects.filter(policy_id=self.policy.id, status="new")
        if self.policy.source:
            qs = qs.filter(monitor_instance_id__in=self.instances_map.keys())
        return qs

    def _build_instances_map(self):
        """构建策略适用的实例映射

        Returns:
            dict: 实例ID到实例名称的映射 {instance_id: instance_name}
        """
        if not self.policy.source:
            return {}

        source_type = self.policy.source["type"]
        source_values = self.policy.source["values"]

        instance_list = self._get_instance_list_by_source(source_type, source_values)

        instances = MonitorInstance.objects.filter(
            monitor_object_id=self.policy.monitor_object_id,
            id__in=instance_list,
            is_deleted=False
        )
        return {instance.id: instance.name for instance in instances}

    def _get_instance_list_by_source(self, source_type, source_values):
        """根据来源类型获取实例列表

        Args:
            source_type: 来源类型 ('instance' | 'organization')
            source_values: 来源值列表

        Returns:
            list: 实例ID列表
        """
        if source_type == "instance":
            return source_values

        if source_type == "organization":
            return list(
                MonitorInstanceOrganization.objects.filter(
                    monitor_instance__monitor_object_id=self.policy.monitor_object_id,
                    organization__in=source_values
                ).values_list("monitor_instance_id", flat=True)
            )

        return []

    def format_period(self, period, points=1):
        """格式化周期为VictoriaMetrics查询步长格式

        Args:
            period: 周期配置 {"type": "min|hour|day", "value": int}
            points: 数据点数,默认为1

        Returns:
            str: 格式化后的步长字符串,如 "5m", "1h", "1d"

        Raises:
            BaseAppException: 周期为空或类型无效
        """
        if not period:
            raise BaseAppException("policy period is empty")

        period_type = period["type"]
        period_value = int(period["value"] / points)

        period_unit_map = {
            "min": "m",
            "hour": "h",
            "day": "d",
        }

        if period_type not in period_unit_map:
            raise BaseAppException(f"invalid period type: {period_type}")

        return f"{period_value}{period_unit_map[period_type]}"

    def format_pmq(self):
        """格式化PromQL/MetricQL查询语句

        Returns:
            str: 格式化后的查询语句
        """
        query_condition = self.policy.query_condition
        query_type = query_condition.get("type")

        # 如果是PMQ类型,直接返回查询语句
        if query_type == "pmq":
            return query_condition.get("query")

        # 否则基于metric构建查询
        query = self.metric.query
        filter_list = query_condition.get("filter", [])
        vm_filter_str = format_to_vm_filter(filter_list)

        # 清理filter字符串尾部的逗号
        if vm_filter_str and vm_filter_str.endswith(","):
            vm_filter_str = vm_filter_str[:-1]

        # 替换查询模板中的label占位符
        query = query.replace("__$labels__", vm_filter_str or "")
        return query

    def query_aggregration_metrics(self, period, points=1):
        """查询聚合指标数据

        Args:
            period: 周期配置
            points: 数据点数

        Returns:
            dict: VictoriaMetrics返回的指标数据

        Raises:
            BaseAppException: 算法方法无效时抛出
        """
        # 计算查询时间范围
        end_timestamp = int(self.policy.last_run_time.timestamp())
        period_seconds = period_to_seconds(period)
        start_timestamp = end_timestamp - period_seconds

        # 准备查询参数
        query = self.format_pmq()
        step = self.format_period(period, points)
        group_by = ",".join(self.instance_id_keys)

        # 获取聚合方法
        method = METHOD.get(self.policy.algorithm)
        if not method:
            raise BaseAppException(f"invalid algorithm method: {self.policy.algorithm}")

        return method(query, start_timestamp, end_timestamp, step, group_by)

    def set_monitor_obj_instance_key(self):
        """设置监控对象实例标识键

        根据查询条件类型确定实例ID的组成键,用于后续数据聚合分组

        Raises:
            BaseAppException: 当metric不存在时抛出
        """
        query_type = self.policy.query_condition.get("type")

        if query_type == "pmq":
            # PMQ类型: trap采集使用source,其他使用配置的instance_id_keys
            if self.policy.collect_type == "trap":
                self.instance_id_keys = ["source"]
            else:
                self.instance_id_keys = self.policy.query_condition.get("instance_id_keys", ["instance_id"])
            return

        # Metric类型: 从metric配置中获取instance_id_keys
        metric_id = self.policy.query_condition["metric_id"]
        self.metric = Metric.objects.filter(id=metric_id).first()

        if not self.metric:
            raise BaseAppException(f"metric does not exist [{metric_id}]")

        self.instance_id_keys = self.metric.instance_id_keys

    def format_aggregration_metrics(self, metrics):
        """格式化聚合指标数据

        Args:
            metrics: VictoriaMetrics返回的原始指标数据

        Returns:
            dict: 格式化后的指标数据 {instance_id: {"value": float, "raw_data": dict}}
        """
        result = {}

        for metric_info in metrics.get("data", {}).get("result", []):
            # 根据instance_id_keys提取实例ID
            instance_id = str(tuple([
                metric_info["metric"].get(key) for key in self.instance_id_keys
            ]))

            # 应用实例范围过滤
            if self.instances_map and instance_id not in self.instances_map:
                continue

            # 提取最后一个时间点的值
            value = metric_info["values"][-1]
            result[instance_id] = {
                "value": float(value[1]),
                "raw_data": metric_info
            }

        return result

    def alert_event(self):
        """处理告警事件检测

        查询指标数据并计算告警/正常事件

        Returns:
            tuple: (告警事件列表, 正常事件列表)
        """
        # 查询并转换指标数据
        vm_data = self.query_aggregration_metrics(self.policy.period)
        df = vm_to_dataframe(
            vm_data.get("data", {}).get("result", []),
            self.instance_id_keys
        )

        # 计算告警
        alert_events, info_events = calculate_alerts(
            self.policy.alert_name,
            df,
            self.policy.threshold
        )

        # 应用实例范围过滤
        if self.policy.source:
            alert_events = self._filter_events_by_instance_scope(alert_events)
            info_events = self._filter_events_by_instance_scope(info_events)

        # 记录告警日志
        if alert_events:
            self._log_alert_events(alert_events, vm_data)

        return alert_events, info_events

    def _filter_events_by_instance_scope(self, events):
        """根据实例范围过滤事件

        Args:
            events: 事件列表

        Returns:
            list: 过滤后的事件列表
        """
        return [
            event for event in events
            if event["instance_id"] in self.instances_map.keys()
        ]

    def _log_alert_events(self, alert_events, vm_data):
        """记录告警事件日志

        Args:
            alert_events: 告警事件列表
            vm_data: VictoriaMetrics查询结果
        """
        logger.info(f"=======alert events: {alert_events}")
        logger.info(f"=======alert events search result: {vm_data}")
        logger.info(f"=======alert events resource scope: {self.instances_map.keys()}")

    def no_data_event(self):
        """检测无数据告警事件

        检查实例范围内哪些实例在指定周期内没有数据上报

        Returns:
            list: 无数据事件列表
        """
        # 早返回: 未配置无数据周期或无实例范围
        if not self.policy.no_data_period or not self.policy.source:
            return []

        # 查询并格式化指标数据
        aggregation_metrics = self.query_aggregration_metrics(self.policy.no_data_period)
        aggregation_result = self.format_aggregration_metrics(aggregation_metrics)

        # 找出没有数据的实例
        events = self._build_no_data_events(aggregation_result)

        # 记录无数据事件日志
        if events:
            self._log_no_data_events(events, aggregation_metrics)

        return events

    def _build_no_data_events(self, aggregation_result):
        """构建无数据事件列表

        Args:
            aggregation_result: 聚合结果字典

        Returns:
            list: 无数据事件列表
        """
        events = []
        for instance_id in self.instances_map.keys():
            if instance_id not in aggregation_result:
                events.append({
                    "instance_id": instance_id,
                    "value": None,
                    "level": "no_data",
                    "content": "no data",
                })
        return events

    def _log_no_data_events(self, events, aggregation_metrics):
        """记录无数据事件日志

        Args:
            events: 无数据事件列表
            aggregation_metrics: 聚合指标数据
        """
        logger.info(f"-------no data events: {events}")
        logger.info(f"-------no data events search result: {aggregation_metrics}")
        logger.info(f"-------no data events resource scope: {self.instances_map.keys()}")

    def recovery_alert(self):
        """处理告警恢复

        根据恢复条件(连续正常事件次数)判断告警是否可以恢复
        """
        if self.policy.recovery_condition <= 0:
            return

        # 获取所有普通告警ID
        alert_ids = [
            alert.id for alert in self.active_alerts
            if alert.alert_type == "alert"
        ]

        # 批量更新满足恢复条件的告警
        MonitorAlert.objects.filter(
            id__in=alert_ids,
            info_event_count__gte=self.policy.recovery_condition
        ).update(
            status="recovered",
            end_event_time=self.policy.last_run_time,
            operator="system"
        )

    def recovery_no_data_alert(self):
        """处理无数据告警恢复

        当无数据的实例恢复数据上报后,将其告警状态更新为已恢复
        """
        if not self.policy.no_data_recovery_period:
            return

        # 查询恢复周期内的数据
        aggregation_metrics = self.query_aggregration_metrics(
            self.policy.no_data_recovery_period
        )
        aggregation_result = self.format_aggregration_metrics(aggregation_metrics)

        # 提取有数据的实例ID
        instance_ids = set(aggregation_result.keys())

        # 批量更新这些实例的无数据告警为已恢复
        MonitorAlert.objects.filter(
            policy_id=self.policy.id,
            monitor_instance_id__in=instance_ids,
            alert_type="no_data",
            status="new",
        ).update(
            status="recovered",
            end_event_time=self.policy.last_run_time,
            operator="system"
        )

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
        event_objs = MonitorEvent.objects.bulk_create(create_events, batch_size=DatabaseConstants.BULK_CREATE_BATCH_SIZE)

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
                MonitorEventRawData.objects.bulk_create(create_raw_data, batch_size=DatabaseConstants.EVENT_RAW_DATA_BATCH_SIZE)

        return event_objs

    def send_notice(self, event_obj):
        """发送告警通知

        Args:
            event_obj: 事件对象

        Returns:
            list: 发送结果列表(当前实现总是返回空列表)
        """
        title = f"告警通知：{self.policy.name}"
        content = f"告警内容：{event_obj.content}"

        try:
            send_result = SystemMgmtUtils.send_msg_with_channel(
                self.policy.notice_type_id, title, content, self.policy.notice_users
            )
            logger.info(f"send notice success: {send_result}")
        except Exception as e:
            logger.error(f"send notice failed: {e}")

        return []

    def notice(self, event_objs):
        """批量发送事件通知

        Args:
            event_objs: 事件对象列表
        """
        # 收集需要通知的事件
        events_to_notify = []

        for event in event_objs:
            # 跳过info级别事件
            if event.level == "info":
                continue

            # 无数据告警需检查是否开启通知
            if event.level == "no_data" and self.policy.no_data_alert <= 0:
                continue

            events_to_notify.append(event)

        # 发送通知并记录结果
        for event in events_to_notify:
            notice_results = self.send_notice(event)
            event.notice_result = notice_results

        # 批量更新通知结果
        if events_to_notify:
            MonitorEvent.objects.bulk_update(
                events_to_notify,
                ["notice_result"],
                batch_size=DatabaseConstants.BULK_UPDATE_BATCH_SIZE
            )

    def handle_alert_events(self, event_objs):
        """处理告警事件,区分新告警和已存在的告警

        Args:
            event_objs: 事件对象列表

        Returns:
            list: 新创建的告警列表
        """
        new_alert_events = []
        old_alert_events = []

        # 构建活跃告警的实例ID集合
        active_instance_ids = {
            alert.monitor_instance_id for alert in self.active_alerts
        }

        # 分类事件
        for event_obj in event_objs:
            if event_obj.monitor_instance_id in active_instance_ids:
                old_alert_events.append(event_obj)
            else:
                new_alert_events.append(event_obj)

        # 更新已存在的告警
        self.update_alert(old_alert_events)

        # 创建新告警
        new_alerts = self.create_alert(new_alert_events)

        return new_alerts

    def update_alert(self, event_objs):
        """更新已存在的告警(支持告警等级升级)

        Args:
            event_objs: 事件对象列表
        """
        if not event_objs:
            return

        # 建立实例ID到事件的映射
        event_map = {event.monitor_instance_id: event for event in event_objs}
        alert_level_updates = []

        for alert in self.active_alerts:
            event_obj = event_map.get(alert.monitor_instance_id)

            # 跳过无对应事件或无数据事件
            if not event_obj or event_obj.level == "no_data":
                continue

            # 检查是否需要升级告警等级
            current_weight = AlertConstants.LEVEL_WEIGHT.get(event_obj.level, 0)
            alert_weight = AlertConstants.LEVEL_WEIGHT.get(alert.level, 0)

            if current_weight > alert_weight:
                alert.level = event_obj.level
                alert.value = event_obj.value
                alert.content = event_obj.content
                alert_level_updates.append(alert)

        # 批量更新告警
        if alert_level_updates:
            MonitorAlert.objects.bulk_update(
                alert_level_updates,
                ["level", "value", "content"],
                batch_size=DatabaseConstants.BULK_UPDATE_BATCH_SIZE
            )

    def create_alert(self, event_objs):
        """基于事件创建新告警

        Args:
            event_objs: 事件对象列表

        Returns:
            list: 创建的告警对象列表
        """
        if not event_objs:
            return []

        create_alerts = []

        for event_obj in event_objs:
            # 根据事件类型确定告警属性
            alert_params = self._build_alert_params(event_obj)

            create_alerts.append(
                MonitorAlert(
                    policy_id=self.policy.id,
                    monitor_instance_id=event_obj.monitor_instance_id,
                    monitor_instance_name=self.instances_map.get(
                        event_obj.monitor_instance_id,
                        event_obj.monitor_instance_id
                    ),
                    alert_type=alert_params["alert_type"],
                    level=alert_params["level"],
                    value=alert_params["value"],
                    content=alert_params["content"],
                    status="new",
                    start_event_time=event_obj.event_time,
                    operator="",
                )
            )

        # 批量创建告警
        new_alerts = MonitorAlert.objects.bulk_create(
            create_alerts,
            batch_size=DatabaseConstants.BULK_CREATE_BATCH_SIZE
        )

        # 兼容性处理: 某些数据库的bulk_create不返回对象
        if not new_alerts or not hasattr(new_alerts[0], 'id'):
            new_alerts = self._query_created_alerts(event_objs)

        return new_alerts

    def _build_alert_params(self, event_obj):
        """构建告警参数

        Args:
            event_obj: 事件对象

        Returns:
            dict: 告警参数字典
        """
        if event_obj.level != "no_data":
            return {
                "alert_type": "alert",
                "level": event_obj.level,
                "value": event_obj.value,
                "content": event_obj.content,
            }

        return {
            "alert_type": "no_data",
            "level": self.policy.no_data_level,
            "value": None,
            "content": "no data",
        }

    def _query_created_alerts(self, event_objs):
        """查询刚创建的告警对象

        Args:
            event_objs: 事件对象列表

        Returns:
            list: 告警对象列表
        """
        instance_ids = [event_obj.monitor_instance_id for event_obj in event_objs]
        return list(
            MonitorAlert.objects.filter(
                policy_id=self.policy.id,
                monitor_instance_id__in=instance_ids,
                start_event_time=self.policy.last_run_time,
                status="new"
            ).order_by('id')
        )

    def count_events(self, alert_events, info_events):
        """统计告警和正常事件,更新告警计数器

        Args:
            alert_events: 告警事件列表
            info_events: 正常事件列表
        """
        # 构建告警实例ID到告警ID的映射
        alerts_map = {
            alert.monitor_instance_id: alert.id
            for alert in self.active_alerts
            if alert.alert_type == "alert"
        }

        # 提取info事件对应的告警ID
        info_alert_ids = {
            alerts_map[event["instance_id"]]
            for event in info_events
            if event["instance_id"] in alerts_map
        }

        # 提取alert事件对应的告警ID
        alert_alert_ids = {
            alerts_map[event["instance_id"]]
            for event in alert_events
            if event["instance_id"] in alerts_map
        }

        # 正常事件:增加计数
        self._increment_info_count(info_alert_ids)

        # 告警事件:清零计数
        self._clear_info_count(alert_alert_ids)

    def _clear_info_count(self, alert_ids):
        """清零告警的正常事件计数

        Args:
            alert_ids: 告警ID集合
        """
        if not alert_ids:
            return

        MonitorAlert.objects.filter(id__in=list(alert_ids)).update(info_event_count=0)

    def _increment_info_count(self, alert_ids):
        """递增告警的正常事件计数

        Args:
            alert_ids: 告警ID集合
        """
        if not alert_ids:
            return

        MonitorAlert.objects.filter(id__in=list(alert_ids)).update(
            info_event_count=F("info_event_count") + 1
        )

    def query_raw_metrics(self, period, points=1):
        """查询原始指标数据(不进行聚合)

        Args:
            period: 周期配置
            points: 数据点数

        Returns:
            dict: VictoriaMetrics返回的原始指标数据
        """
        # 计算查询时间范围
        end_timestamp = int(self.policy.last_run_time.timestamp())
        period_seconds = period_to_seconds(period)
        start_timestamp = end_timestamp - period_seconds

        # 准备查询参数
        query = self.format_pmq()
        step = self.format_period(period, points)

        # 直接查询原始数据
        raw_metrics = VictoriaMetricsAPI().query_range(
            query, start_timestamp, end_timestamp, step
        )
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
            MonitorAlertMetricSnapshot.objects.bulk_create(create_snapshots, batch_size=DatabaseConstants.BULK_CREATE_BATCH_SIZE)

    def create_pre_alert_snapshots(self, new_alerts):
        """为新产生的告警创建告警前的快照数据

        Args:
            new_alerts: 新创建的告警列表
        """
        if not new_alerts:
            return

        # 计算前一个周期的时间点
        period_seconds = period_to_seconds(self.policy.period)
        pre_alert_time = datetime.fromtimestamp(
            self.policy.last_run_time.timestamp() - period_seconds,
            tz=timezone.utc
        )

        # 检查时间合理性,避免查询过早的数据(最多往前查7天)
        min_time = datetime.now(timezone.utc) - timedelta(days=7)
        if pre_alert_time < min_time:
            logger.warning(
                f"Pre-alert time {pre_alert_time} too early, "
                f"skipping pre-alert snapshots for policy {self.policy.id}"
            )
            return

        # 准备查询参数
        end_timestamp = int(pre_alert_time.timestamp())
        start_timestamp = end_timestamp - period_seconds
        query = self.format_pmq()
        step = self.format_period(self.policy.period)
        group_by = ",".join(self.instance_id_keys)

        # 获取聚合方法
        method = METHOD.get(self.policy.algorithm)
        if not method:
            return

        # 查询告警前一个周期的原始数据
        try:
            pre_alert_metrics = method(query, start_timestamp, end_timestamp, step, group_by)
        except Exception as e:
            logger.error(f"Failed to query pre-alert metrics for policy {self.policy.id}: {e}")
            return

        # 按实例ID分组原始数据,应用实例范围过滤
        pre_alert_data_map = self._build_pre_alert_data_map(pre_alert_metrics)

        # 批量创建告警前快照
        create_snapshots = []
        for alert in new_alerts:
            instance_id = alert.monitor_instance_id
            raw_data = pre_alert_data_map.get(instance_id, {})

            create_snapshots.append(
                MonitorAlertMetricSnapshot(
                    alert_id=alert.id,
                    event=None,  # 告警前快照不关联具体事件
                    policy_id=self.policy.id,
                    monitor_instance_id=instance_id,
                    snapshot_time=pre_alert_time,
                    raw_data=[raw_data] if raw_data else [],
                )
            )

        if create_snapshots:
            MonitorAlertMetricSnapshot.objects.bulk_create(
                create_snapshots,
                batch_size=DatabaseConstants.BULK_CREATE_BATCH_SIZE
            )
            logger.info(f"Created {len(create_snapshots)} pre-alert snapshots for policy {self.policy.id}")

    def _build_pre_alert_data_map(self, pre_alert_metrics):
        """构建告警前数据映射

        Args:
            pre_alert_metrics: 告警前的指标数据

        Returns:
            dict: 实例ID到指标数据的映射
        """
        pre_alert_data_map = {}

        for metric_info in pre_alert_metrics.get("data", {}).get("result", []):
            instance_id = str(tuple([
                metric_info["metric"].get(key) for key in self.instance_id_keys
            ]))

            # 应用实例范围过滤
            if self.instances_map and instance_id not in self.instances_map:
                continue

            pre_alert_data_map[instance_id] = metric_info

        return pre_alert_data_map

    def _execute_step(self, step_name, func, *args, critical=False, **kwargs):
        """执行流程步骤，统一错误处理

        Args:
            step_name: 步骤名称，用于日志记录
            func: 要执行的函数
            *args: 函数参数
            critical: 是否为关键步骤，失败后是否中断流程
            **kwargs: 函数关键字参数

        Returns:
            tuple: (是否成功, 函数执行结果)
                - 成功时返回 (True, result)
                - 失败时返回 (False, None)，如果critical=True则直接抛出异常
        """
        try:
            result = func(*args, **kwargs)
            logger.info(f"{step_name} completed for policy {self.policy.id}")
            return True, result
        except Exception as e:
            logger.error(f"Failed to {step_name.lower()} for policy {self.policy.id}: {e}", exc_info=True)
            if critical:
                raise
            return False, None

    def _process_threshold_alerts(self):
        """处理阈值告警"""
        alert_events, info_events = self.alert_event()
        self.count_events(alert_events, info_events)
        self.recovery_alert()
        return alert_events, info_events

    def _process_no_data_alerts(self):
        """处理无数据告警"""
        no_data_events = self.no_data_event()
        self.recovery_no_data_alert()
        return no_data_events

    def _create_events_and_alerts(self, events):
        """创建事件和告警

        Args:
            events: 事件列表

        Returns:
            tuple: (事件对象列表, 新告警列表)
        """
        event_objs = self.create_events(events)
        new_alerts = []
        if event_objs:
            new_alerts = self.handle_alert_events(event_objs)
        return event_objs, new_alerts

    def run(self):
        """执行监控策略扫描主流程

        流程说明:
        1. 前置检查：实例范围、实例标识键
        2. 处理告警：阈值告警、无数据告警（独立隔离）
        3. 创建记录：事件、告警（关键步骤）
        4. 后续处理：通知、快照（独立隔离）
        """
        # 前置检查：实例范围
        if self.policy.source and not self.instances_map:
            logger.warning(f"Policy {self.policy.id} has source but no instances, skipping scan")
            return

        # 前置检查：实例标识键（关键步骤，失败则抛出异常终止）
        try:
            self._execute_step("Set monitor instance key", self.set_monitor_obj_instance_key, critical=True)
        except Exception:
            return

        # 初始化结果变量
        alert_events, info_events, no_data_events = [], [], []

        # 步骤1: 处理阈值告警（独立隔离）
        if AlertConstants.THRESHOLD in self.policy.enable_alerts:
            success, result = self._execute_step("Process threshold alerts", self._process_threshold_alerts)
            if success and result is not None:
                alert_events, info_events = result
                logger.info(f"Threshold alerts: {len(alert_events)} alerts, {len(info_events)} info events")

        # 步骤2: 处理无数据告警（独立隔离）
        if AlertConstants.NO_DATA in self.policy.enable_alerts:
            success, result = self._execute_step("Process no-data alerts", self._process_no_data_alerts)
            if success and result is not None:
                no_data_events = result
                logger.info(f"No-data alerts: {len(no_data_events)} events")

        # 步骤3: 创建事件和告警（关键步骤）
        events = alert_events + no_data_events
        if not events:
            logger.info(f"No events to process for policy {self.policy.id}")
            return

        success, result = self._execute_step("Create events and alerts", self._create_events_and_alerts, events, critical=True)
        if not success:
            return  # 关键步骤失败，终止流程
        
        event_objs, new_alerts = result
        logger.info(f"Created {len(event_objs)} events and {len(new_alerts)} new alerts")

        # 步骤4: 发送通知（独立隔离）
        if self.policy.notice and event_objs:
            self._execute_step("Send notifications", self.notice, event_objs)

        # 步骤5: 创建指标快照（独立隔离）
        self._execute_step(
            "Create metric snapshots",
            self.create_metric_snapshots_for_active_alerts,
            info_events=info_events,
            event_objs=event_objs,
            new_alerts=new_alerts
        )

        # 步骤6: 创建告警前快照（独立隔离）
        if new_alerts:
            self._execute_step("Create pre-alert snapshots", self.create_pre_alert_snapshots, new_alerts)
