import json
import uuid
from typing import Any, Dict, List, Optional

from django.db import transaction
from django.utils import timezone

from apps.alerts.aggregation.batching import AGGREGATION_BATCH_SIZE
from apps.alerts.aggregation.builder.event_reducer import EventFieldReducer
from apps.alerts.aggregation.window.factory import WindowFactory
from apps.alerts.constants.constants import AlertStatus, EventAction, LevelType, SessionStatus
from apps.alerts.enrichment.merge import merge_namespace_payload
from apps.alerts.models.alert_operator import AlarmStrategy
from apps.alerts.models.models import Alert, Event, Level
from apps.alerts.service.monitor_sources import remember_snapshot
from apps.alerts.utils.permission_scope import normalize_team_ids
from apps.alerts.utils.queryset import iter_queryset_in_pk_batches
from apps.core.logger import alert_logger as logger

MAX_ALERT_OWNERS = 50


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
    def _collect_owners(events) -> list:
        """创建事件责任人的有序并集。恢复和关闭事件不参与。"""
        owners = []
        seen = set()
        for event in events:
            if getattr(event, "action", None) != EventAction.CREATED:
                continue
            for name in getattr(event, "assignee", None) or []:
                if not isinstance(name, str):
                    continue
                username = name.strip()
                if not username or username in seen:
                    continue
                seen.add(username)
                owners.append(username)
                if len(owners) >= MAX_ALERT_OWNERS:
                    return owners
        return owners

    @staticmethod
    def _reduce_events(events, group_by_field: str = "") -> EventFieldReducer:
        reducer = EventFieldReducer(group_by_field)
        batch = []
        for event in events:
            batch.append(event)
            if len(batch) >= AGGREGATION_BATCH_SIZE:
                reducer.consume(batch)
                batch = []
        if batch:
            reducer.consume(batch)
        return reducer

    @staticmethod
    def _resolve_standard_fields(events) -> Dict[str, Any]:
        return AlertBuilder._reduce_events(events).standard_fields()

    @staticmethod
    def _resolve_dimensions(events: List[Event], group_by_field: str) -> Dict[str, str]:
        if not group_by_field:
            return {}
        return AlertBuilder._reduce_events(events, group_by_field).dimensions()

    @staticmethod
    def _pk_batches_for_event_ids(event_ids: List):
        if not event_ids:
            return
        queryset = Event.objects.filter(event_id__in=event_ids)
        for batch in iter_queryset_in_pk_batches(queryset, AGGREGATION_BATCH_SIZE):
            yield [event.pk for event in batch]

    @staticmethod
    def _link_pk_batches(alert: Alert, pk_batches) -> int:
        added = 0
        for pks in pk_batches or []:
            if not pks:
                continue
            existing = set(alert.events.filter(pk__in=pks).values_list("pk", flat=True))
            new_pks = [pk for pk in pks if pk not in existing]
            if not new_pks:
                continue
            alert.events.add(*new_pks)
            added += len(new_pks)
        return added

    @staticmethod
    def _fill_reduced_fields(alert: Alert, group_by_field: str) -> None:
        reducer = EventFieldReducer(group_by_field)
        related = alert.events.select_related("source")
        for batch in iter_queryset_in_pk_batches(related, AGGREGATION_BATCH_SIZE):
            reducer.consume(batch)
        fields = reducer.standard_fields()
        alert.source_name = fields["source_name"]
        alert.push_source_ids = fields["push_source_ids"]
        alert.resource_id = fields["resource_id"]
        alert.resource_name = fields["resource_name"]
        alert.resource_type = fields["resource_type"]
        alert.item = fields["item"]
        alert.labels = fields["labels"]
        alert.enrichment = fields["enrichment"]
        alert.enrichment_meta = fields["enrichment_meta"]
        alert.dimensions = reducer.dimensions()
        alert.monitor_objects = reducer.monitor_objects
        alert.owners = reducer.owners

    @staticmethod
    def create_or_update_alert(
        aggregation_result: Dict[str, Any],
        strategy: AlarmStrategy,
        group_by_field: str = "",
        window_end=None,
        member_pk_batches=None,
    ) -> Alert:
        """
        创建或更新Alert（并发安全版本）

        使用行级锁防止多进程并发创建相同fingerprint的Alert
        """
        fingerprint = aggregation_result.get("fingerprint")
        event_ids = aggregation_result.get("event_ids", [])
        if member_pk_batches is None:
            member_pk_batches = AlertBuilder._pk_batches_for_event_ids(event_ids)

        from apps.alerts.service.active_fingerprint import bind_active_fingerprint, claim_active_fingerprint

        lease, alert = claim_active_fingerprint(fingerprint)
        if alert:
            return AlertBuilder._update_existing_alert(
                alert,
                aggregation_result,
                member_pk_batches,
                strategy,
                group_by_field,
                window_end,
            )

        alert = AlertBuilder._create_new_alert(
            aggregation_result,
            strategy,
            member_pk_batches,
            group_by_field,
            window_end,
        )
        bind_active_fingerprint(lease, alert)
        return alert

    @staticmethod
    @transaction.atomic
    def _create_new_alert(
        result: Dict[str, Any],
        strategy: AlarmStrategy,
        member_pk_batches,
        group_by_field: str,
        window_end=None,
    ) -> Alert:
        alert_id = f"ALERT-{uuid.uuid4().hex.upper()}"
        window_config = WindowFactory.create_from_strategy(strategy, window_end=window_end)

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
            labels={},
            enrichment={},
            enrichment_meta={"schema_version": 1, "event_count": 0, "status_counts": {}},
            item=None,
            resource_id=None,
            resource_name=None,
            resource_type=None,
            monitor_objects=[],
            owners=[],
            source_name=None,
            push_source_ids=[],
            group_by_field=group_by_field,
            dimensions={},
            is_session_alert=is_session_alert,
            session_status=SessionStatus.OBSERVING if is_session_alert and session_timeout_minutes else None,
            session_end_time=window_config.get_session_end_time() if is_session_alert and session_timeout_minutes else None,
            rule_id=strategy.id,  # 软关联告警策略
            team=AlertBuilder._get_safe_strategy_team(strategy),
        )

        added = AlertBuilder._link_pk_batches(alert, member_pk_batches)
        AlertBuilder._fill_reduced_fields(alert, group_by_field)
        alert.save(
            update_fields=[
                "source_name",
                "push_source_ids",
                "resource_id",
                "resource_name",
                "resource_type",
                "item",
                "labels",
                "enrichment",
                "enrichment_meta",
                "dimensions",
                "monitor_objects",
                "owners",
                "updated_at",
            ]
        )
        alert.aggregation_linked_new_events = added

        remember_snapshot(alert)

        from apps.alerts.itsm.service import enqueue_creation

        enqueue_creation(alert)

        from django.db import transaction

        from apps.alerts.service.alert_lifecycle import dispatch_alert_lifecycle

        transaction.on_commit(lambda aid=alert.alert_id: dispatch_alert_lifecycle([aid], "created"))

        return alert

    @staticmethod
    def _update_existing_alert(
        alert: Alert,
        result: Dict[str, Any],
        member_pk_batches,
        strategy: AlarmStrategy,
        group_by_field: str = "",
        window_end=None,
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
                window_config = WindowFactory.create_from_strategy(strategy, window_end=window_end)
                alert.session_end_time = window_config.get_session_end_time()

        added = AlertBuilder._link_pk_batches(alert, member_pk_batches)
        AlertBuilder._fill_reduced_fields(alert, group_by_field or alert.group_by_field or "")
        alert.aggregation_linked_new_events = added
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
                "owners",
                "item",
                "labels",
                "enrichment",
                "enrichment_meta",
                "dimensions",
            ]
        )
        remember_snapshot(alert)
        return alert
