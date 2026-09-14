import json
import uuid
from typing import Any, Dict, List, Optional

from django.utils import timezone

from apps.alerts.aggregation.window.factory import WindowFactory
from apps.alerts.constants.constants import AlertStatus, EventAction, LevelType, SessionStatus
from apps.alerts.enrichment.merge import merge_namespace_payload
from apps.alerts.models.alert_operator import AlarmStrategy
from apps.alerts.models.models import Alert, Event, Level
from apps.alerts.service.monitor_object_snapshot import resolve_monitor_objects
from apps.alerts.service.monitor_sources import collect_push_source_ids
from apps.alerts.utils.enrichment import resolve_data_path
from apps.alerts.utils.permission_scope import normalize_team_ids
from apps.core.logger import alert_logger as logger


class AlertBuilder:
    _alert_event_cache: Dict[int, set] = {}

    # ALERT类型的有效level_id缓存（首次使用时加载，Level 信号变更时自动失效）
    _valid_alert_levels: Optional[set] = None

    @classmethod
    def clear_event_cache(cls):
        cls._alert_event_cache.clear()

    @classmethod
    def _get_valid_alert_levels(cls) -> set:
        """
        获取ALERT类型的有效level_id集合

        Returns:
            set: ALERT类型的level_id集合，如{0, 1, 2}
        """
        if cls._valid_alert_levels is None:
            cls._valid_alert_levels = set(Level.objects.filter(level_type=LevelType.ALERT).values_list("level_id", flat=True))
            logger.info("[AlertBuild] 加载ALERT类型有效级别: %s", sorted(cls._valid_alert_levels))
        return cls._valid_alert_levels

    @classmethod
    def _map_event_level_to_alert(cls, event_level: Any) -> str:
        """
        将EVENT级别映射到ALERT级别

        级别语义：数字越小越严重 (0=致命 > 1=错误 > 2=预警 > 3=提醒)
        如果event_level超出ALERT的有效范围，映射到最接近的有效值

        Args:
            event_level: Event的level值（可能是字符串或整数）

        Returns:
            str: ALERT类型的有效level_id字符串
        """
        try:
            level_id = int(event_level)
        except (ValueError, TypeError):
            logger.warning("[AlertBuild] 无效的event_level: %s, 使用默认值0(致命)", event_level)
            return "0"

        valid_levels = cls._get_valid_alert_levels()

        if not valid_levels:
            logger.error("[AlertBuild] 未找到ALERT类型的级别配置，使用默认值0(致命)")
            return "0"

        # 如果在有效范围内，直接返回
        if level_id in valid_levels:
            return str(level_id)

        # 超出范围，映射到最接近的有效值
        sorted_levels = sorted(valid_levels)

        if level_id < sorted_levels[0]:
            # Event比ALERT最严重的级别还要严重，保持最严重级别
            mapped_level = sorted_levels[0]
            logger.debug(
                "[AlertBuild] Event级别%s比ALERT最严重级别还严重，映射到%s(最严重)",
                level_id,
                mapped_level,
            )
        elif level_id > sorted_levels[-1]:
            # Event比ALERT最轻微的级别还要轻微，映射到ALERT最轻微级别
            mapped_level = sorted_levels[-1]
            logger.warning(
                "[AlertBuild] Event级别%s(更轻微)超出ALERT范围，映射到%s(ALERT最轻微级别)",
                level_id,
                mapped_level,
            )
        else:
            # 在范围内但不存在，向更严重方向取最接近的有效值
            mapped_level = max(lvl for lvl in sorted_levels if lvl < level_id)
            logger.debug(
                "[AlertBuild] Event级别%s不存在于ALERT，向严重方向映射到%s",
                level_id,
                mapped_level,
            )

        return str(mapped_level)

    @staticmethod
    def _get_safe_strategy_team(strategy: AlarmStrategy) -> List[int]:
        try:
            dispatch_team = normalize_team_ids(strategy.dispatch_team)
        except ValueError:
            logger.warning(
                "[AlertBuild] 告警策略 dispatch_team 非法，回退为空列表: strategy_id=%s dispatch_team=%s",
                strategy.id,
                strategy.dispatch_team,
            )
            return []

        if not dispatch_team:
            return []

        return dispatch_team

    @staticmethod
    def _get_unique_scalar_value(values: List[Any]) -> Any:
        unique_values = {value for value in values}
        if len(unique_values) == 1:
            return values[0]
        return None

    @staticmethod
    def _merge_enrichment(events) -> dict:
        """合并成员事件 enrichment；命名空间保持稳定对象，冲突写入 _meta。"""
        merged_by_namespace = {}
        for event in events:
            data = getattr(event, "enrichment", None) or {}
            for namespace, payload in data.items():
                if not payload:
                    continue
                existing = merged_by_namespace.get(namespace)
                if existing is None:
                    merged_by_namespace[namespace], _ = merge_namespace_payload({}, payload)
                elif existing != payload:
                    merged_by_namespace[namespace], _ = merge_namespace_payload(existing, payload)
        return merged_by_namespace

    @staticmethod
    def _get_consistent_labels(events: List[Event]) -> Dict[str, Any]:
        if not events:
            return {}

        serialized_labels = [json.dumps(event.labels or {}, sort_keys=True, ensure_ascii=False) for event in events]

        if len(set(serialized_labels)) == 1:
            return events[0].labels or {}

        return {}

    @staticmethod
    def _merge_enrichment_meta(events) -> dict:
        status_counts: Dict[str, int] = {}
        event_count = 0
        for event in events:
            event_count += 1
            status = (getattr(event, "enrichment_meta", None) or {}).get("status", "skipped")
            status_counts[status] = status_counts.get(status, 0) + 1
        return {
            "schema_version": 1,
            "event_count": event_count,
            "status_counts": status_counts,
        }

    @staticmethod
    def _resolve_standard_fields(events) -> Dict[str, Any]:
        event_list = list(events)
        if not event_list:
            return {
                "source_name": None,
                "push_source_ids": [],
                "resource_id": None,
                "resource_name": None,
                "resource_type": None,
                "item": None,
                "labels": {},
                "enrichment": {},
                "enrichment_meta": {"schema_version": 1, "event_count": 0, "status_counts": {}},
            }

        return {
            "source_name": AlertBuilder._get_unique_scalar_value([event.source.name for event in event_list]),
            "push_source_ids": collect_push_source_ids(event_list),
            "resource_id": AlertBuilder._get_unique_scalar_value([event.resource_id for event in event_list]),
            "resource_name": AlertBuilder._get_unique_scalar_value([event.resource_name for event in event_list]),
            "resource_type": AlertBuilder._get_unique_scalar_value([event.resource_type for event in event_list]),
            "item": AlertBuilder._get_unique_scalar_value([event.item for event in event_list]),
            "labels": AlertBuilder._get_consistent_labels(event_list),
            "enrichment": AlertBuilder._merge_enrichment(event_list),
            "enrichment_meta": AlertBuilder._merge_enrichment_meta(event_list),
        }

    @staticmethod
    def _resolve_dimensions(events: List[Event], group_by_field: str) -> Dict[str, str]:
        event_list = list(events)
        if not event_list or not group_by_field:
            return {}

        dimension_names = [item.strip() for item in group_by_field.split(",") if item.strip()]
        dimensions: Dict[str, str] = {}

        for dimension_name in dimension_names:
            values = set()
            for event in event_list:
                if dimension_name.startswith("enrichment."):
                    value = resolve_data_path(
                        {"enrichment": getattr(event, "enrichment", None) or {}},
                        dimension_name,
                    )
                else:
                    value = getattr(event, dimension_name, None)
                if value is None:
                    continue
                normalized_value = str(value).strip()
                if normalized_value:
                    values.add(normalized_value)

            if len(values) == 1:
                dimensions[dimension_name] = values.pop()

        return dimensions

    @staticmethod
    def _get_events_by_ids(event_ids: List) -> List[Event]:
        return list(Event.objects.select_related("source").filter(event_id__in=event_ids).order_by("pk"))

    @staticmethod
    def create_or_update_alert(
        aggregation_result: Dict[str, Any],
        strategy: AlarmStrategy,
        group_by_field: str = "",
    ) -> Alert:
        """
        创建或更新Alert（并发安全版本）

        使用行级锁防止多进程并发创建相同fingerprint的Alert
        """
        fingerprint = aggregation_result.get("fingerprint")
        event_ids = aggregation_result.get("event_ids", [])

        from apps.alerts.service.active_fingerprint import bind_active_fingerprint, claim_active_fingerprint

        lease, alert = claim_active_fingerprint(fingerprint)
        if alert:
            return AlertBuilder._update_existing_alert(alert, aggregation_result, event_ids, strategy)

        alert = AlertBuilder._create_new_alert(aggregation_result, strategy, event_ids, group_by_field)
        bind_active_fingerprint(lease, alert)
        return alert

    @staticmethod
    def _create_new_alert(
        result: Dict[str, Any],
        strategy: AlarmStrategy,
        event_ids: List,
        group_by_field: str,
    ) -> Alert:
        alert_id = f"ALERT-{uuid.uuid4().hex.upper()}"
        events = AlertBuilder._get_events_by_ids(event_ids) if event_ids else []
        standard_fields = AlertBuilder._resolve_standard_fields(events)
        dimensions = AlertBuilder._resolve_dimensions(events, group_by_field)
        monitor_objects = resolve_monitor_objects(event for event in events if event.action == EventAction.CREATED)

        window_config = WindowFactory.create_from_strategy(strategy)

        is_session_alert = window_config.is_session_window
        session_timeout_minutes = getattr(window_config, "session_timeout_minutes", 0)

        # 确保level在ALERT类型的有效范围内
        mapped_level = AlertBuilder._map_event_level_to_alert(result["alert_level"])

        alert = Alert.objects.create(
            alert_id=alert_id,
            fingerprint=result["fingerprint"],
            level=mapped_level,
            title=result["alert_title"] or "聚合告警",
            content=result.get("alert_description") or "",
            status=AlertStatus.UNASSIGNED,
            first_event_time=result["first_event_time"],
            last_event_time=result["last_event_time"],
            labels=standard_fields["labels"],
            enrichment=standard_fields["enrichment"],
            enrichment_meta=standard_fields["enrichment_meta"],
            item=standard_fields["item"],
            resource_id=standard_fields["resource_id"],
            resource_name=standard_fields["resource_name"],
            resource_type=standard_fields["resource_type"],
            monitor_objects=monitor_objects,
            source_name=standard_fields["source_name"],
            push_source_ids=standard_fields["push_source_ids"],
            group_by_field=group_by_field,
            dimensions=dimensions,
            is_session_alert=is_session_alert,
            session_status=SessionStatus.OBSERVING if is_session_alert and session_timeout_minutes else None,
            session_end_time=window_config.get_session_end_time() if is_session_alert and session_timeout_minutes else None,
            rule_id=strategy.id,  # 软关联告警策略
            team=AlertBuilder._get_safe_strategy_team(strategy),
        )

        if events:
            alert.events.add(*events)

            # 初始化新创建Alert的缓存
            AlertBuilder._alert_event_cache[alert.pk] = set(event_ids)

        from django.db import transaction

        from apps.alerts.service.alert_lifecycle import dispatch_alert_lifecycle

        transaction.on_commit(lambda aid=alert.alert_id: dispatch_alert_lifecycle([aid], "created"))

        return alert

    @staticmethod
    def _update_existing_alert(
        alert: Alert,
        result: Dict[str, Any],
        event_ids: List,
        strategy: AlarmStrategy,
    ) -> Alert:
        # 与恢复事件关联、历史回填共用 Alert 行锁；锁内重读快照。
        alert = Alert.objects.select_for_update().get(pk=alert.pk)
        alert.last_event_time = result["last_event_time"]
        # 确保level在ALERT类型的有效范围内
        alert.level = AlertBuilder._map_event_level_to_alert(result["alert_level"])
        alert.updated_at = timezone.now()

        if alert.is_session_alert and alert.session_status == SessionStatus.OBSERVING:
            params = strategy.params or {}
            time_out = params.get("time_out", False)

            if time_out:
                window_config = WindowFactory.create_from_strategy(strategy)
                alert.session_end_time = window_config.get_session_end_time()

        if event_ids:
            # 事务回滚不会回滚进程缓存；锁内以数据库关系为准，保证重试不会漏关联。
            existing_event_ids = set(alert.events.filter(event_id__in=event_ids).values_list("event_id", flat=True))
            new_event_ids = [eid for eid in event_ids if eid not in existing_event_ids]

            if new_event_ids:
                new_events = Event.objects.filter(event_id__in=new_event_ids)
                alert.events.add(*new_events)

        related_events = alert.events.select_related("source").all().order_by("pk")
        standard_fields = AlertBuilder._resolve_standard_fields(related_events)
        alert.monitor_objects = resolve_monitor_objects(event for event in related_events if event.action == EventAction.CREATED)
        dimensions = AlertBuilder._resolve_dimensions(
            related_events,
            alert.group_by_field or "",
        )
        alert.source_name = standard_fields["source_name"]
        alert.push_source_ids = standard_fields["push_source_ids"]
        alert.resource_id = standard_fields["resource_id"]
        alert.resource_name = standard_fields["resource_name"]
        alert.resource_type = standard_fields["resource_type"]
        alert.item = standard_fields["item"]
        alert.labels = standard_fields["labels"]
        alert.enrichment = standard_fields["enrichment"]
        alert.enrichment_meta = standard_fields["enrichment_meta"]
        alert.dimensions = dimensions
        alert.save(
            update_fields=[
                "last_event_time",
                "level",
                "updated_at",
                "session_end_time",
                "source_name",
                "push_source_ids",
                "resource_id",
                "resource_name",
                "resource_type",
                "monitor_objects",
                "item",
                "labels",
                "enrichment",
                "enrichment_meta",
                "dimensions",
            ]
        )
        return alert
