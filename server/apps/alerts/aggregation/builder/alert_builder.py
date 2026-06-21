import json
from typing import Dict, List, Any, Optional
import uuid
from django.utils import timezone
from apps.alerts.models.models import Alert, Event, Level
from apps.alerts.models.alert_operator import AlarmStrategy
from apps.alerts.constants.constants import AlertStatus, SessionStatus, LevelType
from apps.alerts.aggregation.window.factory import WindowFactory
from apps.alerts.utils.permission_scope import normalize_team_ids
from apps.core.logger import alert_logger as logger


class AlertBuilder:
    _alert_event_cache: Dict[int, set] = {}

    # ALERT类型的有效level_id缓存（启动时加载）
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
            cls._valid_alert_levels = set(
                Level.objects.filter(level_type=LevelType.ALERT).values_list(
                    "level_id", flat=True
                )
            )
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
                level_id, mapped_level,
            )
        elif level_id > sorted_levels[-1]:
            # Event比ALERT最轻微的级别还要轻微，映射到ALERT最轻微级别
            mapped_level = sorted_levels[-1]
            logger.warning(
                "[AlertBuild] Event级别%s(更轻微)超出ALERT范围，映射到%s(ALERT最轻微级别)",
                level_id, mapped_level,
            )
        else:
            # 在范围内但不存在，向更严重方向取最接近的有效值
            mapped_level = max(lvl for lvl in sorted_levels if lvl < level_id)
            logger.debug(
                "[AlertBuild] Event级别%s不存在于ALERT，向严重方向映射到%s",
                level_id, mapped_level,
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
        """按命名空间合并成员事件 enrichment：首条非空者优先。"""
        merged = {}
        for event in events:
            data = getattr(event, "enrichment", None) or {}
            for namespace, payload in data.items():
                if namespace not in merged and payload:
                    merged[namespace] = payload
        return merged

    @staticmethod
    def _get_consistent_labels(events: List[Event]) -> Dict[str, Any]:
        if not events:
            return {}

        serialized_labels = [
            json.dumps(event.labels or {}, sort_keys=True, ensure_ascii=False)
            for event in events
        ]

        if len(set(serialized_labels)) == 1:
            return events[0].labels or {}

        return {}

    @staticmethod
    def _resolve_standard_fields(events) -> Dict[str, Any]:
        event_list = list(events)
        if not event_list:
            return {
                "source_name": None,
                "resource_id": None,
                "resource_name": None,
                "resource_type": None,
                "item": None,
                "labels": {},
                "enrichment": {},
            }

        return {
            "source_name": AlertBuilder._get_unique_scalar_value(
                [event.source.name for event in event_list]
            ),
            "resource_id": AlertBuilder._get_unique_scalar_value(
                [event.resource_id for event in event_list]
            ),
            "resource_name": AlertBuilder._get_unique_scalar_value(
                [event.resource_name for event in event_list]
            ),
            "resource_type": AlertBuilder._get_unique_scalar_value(
                [event.resource_type for event in event_list]
            ),
            "item": AlertBuilder._get_unique_scalar_value(
                [event.item for event in event_list]
            ),
            "labels": AlertBuilder._get_consistent_labels(event_list),
            "enrichment": AlertBuilder._merge_enrichment(event_list),
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
        return list(
            Event.objects.select_related("source")
            .filter(event_id__in=event_ids)
            .order_by("pk")
        )

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

        # 使用 select_for_update 行级锁确保并发安全
        # 注意：必须在外层transaction.atomic()中调用（由aggregation_processor保证）
        existing_alerts = Alert.objects.select_for_update().filter(
            fingerprint=fingerprint,
            status__in=AlertStatus.ACTIVATE_STATUS,
        )

        if existing_alerts.exists():
            # 防御性检查：如果存在多个活跃Alert（理论上不应该发生）
            alert_count = existing_alerts.count()
            if alert_count > 1:
                logger.warning(
                    "[AlertBuild] 发现 %s 个相同fingerprint的活跃Alert: %s, 使用最新的Alert",
                    alert_count, fingerprint,
                )

            alert = existing_alerts.order_by("-updated_at").first()
            return AlertBuilder._update_existing_alert(
                alert, aggregation_result, event_ids, strategy
            )
        else:
            # 不存在活跃Alert，创建新的
            # 此时其他进程的select_for_update已被阻塞，等待锁释放后会看到新创建的Alert
            return AlertBuilder._create_new_alert(
                aggregation_result, strategy, event_ids, group_by_field
            )

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
            item=standard_fields["item"],
            resource_id=standard_fields["resource_id"],
            resource_name=standard_fields["resource_name"],
            resource_type=standard_fields["resource_type"],
            source_name=standard_fields["source_name"],
            group_by_field=group_by_field,
            dimensions=dimensions,
            is_session_alert=is_session_alert,
            session_status=SessionStatus.OBSERVING
            if is_session_alert and session_timeout_minutes
            else None,
            session_end_time=window_config.get_session_end_time()
            if is_session_alert and session_timeout_minutes
            else None,
            rule_id=strategy.id,  # 软关联告警策略
            team=AlertBuilder._get_safe_strategy_team(strategy),
        )

        if events:
            alert.events.add(*events)

            # 初始化新创建Alert的缓存
            AlertBuilder._alert_event_cache[alert.pk] = set(event_ids)

        return alert

    @staticmethod
    def _update_existing_alert(
        alert: Alert,
        result: Dict[str, Any],
        event_ids: List,
        strategy: AlarmStrategy,
    ) -> Alert:
        events_to_validate = AlertBuilder._get_events_by_ids(event_ids) if event_ids else []
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
            # 性能优化：使用类级别缓存避免重复查询已关联的event_id
            if alert.pk not in AlertBuilder._alert_event_cache:
                AlertBuilder._alert_event_cache[alert.pk] = set(
                    alert.events.values_list("event_id", flat=True)
                )

            existing_event_ids = AlertBuilder._alert_event_cache[alert.pk]
            new_event_ids = [eid for eid in event_ids if eid not in existing_event_ids]

            if new_event_ids:
                new_events = Event.objects.filter(event_id__in=new_event_ids)
                alert.events.add(*new_events)
                # 更新缓存
                existing_event_ids.update(new_event_ids)

        standard_fields = AlertBuilder._resolve_standard_fields(
            alert.events.select_related("source").all().order_by("pk")
        )
        dimensions = AlertBuilder._resolve_dimensions(
            alert.events.all().order_by("pk"),
            alert.group_by_field or "",
        )
        alert.source_name = standard_fields["source_name"]
        alert.resource_id = standard_fields["resource_id"]
        alert.resource_name = standard_fields["resource_name"]
        alert.resource_type = standard_fields["resource_type"]
        alert.item = standard_fields["item"]
        alert.labels = standard_fields["labels"]
        alert.enrichment = standard_fields["enrichment"]
        alert.dimensions = dimensions
        alert.save(
            update_fields=[
                "last_event_time",
                "level",
                "updated_at",
                "session_end_time",
                "source_name",
                "resource_id",
                "resource_name",
                "resource_type",
                "item",
                "labels",
                "enrichment",
                "dimensions",
            ]
        )
        return alert
