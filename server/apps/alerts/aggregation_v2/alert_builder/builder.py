# -- coding: utf-8 --
"""
告警构建器

从聚合结果构建 Alert 对象
"""
import uuid
from typing import List, Dict, Any, Tuple
from django.db import transaction, IntegrityError
import pandas as pd

from apps.alerts.models import Alert, Event, Level, OperatorLog
from apps.alerts.constants import AlertStatus, LevelType, LogAction, LogTargetType
from apps.alerts.aggregation_v2.utils.template import format_alert_message
from apps.core.logger import alert_logger as logger
from django.db.models import QuerySet


class AlertBuilder:
    """告警构建器"""

    # 类级别缓存
    _level_priority = None
    _level_priority_map = None

    @classmethod
    def set_level(cls):
        """从数据库加载级别优先级配置"""
        instances = Level.objects.filter(level_type=LevelType.EVENT, level_id__lt=3).order_by("level_id")
        cls._level_priority = list(instances.values_list("level_id", flat=True))
        cls._level_priority_map = {level.level_name: level.level_id for level in instances}

    @classmethod
    def get_level_priority(cls) -> List[int]:
        """获取级别优先级列表（懒加载）"""
        if cls._level_priority is None:
            cls.set_level()
        return cls._level_priority

    @classmethod
    def get_level_priority_map(cls) -> Dict[str, int]:
        """获取级别优先级映射（懒加载）"""
        if cls._level_priority_map is None:
            cls.set_level()
        return cls._level_priority_map

    @classmethod
    def build_from_aggregation_result(
            cls,
            result_df: pd.DataFrame,
            correlation_rule,
            window_type: str = 'fixed'
    ) -> Tuple[List[Alert], List[Alert]]:
        """
        从聚合结果构建告警
        
        Args:
            result_df: 聚合结果 DataFrame，包含以下列：
                - fingerprint: 事件指纹
                - event_ids: 事件ID列表（JSON字符串或列表）
                - event_count: 事件数量
                - first_event_time: 首次事件时间
                - last_event_time: 最后事件时间
                - max_level: 最高级别
                - 其他聚合字段...
            correlation_rule: 关联规则对象
            window_type: 窗口类型
            
        Returns:
            (created_alerts, updated_alerts): 创建和更新的告警列表
        """
        if result_df.empty:
            return [], []

        created_alerts = []
        updated_alerts = []

        logger.info(f"开始构建告警: {len(result_df)} 个聚合窗口")
        logger.debug(f"聚合结果列: {list(result_df.columns)}")

        for idx, row in result_df.iterrows():
            try:
                fingerprint = row['fingerprint']
                event_ids = row["event_ids"].tolist()
                # event_ids = cls._parse_event_ids(row.get('event_ids', []))
                logger.debug(
                    f"窗口 {idx}: fingerprint={fingerprint}, event_ids类型={type(row.get('event_ids'))}, 数量={len(event_ids) if event_ids else 0}")

                if not event_ids:
                    logger.warning(f"窗口 {idx} 没有事件ID，跳过")
                    continue

                # 获取事件实例
                events = Event.objects.filter(event_id__in=event_ids).order_by('received_at')

                if not events.exists():
                    logger.warning(f"指纹 {fingerprint} 的事件不存在，跳过")
                    continue

                # 构建告警数据
                alert_data = cls._build_alert_data(
                    row=row,
                    events=events,
                    correlation_rule=correlation_rule,
                    fingerprint=fingerprint
                )

                # 创建或更新告警
                alert, is_created = cls._create_or_update_alert(
                    alert_data=alert_data,
                    events=events,
                    fingerprint=fingerprint
                )

                if alert:
                    if is_created:
                        created_alerts.append(alert)
                    else:
                        updated_alerts.append(alert)

            except Exception as e:
                logger.error(f"构建告警失败 (窗口 {idx}): {e}", exc_info=True)
                continue

        logger.info(
            f"告警构建完成: 创建 {len(created_alerts)} 个，"
            f"更新 {len(updated_alerts)} 个"
        )

        cls.bulk_add_operator_log(created_alerts)

        return created_alerts, updated_alerts

    @staticmethod
    def _parse_event_ids(event_ids_value: Any) -> List[str]:
        """解析事件ID列表"""
        if isinstance(event_ids_value, str):
            # JSON 字符串或逗号分隔
            import json
            try:
                return json.loads(event_ids_value)
            except (json.JSONDecodeError, ValueError):
                return [eid.strip() for eid in event_ids_value.split(',') if eid.strip()]
        elif isinstance(event_ids_value, list):
            return event_ids_value
        else:
            return []

    @classmethod
    def _build_alert_data(
            cls,
            row: pd.Series,
            events: QuerySet[Event],
            correlation_rule,
            fingerprint: str
    ) -> Dict[str, Any]:
        """构建告警数据字典"""
        # 获取基础事件（第一个事件）
        base_event = events.first()

        # 获取聚合规则
        aggregation_rule = correlation_rule.aggregation_rules.first()

        # 格式化标题和内容
        event_data = {
            'item': base_event.item,
            'resource_id': base_event.resource_id,
            'resource_name': base_event.resource_name,
            'resource_type': base_event.resource_type,
            'title': base_event.title,
            'description': base_event.description,
            'value': getattr(base_event, 'value', None),
            'level': base_event.level,
        }

        title, content = format_alert_message(
            rule={},
            event_data=event_data
        )

        # 确定告警级别
        level = cls._determine_alert_level(events, row)

        # 构建告警数据
        alert_data = {
            'alert_id': f"ALERT-{uuid.uuid4().hex.upper()}",
            'level': str(level),
            'title': title,
            'content': content,
            'item': base_event.item,
            'resource_id': base_event.resource_id,
            'resource_name': base_event.resource_name,
            'resource_type': base_event.resource_type,
            'first_event_time': row.get('first_event_time', events.first().received_at),
            'last_event_time': row.get('last_event_time', events.last().received_at),
            'source_name': base_event.source.name if base_event.source else None,
            'fingerprint': fingerprint,
            'rule_id': aggregation_rule.rule_id if aggregation_rule else None,
            'status': AlertStatus.UNASSIGNED,
        }

        return alert_data

    @classmethod
    def _determine_alert_level(
            cls,
            events: 'QuerySet[Event]',
            row: pd.Series
    ) -> int:
        """
        确定告警级别
        
        优先使用聚合结果中的 max_level，否则从事件中计算
        使用最低级别（数字最大，对应 level_max=False）
        """
        # 优先使用聚合结果
        if 'max_level' in row and pd.notna(row['max_level']):
            return int(row['max_level'])

        # 从事件中获取最低级别（数字最大）- 对应旧代码的 level_max=False
        event_levels = list(events.values_list('level', flat=True))
        if event_levels:
            return cls.get_min_level(event_levels)  # 使用 get_min_level 而不是 get_max_level

        # 默认级别
        level_priority = cls.get_level_priority()
        return level_priority[-1] if level_priority else 5

    @classmethod
    def get_max_level(cls, event_levels: List[int]) -> int:
        """
        获取最高级别（数字最小）
        
        对应 AlertProcessor.get_max_level
        """
        logger.debug(f"Processing event levels: {event_levels}")
        event_levels = [int(level) for level in event_levels]
        highest_level = min(event_levels)

        # 验证级别是否有效
        level_priority = cls.get_level_priority()
        if highest_level not in level_priority:
            highest_level = level_priority[-1] if level_priority else 5

        return int(highest_level)

    @classmethod
    def get_min_level(cls, event_levels: List[int]) -> int:
        """
        获取最低级别（数字最大）
        
        对应 AlertProcessor.get_min_level
        """
        logger.debug(f"Processing event levels: {event_levels}")
        event_levels = [int(level) for level in event_levels]
        low_level = max(event_levels)

        # 验证级别是否有效
        level_priority = cls.get_level_priority()
        if low_level not in level_priority:
            low_level = level_priority[-1] if level_priority else 5

        return int(low_level)

    @classmethod
    def _create_or_update_alert(
            cls,
            alert_data: Dict[str, Any],
            events: 'QuerySet[Event]',
            fingerprint: str
    ) -> Tuple[Alert, bool]:
        """
        创建或更新告警
        
        Returns:
            (alert, is_created): 告警对象和是否新建的标志
        """
        with transaction.atomic():
            try:
                # 查找活跃的告警（带锁）
                existing_alert = Alert.objects.select_for_update().filter(
                    fingerprint=fingerprint,
                    status__in=AlertStatus.ACTIVATE_STATUS
                ).first()

                if existing_alert:
                    # 更新现有告警
                    return cls._update_existing_alert(
                        alert=existing_alert,
                        alert_data=alert_data,
                        events=events
                    ), False
                else:
                    # 创建新告警
                    return cls._create_new_alert(
                        alert_data=alert_data,
                        events=events
                    ), True

            except IntegrityError:
                # 并发冲突，重新查询
                logger.warning(f"告警创建冲突，重新查询: {fingerprint}")
                existing_alert = Alert.objects.filter(
                    fingerprint=fingerprint,
                    status__in=AlertStatus.ACTIVATE_STATUS
                ).first()

                if existing_alert:
                    existing_alert.events.add(*events)
                    logger.info(f"并发冲突解决，更新告警: {fingerprint}")
                    return existing_alert, False

                raise

    @classmethod
    def _create_new_alert(
            cls,
            alert_data: Dict[str, Any],
            events: 'QuerySet[Event]'
    ) -> Alert:
        """创建新告警"""
        # 创建告警对象
        alert = Alert.objects.create(**alert_data)

        # 批量关联事件
        through_model = Alert.events.through
        through_values = [
            through_model(alert_id=alert.id, event_id=event.id)
            for event in events
        ]
        through_model.objects.bulk_create(through_values)

        logger.info(
            f"创建新告警: {alert.alert_id}, "
            f"fingerprint={alert.fingerprint}, "
            f"events={events.count()}"
        )

        return alert

    @classmethod
    def _update_existing_alert(
            cls,
            alert: Alert,
            alert_data: Dict[str, Any],
            events: 'QuerySet[Event]'
    ) -> Alert:
        """更新现有告警"""
        # 更新级别（取最低级别，对应旧代码的 get_min_level）
        new_level = int(alert_data['level'])
        current_level = int(alert.level)
        alert.level = str(cls.get_min_level([new_level, current_level]))  # 使用 get_min_level

        # 更新时间
        alert.last_event_time = alert_data.get(
            'last_event_time',
            alert.last_event_time
        )

        # 保存更新
        alert.save(update_fields=['level', 'last_event_time'])

        # 添加新事件
        alert.events.add(*events)

        logger.info(
            f"更新告警: {alert.alert_id}, "
            f"fingerprint={alert.fingerprint}, "
            f"new_events={events.count()}"
        )

        return alert

    @classmethod
    def bulk_build_alerts(
            cls,
            alert_data_list: List[Dict[str, Any]]
    ) -> Tuple[List[str], int]:
        """
        批量构建告警（向后兼容旧接口）
        
        Args:
            alert_data_list: 告警数据列表
            
        Returns:
            (created_alert_ids, updated_count)
        """
        created_ids = []
        updated_count = 0

        for alert_data in alert_data_list:
            try:
                events = alert_data.pop('events')
                fingerprint = alert_data.get('fingerprint')

                alert, is_created = cls._create_or_update_alert(
                    alert_data=alert_data,
                    events=events,
                    fingerprint=fingerprint
                )

                if is_created:
                    created_ids.append(alert.alert_id)
                else:
                    updated_count += 1

            except Exception as e:
                logger.error(f"批量构建告警失败: {e}", exc_info=True)
                continue

        return created_ids, updated_count

    @staticmethod
    def bulk_add_operator_log(alerts: List):
        """
        批量添加告警处理人

        Args:
            alerts: 告警ID列表

        Returns:
            更新的告警数量
        """
        bulk_data = []
        for alert in alerts:
            bulk_data.append(
                OperatorLog(
                    action=LogAction.ADD,
                    target_type=LogTargetType.ALERT,
                    operator="system",
                    operator_object="告警-生成告警",
                    target_id=alert.alert_id,
                    overview=f"生成告警, 告警ID[{alert.alert_id}]",
                )

            )
        OperatorLog.objects.bulk_create(bulk_data)
