# -- coding: utf-8 --
from django.db import transaction
from django.db.models import Q

from apps.alerts.aggregation.batching import AGGREGATION_BATCH_SIZE
from apps.alerts.aggregation.recovery.match_key import build_recovery_match_key
from apps.alerts.constants.constants import AlertStatus, EventAction, SessionStatus
from apps.alerts.models.models import Alert, Event
from apps.alerts.utils.queryset import iter_queryset_in_pk_batches
from apps.core.logger import alert_logger as logger


class AlertRecoveryChecker:
    """
    Alert 恢复状态检查器

    职责：
    1. 检查 Alert 下所有 CREATED 事件是否都被恢复
    2. 判断逻辑：CREATED 事件被恢复 = 存在相同 external_id 且事件时间更晚的 RECOVERY/CLOSED 事件
    3. 如果所有 CREATED 都被恢复，则将 Alert 状态设置为 AUTO_RECOVERY
    4. 如果是会话窗口 Alert，同时更新 session_status 为 RECOVERED
    """

    @staticmethod
    def _get_created_event_time(event: Event):
        return event.start_time or event.received_at

    @staticmethod
    def _get_recovery_event_time(event: Event):
        return event.end_time or event.start_time or event.received_at

    @staticmethod
    def check_and_recover_alert(alert: Alert) -> bool:
        """
        检查 Alert 是否应该被自动恢复

        条件：Alert 下所有 CREATED 事件都有对应的"事件时间更晚"的 RECOVERY/CLOSED 事件
        """
        related = alert.events.all()
        if not related.exists():
            logger.debug("[AlertRecovery] Alert %s 没有关联事件", alert.alert_id)
            return False

        created = related.filter(action=EventAction.CREATED)
        has_recovery = (
            related.filter(action__in=[EventAction.RECOVERY, EventAction.CLOSED]).exclude(external_id__isnull=True).exclude(external_id="").exists()
        )
        has_created = created.exists()
        if not has_created and not has_recovery:
            logger.debug("[AlertRecovery] Alert %s 没有 CREATED 事件和 恢复事件，无需恢复", alert.alert_id)
            return False

        unrecovered_count = 0
        unrecovered_samples = []
        created_count = 0
        if has_created and not has_recovery:
            created_count = created.count()
            unrecovered_count = created_count
            unrecovered_samples = list(created.exclude(external_id__isnull=True).exclude(external_id="").values_list("external_id", flat=True)[:3])
            missing_external_id = created.filter(Q(external_id__isnull=True) | Q(external_id=""))
            for created_event in missing_external_id.iterator():
                logger.warning(
                    "[AlertRecovery] Alert %s 的 CREATED 事件 %s 缺少 external_id，无法判断恢复状态",
                    alert.alert_id,
                    created_event.event_id,
                )
        else:
            latest_recovery = {}
            linked_recoveries = related.filter(action__in=[EventAction.RECOVERY, EventAction.CLOSED]).order_by("pk")
            for batch in iter_queryset_in_pk_batches(linked_recoveries, AGGREGATION_BATCH_SIZE):
                for recovery_event in batch:
                    recovery_key = build_recovery_match_key(recovery_event)
                    if recovery_key is None:
                        continue
                    recovery_time = AlertRecoveryChecker._get_recovery_event_time(recovery_event)
                    previous = latest_recovery.get(recovery_key)
                    if previous is None or recovery_time > previous:
                        latest_recovery[recovery_key] = recovery_time
            for batch in iter_queryset_in_pk_batches(created.order_by("pk"), AGGREGATION_BATCH_SIZE):
                for created_event in batch:
                    created_count += 1
                    if AlertRecoveryChecker._created_time_is_recovered(alert, created_event, latest_recovery):
                        continue
                    unrecovered_count += 1
                    if created_event.external_id and len(unrecovered_samples) < 3:
                        unrecovered_samples.append(created_event.external_id)

        if unrecovered_count:
            logger.debug(
                "[AlertRecovery] Alert %s 还有 %s 个未恢复的 CREATED 事件，external_ids: %s%s",
                alert.alert_id,
                unrecovered_count,
                unrecovered_samples,
                "..." if unrecovered_count > 3 else "",
            )
            return False

        alert.status = AlertStatus.AUTO_RECOVERY
        Alert.stamp_closed_at(alert)

        if alert.is_session_alert and alert.session_status == SessionStatus.OBSERVING:
            alert.session_status = SessionStatus.RECOVERED
            alert.save(update_fields=["status", "session_status", "updated_at", "closed_at"])
            logger.info(
                "[AlertRecovery] 会话 Alert %s 已自动恢复 (session_status=%s, CREATED 事件数=%s)",
                alert.alert_id,
                SessionStatus.RECOVERED,
                created_count,
            )
        else:
            alert.save(update_fields=["status", "updated_at", "closed_at"])
            logger.info(
                "[AlertRecovery] Alert %s 已自动恢复 (CREATED 事件数=%s)",
                alert.alert_id,
                created_count,
            )

        from apps.alerts.service.alert_lifecycle import dispatch_alert_lifecycle
        from apps.alerts.service.recovery_notify import notify_alert_recovered
        from apps.alerts.service.reminder_service import ReminderService

        ReminderService.stop_reminder_task(alert)
        recovered_alert_id = alert.alert_id
        transaction.on_commit(lambda a=alert: notify_alert_recovered(a))
        transaction.on_commit(lambda aid=recovered_alert_id: dispatch_alert_lifecycle([aid], "resolved"))

        return True

    @staticmethod
    def _created_time_is_recovered(alert: Alert, created_event: Event, latest_recovery: dict) -> bool:
        if not created_event.external_id:
            logger.warning(
                "[AlertRecovery] Alert %s 的 CREATED 事件 %s 缺少 external_id，无法判断恢复状态",
                alert.alert_id,
                created_event.event_id,
            )
            return False
        created_key = build_recovery_match_key(created_event)
        if created_key is None:
            return False
        recovery_time = latest_recovery.get(created_key)
        if recovery_time is None:
            return False
        return recovery_time > AlertRecoveryChecker._get_created_event_time(created_event)


