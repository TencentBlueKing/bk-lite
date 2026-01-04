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
from apps.monitor.utils.unit_converter import UnitConverter
from apps.core.logger import celery_logger as logger


class MonitorPolicyScan:
    """监控策略扫描执行器"""

    def __init__(self, policy):
        self.policy = policy
        self.instances_map = self._build_instances_map()
        self.active_alerts = self._get_active_alerts()
        self.instance_id_keys = None
        self.metric = None
        # 单位转换配置
        self._unit_conversion_enabled = bool(
            self.policy.metric_unit and 
            self.policy.calculation_unit and 
            self.policy.metric_unit != self.policy.calculation_unit
        )

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

    def query_aggregation_metrics(self, period, points=1):
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

    def _convert_metric_values(self, vm_data):
        """转换指标数值到计算单位

        Args:
            vm_data: VictoriaMetrics返回的数据

        Returns:
            dict: 转换后的数据（如果不需要转换则返回原数据）
        """
        if not self._unit_conversion_enabled:
            return vm_data

        # 检查单位是否可以转换
        if not UnitConverter.is_convertible(self.policy.metric_unit, self.policy.calculation_unit):
            logger.warning(
                f"策略 {self.policy.id}: 单位 '{self.policy.metric_unit}' 和 "
                f"'{self.policy.calculation_unit}' 不属于同一体系，跳过单位转换"
            )
            return vm_data

        try:
            # 遍历所有result，转换values中的数值
            for result in vm_data.get("data", {}).get("result", []):
                if "values" not in result:
                    continue

                # 提取所有数值（跳过时间戳）
                values = [float(v[1]) for v in result["values"]]

                # 进行单位转换
                converted_values = UnitConverter.convert_values(
                    values,
                    self.policy.metric_unit,
                    self.policy.calculation_unit
                )

                # 更新result中的values
                for i, (timestamp, _) in enumerate(result["values"]):
                    result["values"][i] = [timestamp, str(converted_values[i])]

            logger.info(
                f"策略 {self.policy.id}: 成功转换指标单位 "
                f"{self.policy.metric_unit} -> {self.policy.calculation_unit}"
            )

        except Exception as e:
            logger.error(f"策略 {self.policy.id}: 单位转换失败: {e}")

        return vm_data

    def _get_display_unit(self):
        """获取用于展示的单位

        Returns:
            str: 展示单位
        """
        if self._unit_conversion_enabled:
            return UnitConverter.get_display_unit(self.policy.calculation_unit)
        elif self.policy.metric_unit:
            return UnitConverter.get_display_unit(self.policy.metric_unit)
        else:
            return ""

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
        # 查询指标数据
        vm_data = self.query_aggregation_metrics(self.policy.period)
        
        # 应用单位转换
        vm_data = self._convert_metric_values(vm_data)
        
        # 转换为DataFrame
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
        aggregation_metrics = self.query_aggregation_metrics(self.policy.no_data_period)
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
        aggregation_metrics = self.query_aggregation_metrics(
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
        """创建事件 - 支持关联告警外键"""
        if not events:
            return []

        create_events = []
        events_with_raw_data = []  # 保存包含原始数据的事件信息

        for event in events:
            event_id = uuid.uuid4().hex

            # ✅ 获取 alert_id（如果有）
            alert_id = event.get("alert_id")

            create_events.append(
                MonitorEvent(
                    id=event_id,
                    alert_id=alert_id,  # ✅ 关联告警外键
                    policy_id=self.policy.id,
                    monitor_instance_id=event["instance_id"],
                    value=event["value"],
                    level=event["level"],
                    content=event["content"],
                    notice_result=True,
                    event_time=self.policy.last_run_time,
                )
            )
            # 如果有原始数据，保存事件ID和原始数据的映射关系
            if event.get("raw_data"):
                events_with_raw_data.append({
                    "event_id": event_id,
                    "raw_data": event["raw_data"],
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

        # 创建原始数据 - 逐个保存以触发 S3JSONField 的上传逻辑
        if events_with_raw_data:
            # 建立事件ID到事件对象的映射（用于兼容性处理）
            event_obj_map = {obj.id: obj for obj in event_objs}

            raw_data_objects = []
            for event_info in events_with_raw_data:
                event_id = event_info["event_id"]
                # 验证事件是否成功创建
                if event_id in event_obj_map or MonitorEvent.objects.filter(id=event_id).exists():
                    raw_data_objects.append(
                        MonitorEventRawData(
                            event_id=event_id,
                            data=event_info["raw_data"],  # S3JSONField 会在 save() 时自动上传
                        )
                    )

            # 批量创建原始数据记录
            if raw_data_objects:
                for raw_data_obj in raw_data_objects:
                    raw_data_obj.save()  # 逐个保存以触发 S3JSONField 的上传逻辑
                logger.info(f"Created {len(raw_data_objects)} raw data records for policy {self.policy.id}")

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
            # 检查发送结果
            if send_result.get("result") is False:
                logger.error(f"send notice failed for policy {self.policy.name}: {send_result.get('message', 'Unknown error')}")
            else:
                logger.info(f"send notice success for policy {self.policy.name}: {send_result}")
        except Exception as e:
            logger.error(f"send notice exception for policy {self.policy.name}: {e}", exc_info=True)

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
        """为活跃告警创建或更新指标快照 - 合并告警下所有事件的快照数据"""
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

        # 建立实例ID到事件对象的映射（支持多个事件）
        event_map = {}
        if event_objs:
            for event_obj in event_objs:
                instance_id = event_obj.monitor_instance_id
                if instance_id not in event_map:
                    event_map[instance_id] = []
                event_map[instance_id].append(event_obj)

        # 建立新告警的实例ID集合，用于判断是否需要创建告警前快照
        new_alert_instance_ids = {alert.monitor_instance_id for alert in new_alerts} if new_alerts else set()

        # 为每个活跃告警创建或更新快照
        for alert in all_active_alerts:
            instance_id = alert.monitor_instance_id
            is_new_alert = instance_id in new_alert_instance_ids

            # 获取对应的事件对象列表
            related_events = event_map.get(instance_id, [])

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

            # 如果有新的事件数据或者是新告警，需要更新快照
            if related_events or raw_data or is_new_alert:
                self._update_alert_snapshot(alert, related_events, raw_data, self.policy.last_run_time, is_new_alert)

    def _update_alert_snapshot(self, alert, event_objs, raw_data, snapshot_time, is_new_alert=False):
        """更新告警的快照数据

        Args:
            alert: 告警对象
            event_objs: 事件对象列表
            raw_data: 原始指标数据
            snapshot_time: 快照时间
            is_new_alert: 是否为新告警
        """
        # 尝试获取已有的快照记录
        snapshot_obj, created = MonitorAlertMetricSnapshot.objects.get_or_create(
            alert_id=alert.id,
            defaults={
                'policy_id': self.policy.id,
                'monitor_instance_id': alert.monitor_instance_id,
                'snapshots': [],
            }
        )

        # 标记是否有新增快照数据
        has_new_snapshot = False

        # 如果是新告警且是首次创建快照记录，需要先添加告警前快照
        if is_new_alert and created:
            pre_alert_snapshot = self._build_pre_alert_snapshot(alert.monitor_instance_id, snapshot_time)
            if pre_alert_snapshot:
                snapshot_obj.snapshots.append(pre_alert_snapshot)
                has_new_snapshot = True
                logger.info(f"Added pre-alert snapshot for alert {alert.id}, instance {alert.monitor_instance_id}")

        # 如果有事件数据，添加到snapshots列表末尾
        if event_objs:
            for event_obj in event_objs:
                event_snapshot = {
                    'type': 'event',
                    'event_id': event_obj.id,
                    'event_time': event_obj.event_time.isoformat() if event_obj.event_time else None,
                    'snapshot_time': snapshot_time.isoformat(),
                    'raw_data': raw_data if raw_data else {},
                }

                # 检查是否已存在相同事件的快照，避免重复
                existing_event_ids = [
                    s.get('event_id') for s in snapshot_obj.snapshots
                    if s.get('type') == 'event'
                ]
                if event_obj.id not in existing_event_ids:
                    snapshot_obj.snapshots.append(event_snapshot)
                    has_new_snapshot = True
                    logger.debug(f"Added event snapshot for alert {alert.id}, event {event_obj.id}")

        # 只有在真正添加了新快照数据时才保存
        if has_new_snapshot:
            snapshot_obj.save(update_fields=['snapshots', 'updated_at'])
            logger.info(f"Saved snapshot for alert {alert.id}, total snapshots: {len(snapshot_obj.snapshots)}")
        else:
            logger.debug(f"No new snapshot data for alert {alert.id}, skipping save")

    def _build_pre_alert_snapshot(self, instance_id, current_snapshot_time):
        """构建告警前快照数据

        Args:
            instance_id: 实例ID
            current_snapshot_time: 当前快照时间

        Returns:
            dict: 告警前快照数据，如果查询失败或无数据则返回None
        """
        # 计算前一个周期的时间点
        period_seconds = period_to_seconds(self.policy.period)
        pre_alert_time = datetime.fromtimestamp(
            current_snapshot_time.timestamp() - period_seconds,
            tz=timezone.utc
        )

        # 检查时间合理性,避免查询过早的数据(最多往前查7天)
        min_time = datetime.now(timezone.utc) - timedelta(days=7)
        if pre_alert_time < min_time:
            logger.warning(
                f"Pre-alert time {pre_alert_time} too early for policy {self.policy.id}, "
                f"skipping pre-alert snapshot for instance {instance_id}"
            )
            return None

        # 准备查询参数
        end_timestamp = int(pre_alert_time.timestamp())
        start_timestamp = end_timestamp - period_seconds
        query = self.format_pmq()
        step = self.format_period(self.policy.period)
        group_by = ",".join(self.instance_id_keys)

        # 获取聚合方法
        method = METHOD.get(self.policy.algorithm)
        if not method:
            logger.warning(f"Invalid algorithm {self.policy.algorithm} for policy {self.policy.id}")
            return None

        # 查询告警前一个周期的原始数据
        try:
            pre_alert_metrics = method(query, start_timestamp, end_timestamp, step, group_by)
        except Exception as e:
            logger.error(f"Failed to query pre-alert metrics for policy {self.policy.id}: {e}")
            return None

        # 查找对应实例的原始数据
        raw_data = {}
        for metric_info in pre_alert_metrics.get("data", {}).get("result", []):
            metric_instance_id = str(tuple([
                metric_info["metric"].get(key) for key in self.instance_id_keys
            ]))

            # 应用实例范围过滤
            if self.instances_map and metric_instance_id not in self.instances_map:
                continue

            if metric_instance_id == instance_id:
                raw_data = metric_info
                break

        # 只有在查询到有效数据时才返回快照
        if not raw_data:
            logger.warning(
                f"No pre-alert data found for policy {self.policy.id}, instance {instance_id} "
                f"at time {pre_alert_time.isoformat()}"
            )
            return None

        # 构建告警前快照数据
        logger.info(f"Built pre-alert snapshot for policy {self.policy.id}, instance {instance_id}")
        return {
            'type': 'pre_alert',
            'snapshot_time': pre_alert_time.isoformat(),
            'raw_data': raw_data,
        }

    def _execute_step(self, step_name, func, *args, critical=False, **kwargs):
        """执行流程步骤，统一��误处理

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
        """创建事件和告警 - 优化版：先创建告警再创建事件以支持外键关联

        Args:
            events: 事件列表（只包含异常事件，不包含 info 事件）

        Returns:
            tuple: (事件对象列表, 新告警列表)
        """
        if not events:
            return [], []

        # 步骤1: 分类事件（新告警 vs 已有告警）
        new_alert_events = []      # 需要创建新告警的异常事件
        existing_alert_events = [] # 对应已有告警的异常事件

        # 构建活跃告警的实例ID到告警对象的映射（注意：映射到对象，不只是ID）
        active_alerts_map = {
            alert.monitor_instance_id: alert
            for alert in self.active_alerts
        }

        for event in events:
            instance_id = event["instance_id"]

            if instance_id in active_alerts_map:
                # 异常事件 + 已有告警：关联现有告警
                alert = active_alerts_map[instance_id]
                event["alert_id"] = alert.id
                event["_alert_obj"] = alert  # ✅ 保存告警对象，用于后续更新
                existing_alert_events.append(event)
            else:
                # 异常事件 + 无告警：需要创建新告警
                new_alert_events.append(event)

        # 步骤2: 先创建新告警（在创建事件之前）
        new_alerts = []
        if new_alert_events:
            new_alerts = self._create_alerts_from_events(new_alert_events)

            # ✅ 验证告警创建数量
            if len(new_alerts) != len(new_alert_events):
                logger.error(
                    f"Alert creation mismatch: expected {len(new_alert_events)}, "
                    f"got {len(new_alerts)} for policy {self.policy.id}"
                )

            # 建立映射，将告警ID回填到事件数据中
            alert_map = {alert.monitor_instance_id: alert for alert in new_alerts}
            for event in new_alert_events:
                alert = alert_map.get(event["instance_id"])
                if alert:
                    event["alert_id"] = alert.id
                    event["_alert_obj"] = alert  # ✅ 保存告警对象
                else:
                    # ✅ 严格检查：如果没有找到对应告警，记录错误
                    logger.error(
                        f"Failed to get alert for event instance {event['instance_id']} "
                        f"in policy {self.policy.id}"
                    )
                    # 设置为 None，后续会跳过
                    event["alert_id"] = None

        # 步骤3: 创建所有异常事件（现在都应该有 alert_id）
        # ✅ 过滤掉没有 alert_id 的事件（异常情况）
        valid_events = [e for e in (new_alert_events + existing_alert_events) if e.get("alert_id")]

        if len(valid_events) != len(new_alert_events) + len(existing_alert_events):
            logger.warning(
                f"Filtered out {len(new_alert_events) + len(existing_alert_events) - len(valid_events)} "
                f"events without alert_id for policy {self.policy.id}"
            )

        event_objs = self.create_events(valid_events)

        # 步骤4: 更新已有告警的等级和内容（如果新事件级别更高）
        if existing_alert_events:
            self._update_existing_alerts_from_events(existing_alert_events)

        logger.info(
            f"Created events and alerts: "
            f"{len(new_alert_events)} new alerts, "
            f"{len(existing_alert_events)} existing alerts, "
            f"{len(event_objs)} events created"
        )

        return event_objs, new_alerts

    def _create_alerts_from_events(self, events):
        """从事件数据创建告警（不依赖事件对象）

        Args:
            events: 事件数据列表（字典格式）

        Returns:
            list: 创建的告警对象列表
        """
        if not events:
            return []

        create_alerts = []

        for event in events:
            # 根据事件类型确定告警属性
            if event["level"] != "no_data":
                alert_type = "alert"
                level = event["level"]
                value = event["value"]
                content = event["content"]
            else:
                alert_type = "no_data"
                level = self.policy.no_data_level
                value = None
                content = "no data"

            create_alerts.append(
                MonitorAlert(
                    policy_id=self.policy.id,
                    monitor_instance_id=event["instance_id"],
                    monitor_instance_name=self.instances_map.get(
                        event["instance_id"],
                        event["instance_id"]
                    ),
                    alert_type=alert_type,
                    level=level,
                    value=value,
                    content=content,
                    status="new",
                    start_event_time=self.policy.last_run_time,
                    operator="",
                )
            )

        # 批量创建告警
        new_alerts = MonitorAlert.objects.bulk_create(
            create_alerts,
            batch_size=DatabaseConstants.BULK_CREATE_BATCH_SIZE
        )

        # 兼容性处理: 某些数据库的 bulk_create 不返回带 ID 的对象
        if not new_alerts or not hasattr(new_alerts[0], 'id'):
            instance_ids = [event["instance_id"] for event in events]
            new_alerts = list(
                MonitorAlert.objects.filter(
                    policy_id=self.policy.id,
                    monitor_instance_id__in=instance_ids,
                    start_event_time=self.policy.last_run_time,
                    status="new"
                ).order_by('id')
            )

        logger.info(f"Created {len(new_alerts)} new alerts for policy {self.policy.id}")
        return new_alerts

    def _update_existing_alerts_from_events(self, event_data_list):
        """更新已有告警的等级和内容（如果新事件级别更高）

        Args:
            event_data_list: 事件数据列表（包含 _alert_obj 字段）
        """
        if not event_data_list:
            return

        alert_level_updates = []

        # ✅ 直接从事件数据中获取告警对象和事件信息
        for event_data in event_data_list:
            alert = event_data.get("_alert_obj")
            if not alert:
                logger.warning(f"Event data missing _alert_obj: {event_data.get('instance_id')}")
                continue

            # 跳过无数据事件（无数据事件不更新告警级别）
            if event_data.get("level") == "no_data":
                continue

            # 检查是否需要升级告警等级
            event_level = event_data.get("level")
            current_weight = AlertConstants.LEVEL_WEIGHT.get(event_level, 0)
            alert_weight = AlertConstants.LEVEL_WEIGHT.get(alert.level, 0)

            if current_weight > alert_weight:
                alert.level = event_level
                alert.value = event_data.get("value")
                alert.content = event_data.get("content")
                alert_level_updates.append(alert)
                logger.debug(
                    f"Upgrading alert {alert.id} level from {alert.level} to {event_level}"
                )

        # 批量更新告警
        if alert_level_updates:
            MonitorAlert.objects.bulk_update(
                alert_level_updates,
                ["level", "value", "content"],
                batch_size=DatabaseConstants.BULK_UPDATE_BATCH_SIZE
            )
            logger.info(f"Updated {len(alert_level_updates)} alerts with higher severity levels")

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

        # 步骤5: 创建指标快照（独立隔离）- 包含告警前快照和事件快照
        self._execute_step(
            "Create metric snapshots",
            self.create_metric_snapshots_for_active_alerts,
            info_events=info_events,
            event_objs=event_objs,
            new_alerts=new_alerts
        )
