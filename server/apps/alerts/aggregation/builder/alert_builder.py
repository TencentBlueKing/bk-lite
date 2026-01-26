from typing import Dict, List, Any, Optional
import uuid
from django.utils import timezone
from django.db import transaction
from apps.alerts.models import Alert, Event, AlarmStrategy
from apps.alerts.constants import AlertStatus, SessionStatus
from apps.alerts.aggregation.window.factory import WindowFactory
from apps.core.logger import alert_logger as logger


class AlertBuilder:
    # 类级别缓存：存储Alert已关联的event_id集合，避免重复查询
    # 注意：仅在单次聚合任务中有效，不跨任务持久化
    _alert_event_cache: Dict[int, set] = {}

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
                    f"发现 {alert_count} 个相同fingerprint的活跃Alert: {fingerprint}, "
                    f"使用最新的Alert"
                )
            
            alert = existing_alerts.order_by('-updated_at').first()
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

        window_config = WindowFactory.create_from_strategy(strategy)

        is_session_alert = window_config.is_session_window
        session_timeout_minutes = getattr(window_config, "session_timeout_minutes", 0)

        alert = Alert.objects.create(
            alert_id=alert_id,
            fingerprint=result["fingerprint"],
            level=result["alert_level"],
            title=result["alert_title"] or "聚合告警",
            content=result.get("alert_description") or "",
            status=AlertStatus.UNASSIGNED,
            first_event_time=result["first_event_time"],
            last_event_time=result["last_event_time"],
            group_by_field=group_by_field,
            is_session_alert=is_session_alert,
            session_status=SessionStatus.OBSERVING if session_timeout_minutes else None,
            session_end_time=window_config.get_session_end_time()
            if session_timeout_minutes
            else None,
            rule_id=strategy.id, # 软关联告警策略
            team=strategy.dispatch_team
        )

        if event_ids:
            events = Event.objects.filter(event_id__in=event_ids)
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
        alert.last_event_time = result["last_event_time"]
        alert.level = result["alert_level"]  # 更新为最新的最高级别
        alert.updated_at = timezone.now()

        if alert.is_session_alert and alert.session_status == SessionStatus.OBSERVING:
            params = strategy.params or {}
            time_out = params.get("time_out", False)

            if time_out:
                window_config = WindowFactory.create_from_strategy(strategy)
                alert.session_end_time = window_config.get_session_end_time()

        alert.save(update_fields=["last_event_time", "level", "updated_at", "session_end_time"])

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

        return alert
