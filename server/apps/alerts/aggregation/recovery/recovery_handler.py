# -- coding: utf-8 --
from typing import List, Optional, Tuple
from collections import defaultdict

from django.db import transaction
from django.db.models import Q

from apps.alerts.aggregation.recovery.recovery_checker import AlertRecoveryChecker
from apps.alerts.aggregation.recovery.match_key import build_recovery_match_key
from apps.alerts.models.models import Alert, Event
from apps.alerts.constants.constants import AlertStatus, EventAction
from apps.core.logger import alert_logger as logger


class RecoveryHandler:
    """
    恢复事件处理器（性能优化版）

    职责：
    1. 接收 RECOVERY/CLOSED 类型的事件
    2. 根据 external_id 查找包含相同指纹的活跃 Alert
    3. 批量将恢复事件关联到这些 Alert

    优化点：
    - 批量预加载所有相关 Alert（1 次查询）
    - 使用 prefetch_related 预加载已关联事件（避免 N+1）
    - 使用字典索引匹配（O(1) 查找）
    - 批量处理 ManyToMany 关联
    """

    @staticmethod
    def _normalize_value(value) -> str:
        if value is None:
            return ""
        return str(value).strip()

    @classmethod
    def _build_fallback_key(cls, event: Event) -> Optional[Tuple[int, str, str, str]]:
        item = cls._normalize_value(event.item)
        resource_name = cls._normalize_value(event.resource_name)
        source_id = cls._normalize_value(getattr(event.source, "source_id", None))
        if not item or not resource_name or not source_id:
            return None
        return event.source_id, item, resource_name, source_id

    @classmethod
    def _supports_unique_fallback(cls, event: Event) -> bool:
        return not cls._normalize_value(event.resource_id) and not cls._normalize_value(event.resource_type)

    @staticmethod
    def _run_recovery_checks(touched_alerts: List[Alert], total_events: int, total_added: int, total_skipped: int):
        recovered_count = 0

        for alert in touched_alerts:
            if hasattr(alert, "_prefetched_objects_cache"):
                alert._prefetched_objects_cache = {}
            alert.refresh_from_db()
            if AlertRecoveryChecker.check_and_recover_alert(alert):
                recovered_count += 1

        logger.info(
            "[AlertRecovery] 恢复事件批量处理完成: 处理 %s 个恢复事件, 新增关联 %s 个, 跳过重复 %s 个, 推进恢复 %s 个",
            total_events, total_added, total_skipped, recovered_count,
        )

    @staticmethod
    def handle_recovery_events(recovery_events: List[Event]):
        """
        处理恢复事件：批量将 RECOVERY/CLOSED 事件关联到对应的 Alert

        性能优化逻辑：
        1. 收集所有 external_id
        2. 一次性查询所有相关 Alert（使用 prefetch_related）
        3. 构建 external_id -> [Alert] 的索引
        4. 批量处理关联关系

        Args:
            recovery_events: RECOVERY 或 CLOSED 类型的事件列表
        """
        if not recovery_events:
            return

        # 1. 收集所有有效的 external_id
        external_ids = set()
        fallback_keys = set()
        recovery_event_map = {}  # event_id -> Event

        for recovery_event in recovery_events:
            if recovery_event.external_id:
                external_ids.add(recovery_event.external_id)
                recovery_event_map[recovery_event.event_id] = recovery_event
                fallback_key = RecoveryHandler._build_fallback_key(recovery_event)
                if RecoveryHandler._supports_unique_fallback(recovery_event) and fallback_key:
                    fallback_keys.add(fallback_key)
            else:
                logger.warning("[AlertRecovery] 恢复事件 %s 缺少 external_id，跳过", recovery_event.event_id)

        if not external_ids and not fallback_keys:
            logger.debug("[AlertRecovery] 所有恢复事件都缺少 external_id，跳过处理")
            return

        # 2. 批量查询所有相关 Alert（优化：仅收敛到本批恢复事件可能命中的候选集）
        candidate_q = Q()

        if external_ids:
            candidate_q |= Q(events__external_id__in=external_ids, events__action=EventAction.CREATED)

        for source_pk, item, resource_name, _ in fallback_keys:
            candidate_q |= Q(
                events__source_id=source_pk,
                events__item=item,
                events__resource_name=resource_name,
                events__action=EventAction.CREATED,
            )

        affected_alerts = (
            Alert.objects.filter(status__in=AlertStatus.ACTIVATE_STATUS)
            .filter(candidate_q)
            .prefetch_related("events__source")
            .distinct()
        )

        if not affected_alerts.exists():
            logger.debug("[AlertRecovery] 未找到包含 external_ids=%s... 的活跃 Alert", list(external_ids)[:5])
            return

        # 3. 构建索引：external_id -> [Alert]
        alerts_by_match_key = defaultdict(list)
        alerts_by_fallback_key = defaultdict(list)
        alert_existing_events = {}  # alert.pk -> set(event_id)

        for alert in affected_alerts:
            prefetched_events = list(alert.events.all())

            # 收集该 Alert 已关联的所有 event_id（复用预取结果，避免重复查询）
            existing_event_ids = {event.event_id for event in prefetched_events}
            alert_existing_events[alert.pk] = existing_event_ids

            # 构建 external_id 索引
            for event in prefetched_events:
                match_key = build_recovery_match_key(event)
                if event.external_id in external_ids and match_key:
                    alerts_by_match_key[match_key].append(alert)
                fallback_key = RecoveryHandler._build_fallback_key(event)
                if fallback_key and event.action == EventAction.CREATED:
                    alerts_by_fallback_key[fallback_key].append(alert)

        # 4. 批量处理恢复事件关联
        total_added = 0
        total_skipped = 0
        touched_alerts = {}

        for recovery_event in recovery_events:
            external_id = recovery_event.external_id
            if not external_id:
                continue

            # 查找匹配的 Alert
            matching_alerts = alerts_by_match_key.get(
                build_recovery_match_key(recovery_event), []
            )

            if not matching_alerts:
                fallback_key = RecoveryHandler._build_fallback_key(recovery_event)
                if RecoveryHandler._supports_unique_fallback(recovery_event) and fallback_key:
                    fallback_alerts = alerts_by_fallback_key.get(fallback_key, [])
                    unique_alerts = []
                    seen_alert_ids = set()
                    for alert in fallback_alerts:
                        if alert.pk not in seen_alert_ids:
                            unique_alerts.append(alert)
                            seen_alert_ids.add(alert.pk)
                    if len(unique_alerts) == 1:
                        matching_alerts = unique_alerts
                        logger.info(
                            "[AlertRecovery] 恢复事件 %s 通过唯一回退键关联到 Alert %s",
                            recovery_event.event_id,
                            unique_alerts[0].alert_id,
                        )
                    elif len(unique_alerts) > 1:
                        logger.warning(
                            "[AlertRecovery] 恢复事件 %s 回退匹配到多个 Alert，跳过: fallback_key=%s",
                            recovery_event.event_id,
                            fallback_key,
                        )

            if not matching_alerts:
                logger.debug("[AlertRecovery] 恢复事件 %s 未找到匹配的 Alert (external_id=%s)", recovery_event.event_id, external_id)
                continue

            unique_matching_alerts = []
            seen_alert_ids = set()
            for alert in matching_alerts:
                if alert.pk in seen_alert_ids:
                    continue
                unique_matching_alerts.append(alert)
                seen_alert_ids.add(alert.pk)

            # 批量添加到匹配的 Alert
            for alert in unique_matching_alerts:
                touched_alerts[alert.pk] = alert
                # 检查是否已关联（使用预加载的数据，无额外查询）
                if recovery_event.event_id not in alert_existing_events[alert.pk]:
                    alert.events.add(recovery_event)
                    alert_existing_events[alert.pk].add(recovery_event.event_id)
                    total_added += 1
                    logger.debug("[AlertRecovery] 恢复事件 %s 已关联到 Alert %s", recovery_event.event_id, alert.alert_id)
                else:
                    total_skipped += 1

        # 5. 汇总日志
        if not touched_alerts:
            logger.info(
                "[AlertRecovery] 恢复事件批量处理完成: 处理 %s 个恢复事件, 新增关联 %s 个, 跳过重复 %s 个, 推进恢复 0 个",
                len(recovery_events), total_added, total_skipped,
            )
            return

        transaction.on_commit(
            lambda: RecoveryHandler._run_recovery_checks(
                list(touched_alerts.values()),
                len(recovery_events),
                total_added,
                total_skipped,
            )
        )