def attach_visible_recoveries(alert: Alert) -> int:
    """把已经提交、且匹配本告警 CREATED 的恢复事件补挂到告警上。"""
    if not Event.objects.filter(action__in=[EventAction.RECOVERY, EventAction.CLOSED]).exists():
        return 0
    added = _attach_primary_recoveries(alert)
    added += _attach_fallback_recoveries(alert)
    return added


def deliver_recovery_reattach(payload: dict) -> None:
    alert_pk = payload.get("alert_pk")
    if not alert_pk:
        raise ValueError("recovery reattach missing alert_pk")
    with transaction.atomic():
        alert = Alert.objects.select_for_update().filter(pk=alert_pk).first()
        if alert is None or alert.status not in AlertStatus.ACTIVATE_STATUS:
            return
        attach_visible_recoveries(alert)
        AlertRecoveryChecker.check_and_recover_alert(alert)


def _attach_primary_recoveries(alert: Alert) -> int:
    from apps.alerts.service.monitor_sources import associate_event_with_monitor_sources

    created_times = {}
    external_ids = set()
    created = alert.events.filter(action=EventAction.CREATED).order_by("pk")
    for batch in iter_queryset_in_pk_batches(created, AGGREGATION_BATCH_SIZE):
        for created_event in batch:
            created_key = build_recovery_match_key(created_event)
            if created_key is None:
                continue
            created_times.setdefault(created_key, []).append(AlertRecoveryChecker._get_created_event_time(created_event))
            external_ids.add(created_event.external_id)
    if not external_ids:
        return 0

    added = 0
    external_id_list = list(external_ids)
    for offset in range(0, len(external_id_list), AGGREGATION_BATCH_SIZE):
        candidates = Event.objects.filter(
            action__in=[EventAction.RECOVERY, EventAction.CLOSED],
            external_id__in=external_id_list[offset : offset + AGGREGATION_BATCH_SIZE],
        ).order_by("pk")
        for batch in iter_queryset_in_pk_batches(candidates, AGGREGATION_BATCH_SIZE):
            for recovery_event in batch:
                recovery_key = build_recovery_match_key(recovery_event)
                times = created_times.get(recovery_key)
                if not times:
                    continue
                recovery_time = AlertRecoveryChecker._get_recovery_event_time(recovery_event)
                if not any(recovery_time > created_time for created_time in times):
                    continue
                if associate_event_with_monitor_sources(alert.pk, recovery_event):
                    added += 1
    return added


def _attach_fallback_recoveries(alert: Alert) -> int:
    from apps.alerts.aggregation.recovery.recovery_handler import RecoveryHandler
    from apps.alerts.service.monitor_sources import associate_event_with_monitor_sources

    created = alert.events.filter(action=EventAction.CREATED).order_by("pk")
    fallback_times = {}
    for batch in iter_queryset_in_pk_batches(created, AGGREGATION_BATCH_SIZE):
        for created_event in batch:
            fallback_key = RecoveryHandler._build_fallback_key(created_event)
            if fallback_key is None:
                continue
            fallback_times.setdefault(fallback_key, []).append(AlertRecoveryChecker._get_created_event_time(created_event))

    added = 0
    for fallback_key, times in fallback_times.items():
        source_pk, item, resource_name, _source_id, _team = fallback_key
        candidate_alert_pks = set(
            Alert.objects.filter(
                status__in=AlertStatus.ACTIVATE_STATUS,
                events__action=EventAction.CREATED,
                events__source_id=source_pk,
                events__item=item,
                events__resource_name=resource_name,
            )
            .order_by()
            .values_list("pk", flat=True)
            .distinct()
        )
        if candidate_alert_pks != {alert.pk}:
            continue
        recoveries = Event.objects.filter(
            action__in=[EventAction.RECOVERY, EventAction.CLOSED],
            source_id=source_pk,
            item=item,
            resource_name=resource_name,
        ).order_by("pk")
        for batch in iter_queryset_in_pk_batches(recoveries, AGGREGATION_BATCH_SIZE):
            for recovery_event in batch:
                if not RecoveryHandler._supports_unique_fallback(recovery_event):
                    continue
                if RecoveryHandler._build_fallback_key(recovery_event) != fallback_key:
                    continue
                if _primary_match_exists(recovery_event):
                    continue
                recovery_time = AlertRecoveryChecker._get_recovery_event_time(recovery_event)
                if not any(recovery_time > created_time for created_time in times):
                    continue
                if associate_event_with_monitor_sources(alert.pk, recovery_event):
                    added += 1
    return added


def _primary_match_exists(recovery_event: Event) -> bool:
    recovery_key = build_recovery_match_key(recovery_event)
    if recovery_key is None:
        return False
    candidates = Event.objects.filter(
        action=EventAction.CREATED,
        source_id=recovery_event.source_id,
        push_source_id=recovery_event.push_source_id,
        external_id=recovery_event.external_id,
        alert__status__in=AlertStatus.ACTIVATE_STATUS,
    )
    for created_event in candidates.iterator():
        if build_recovery_match_key(created_event) == recovery_key:
            return True
    return False
