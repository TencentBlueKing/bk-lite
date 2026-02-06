# -- coding: utf-8 --
# @File: base.py
# @Time: 2025/5/13 15:48
# @Author: windyzhao
import datetime
import uuid
import hashlib
from abc import ABC, abstractmethod
from typing import Dict, Any, List

from django.utils import timezone

from apps.alerts.aggregation.recovery.recovery_handler import RecoveryHandler
from apps.alerts.common.shield import execute_shield_check_for_events
from apps.alerts.constants.constants import LevelType, EventAction
from apps.alerts.constants.init_data import INIT_ALERT_ENRICH
from apps.alerts.models.sys_setting import SystemSetting
from apps.alerts.models.models import  Event, Level
from apps.alerts.models.alert_source import  AlertSource
from apps.alerts.common.source_adapter import logger
from apps.alerts.utils.util import split_list
from apps.rpc.cmdb import CMDB


class AlertSourceAdapter(ABC):
    """告警源适配器基类"""

    def __init__(
            self, alert_source: AlertSource, secret: str = None, events: List = []
    ):
        self.alert_source = alert_source
        self.config = alert_source.config
        self.secret = secret
        self.events = events
        self.mapping = self.alert_source.config.get("event_fields_mapping", {})
        self.unique_fields = ["title"]
        self.info_level, self.levels = self.get_event_level()  # 默认级别为最低级别
        self.enable_rich_event = self.enable_enrich()

    @staticmethod
    def enable_enrich():
        """
        是否开启告警丰富
        默认不开启
        """
        instance = SystemSetting.objects.filter(key=INIT_ALERT_ENRICH).first()
        if not instance:
            return False
        return instance.value.get("enable", False)

    @staticmethod
    def get_event_level() -> tuple:
        """获取事件级别"""
        instance = list(
            Level.objects.filter(level_type=LevelType.EVENT)
            .order_by("level_id")
            .values_list("level_id", flat=True)
        )

        return str(max(instance)), [str(i) for i in instance]

    @abstractmethod
    def authenticate(self, *args, **kwargs) -> bool:
        """认证告警源"""
        pass

    @abstractmethod
    def fetch_alerts(self) -> List[Dict[str, Any]]:
        """从告警源获取告警数据"""
        pass

    def mapping_fields_to_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """将告警字段映射到事件字段"""
        result = {}
        for key, field in self.mapping.items():
            _value = event.get(field, None)
            if key in self.unique_fields:
                # 如果是唯一字段但是没有传递 丢弃
                if not _value:
                    return {}
            elif key == "level":
                # 如果是级别字段没有传递默认给 info
                if not _value or _value not in self.levels:
                    _value = self.info_level
            else:
                if not _value and _value != 0:
                    # 去元数据里找
                    label = event.get("labels", {})
                    _value = label.get(field, None)
                    if not _value:
                        # 如果元数据里也没有，直接跳过
                        continue

            if _value and key == "start_time" or key == "end_time":
                _value = self.timestamp_to_datetime(_value)

            if key == "value":
                _value = (
                    float(_value)
                    if _value and isinstance(_value, str) and _value.isdigit()
                    else _value
                )

            result[key] = _value

        self.add_start_time(result)

        return result

    @staticmethod
    def add_start_time(data):
        if "start_time" not in data:
            # 如果没有开始时间，默认使用当前时间
            data["start_time"] = timezone.now()

    def create_events(self, add_events):
        """将原始告警数据转换为Event对象"""
        events = []
        for add_event in add_events:
            try:
                event = self._transform_alert_to_event(add_event)
                self.add_base_fields(event, add_event)
                events.append(event)
            except Exception as e:
                logger.error(f"Failed to transform alert: {add_event}, error: {e}")
        bulk_events = self.bulk_save_events(events)
        return bulk_events

    @staticmethod
    def generate_external_id(item: str, resource_name: str, source_id) -> str:
        components = f"{item or ''}|{resource_name or ''}|{source_id or ''}"
        return hashlib.md5(components.encode("utf-8")).hexdigest()

    def add_base_fields(self, event: Event, alert: Dict[str, Any]):
        """添加基础字段"""

        event.source = self.alert_source
        event.raw_data = alert
        event.event_id = f"EVENT-{uuid.uuid4().hex}"

        if not event.external_id or not str(event.external_id).strip():
            event.external_id = self.generate_external_id(
                event.item, event.resource_name, self.alert_source.source_id
            )
            logger.debug(f"Generated external_id for event: {event.event_id}")

    @staticmethod
    def bulk_save_events(events: List[Event]):
        """
        批量保存事件（性能优化版）
        
        优化点：
        1. 使用 bulk_create 批量入库
        2. 立即查询返回带 pk 的对象（避免后续重复查询）
        3. 保持分批逻辑（每批 100 个）
        
        Returns:
            List[List[Event]]: 分批后的事件列表（带 pk）
        """
        if not events:
            return []

        # 1. 分批保存
        bulk_create_events = split_list(events, 100)
        all_event_ids = []

        for event_batch in bulk_create_events:
            Event.objects.bulk_create(
                event_batch, ignore_conflicts=True
            )
            # 收集所有 event_id 用于后续查询
            all_event_ids.extend([e.event_id for e in event_batch])

        logger.info(f"Bulk saved {len(events)} events.")

        # 2. 优化：立即查询返回带 pk 的对象（1 次查询）
        # 避免后续 event_operator 需要用 event_id 再查一遍
        created_events = Event.objects.filter(event_id__in=all_event_ids)

        # 3. 重新分批返回（保持与原来相同的数据结构）
        created_events_list = list(created_events)
        result = split_list(created_events_list, 100)

        logger.debug(f"Reloaded {len(created_events_list)} events with pk")
        return result

    def rich_event(self, event: dict):
        """告警丰富"""
        if not self.enable_rich_event:
            return
        try:
            self.enrich_event(event)
        except Exception as e:
            logger.error(f"Failed to enrich events: {e}")

    @staticmethod
    def enrich_event(event):
        """
        对单个事件进行丰富处理
        查询cmdb nats获取信息
        """
        params = {}
        resource_type = event.get("resource_type", None)
        if not resource_type:
            return
        params["model_id"] = resource_type
        resource_id = event.get("resource_id", None)
        resource_name = event.get("resource_name", None)
        if resource_id:
            params["_id"] = resource_id
        elif resource_name:
            params["inst_name"] = resource_name
        else:
            return

        try:
            cmdb_instance = CMDB().search_instances(params=params)
            # 将cmdb实例信息添加到事件中
            event["labels"].update(cmdb_instance)
        except Exception as err:
            import traceback

            logger.error(f"CMDB search_instances failed: {traceback.format_exc()}")

    def _transform_alert_to_event(self, add_event: Dict[str, Any]) -> Event:
        """将单个告警数据转换为Event对象"""
        data = self.mapping_fields_to_event(add_event)
        self.rich_event(data)
        event = Event(**data)
        return event

    @staticmethod
    def timestamp_to_datetime(timestamp: str) -> datetime:
        """将时间戳转换为datetime对象"""
        # 先转为 naive datetime timestamp 微妙
        try:
            dt = datetime.datetime.fromtimestamp(
                int(timestamp) / 1000 if len(timestamp) == 13 else int(timestamp)
            )
            # 转为 aware datetime（带时区）
            return timezone.make_aware(dt, timezone.get_current_timezone())
        except Exception as e:
            logger.error(f"Failed to convert timestamp {timestamp} to datetime: {e}")
            return timezone.now()

    @staticmethod
    def get_active_shields():
        """
        获取所有活跃的屏蔽策略（优化：一次性查询，全局复用）
        
        Returns:
            QuerySet 或 None
        """
        try:
            from apps.alerts.models import AlertShield
            shields = AlertShield.objects.filter(is_active=True)
            if shields.exists():
                logger.debug(f"加载了 {shields.count()} 个活跃屏蔽策略")
                return shields
            return None
        except Exception as e:
            logger.error(f"查询活跃屏蔽策略失败: {e}")
            return None

    def event_operator(self, events_list):
        """
        event的自动屏蔽（性能优化版）
        
        Args:
            events_list: 事件批次列表
        """

        # 优化：预先查询活跃屏蔽策略，避免每批次重复查询
        active_shields = self.get_active_shields()

        for event_list in events_list:
            try:
                execute_shield_check_for_events(
                    [i.event_id for i in event_list],
                    active_shields=active_shields
                )
            except Exception as err: # noqa
                import traceback
                logger.error(f"Shield check failed for events:{traceback.format_exc()}")

    def main(self, events=None):
        """使适配器实例可调用"""
        if not events:
            events = self.events
        bulk_events = self.create_events(events)
        if not bulk_events:
            return
        self.event_operator(bulk_events)
        self.handle_recovery_events(bulk_events)

    @staticmethod
    def handle_recovery_events(bulk_events):
        """
        处理恢复事件：将 RECOVERY/CLOSED 事件关联到对应的 Alert
        
        Args:
            bulk_events: 批量创建的事件列表（分批后的列表）
        """

        for event_batch in bulk_events:
            # 过滤出 RECOVERY 和 CLOSED 类型的事件
            recovery_events = [
                e for e in event_batch
                if e.action in [EventAction.RECOVERY, EventAction.CLOSED]
            ]

            if recovery_events:
                try:
                    RecoveryHandler.handle_recovery_events(recovery_events)
                    logger.info(
                        f"处理了 {len(recovery_events)} 个恢复事件 "
                        f"(RECOVERY/CLOSED)"
                    )
                except Exception as err:
                    import traceback
                    logger.error(
                        f"Recovery handler failed: {traceback.format_exc()}"
                    )


class AlertSourceAdapterFactory:
    """告警源适配器工厂"""

    _adapters = {}

    @classmethod
    def register_adapter(cls, source_type: str, adapter_class):
        """注册适配器"""
        cls._adapters[source_type] = adapter_class
        logger.info(f"Adapter registered for source type: {source_type}")

    @classmethod
    def get_adapter(cls, alert_source: AlertSource):
        """获取适配器实例"""
        adapter_class = cls._adapters.get(alert_source.source_type)
        if not adapter_class:
            raise ValueError(
                f"No adapter found for source type: {alert_source.source_type}"
            )
        return adapter_class

    @classmethod
    def get_supported_types(cls) -> List[str]:
        """获取支持的告警源类型"""
        return list(cls._adapters.keys())
