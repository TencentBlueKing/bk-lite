# -- coding: utf-8 --
# @File: base.py
# @Time: 2025/5/13 15:48
# @Author: windyzhao
import datetime
import uuid
from abc import ABC, abstractmethod
from typing import Dict, Any, List

from django.utils import timezone

from apps.alerts.common.shield import execute_shield_check_for_events
from apps.alerts.constants import LevelType
from apps.alerts.init_constants import INIT_ALERT_ENRICH
from apps.alerts.models import AlertSource, Event, Level, SystemSetting
from apps.alerts.common.source_adapter import logger
from apps.alerts.utils.util import split_list
from apps.rpc.cmdb import CMDB


class AlertSourceAdapter(ABC):
    """告警源适配器基类"""

    def __init__(self, alert_source: AlertSource, secret: str = None, events: List = []):
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
            Level.objects.filter(level_type=LevelType.EVENT).order_by("level_id").values_list(
                "level_id", flat=True)
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
                _value = float(_value) if _value and isinstance(_value, str) and _value.isdigit() else _value

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

    def add_base_fields(self, event: Event, alert: Dict[str, Any]):
        """添加基础字段"""
        event.source = self.alert_source
        event.raw_data = alert
        event.event_id = f"EVENT-{uuid.uuid4().hex}"

    @staticmethod
    def bulk_save_events(events: List[Event]):
        """批量保存事件"""
        if events:
            bulk_create_events = split_list(events, 100)
            for event_batch in bulk_create_events:
                Event.objects.bulk_create(event_batch, ignore_conflicts=True)  # 跳过唯一性约束
            logger.info(f"Bulk saved {len(events)} events.")
            return bulk_create_events

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
            dt = datetime.datetime.fromtimestamp(int(timestamp) / 1000 if len(timestamp) == 13 else int(timestamp))
            # 转为 aware datetime（带时区）
            return timezone.make_aware(dt, timezone.get_current_timezone())
        except Exception as e:
            logger.error(f"Failed to convert timestamp {timestamp} to datetime: {e}")
            return timezone.now()

    @staticmethod
    def event_operator(events_list):
        """
        event的自动屏蔽
        """
        for event_list in events_list:
            try:
                execute_shield_check_for_events([i.event_id for i in event_list])
            except Exception as err:
                import traceback
                logger.error(f"Shield check failed for events:{traceback.format_exc()}")

    def main(self, events=None):
        """使适配器实例可调用"""
        if not events:
            events = self.events
        bulk_events = self.create_events(events)
        self.event_operator(bulk_events)


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
            raise ValueError(f"No adapter found for source type: {alert_source.source_type}")
        return adapter_class

    @classmethod
    def get_supported_types(cls) -> List[str]:
        """获取支持的告警源类型"""
        return list(cls._adapters.keys())
