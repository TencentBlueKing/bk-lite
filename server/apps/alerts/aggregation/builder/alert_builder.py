from typing import Dict, List, Any, Optional
import uuid
from django.utils import timezone
from apps.alerts.models.models import Alert, Event, Level
from apps.alerts.models.alert_operator import AlarmStrategy
from apps.alerts.constants.constants import AlertStatus, SessionStatus, LevelType
from apps.alerts.aggregation.window.factory import WindowFactory
from apps.core.logger import alert_logger as logger


class AlertBuilder:
    # 类级别缓存：存储Alert已关联的event_id集合，避免重复查询
    # 注意：仅在单次聚合任务中有效，不跨任务持久化
    _alert_event_cache: Dict[int, set] = {}
    
    # ALERT类型的有效level_id缓存（启动时加载）
    _valid_alert_levels: Optional[set] = None

    @classmethod
    def _get_valid_alert_levels(cls) -> set:
        """
        获取ALERT类型的有效level_id集合
        
        Returns:
            set: ALERT类型的level_id集合，如{0, 1, 2}
        """
        if cls._valid_alert_levels is None:
            cls._valid_alert_levels = set(
                Level.objects.filter(level_type=LevelType.ALERT)
                .values_list('level_id', flat=True)
            )
            logger.info(f"加载ALERT类型有效级别: {sorted(cls._valid_alert_levels)}")
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
            logger.warning(f"无效的event_level: {event_level}, 使用默认值0(致命)")
            return "0"
        
        valid_levels = cls._get_valid_alert_levels()
        
        if not valid_levels:
            logger.error("未找到ALERT类型的级别配置，使用默认值0(致命)")
            return "0"
        
        # 如果在有效范围内，直接返回
        if level_id in valid_levels:
            return str(level_id)
        
        # 超出范围，映射到最接近的有效值
        sorted_levels = sorted(valid_levels)
        
        if level_id < sorted_levels[0]:
            # Event比ALERT最严重的级别还要严重，保持最严重级别
            mapped_level = sorted_levels[0]
            logger.debug(f"Event级别{level_id}比ALERT最严重级别还严重，映射到{mapped_level}(最严重)")
        elif level_id > sorted_levels[-1]:
            # Event比ALERT最轻微的级别还要轻微，映射到ALERT最轻微级别
            mapped_level = sorted_levels[-1]
            logger.warning(
                f"Event级别{level_id}(更轻微)超出ALERT范围，映射到{mapped_level}(ALERT最轻微级别)"
            )
        else:
            # 在范围内但不存在，向更严重方向取最接近的有效值
            mapped_level = max(lvl for lvl in sorted_levels if lvl < level_id)
            logger.debug(f"Event级别{level_id}不存在于ALERT，向严重方向映射到{mapped_level}")
        
        return str(mapped_level)

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
        # 确保level在ALERT类型的有效范围内
        alert.level = AlertBuilder._map_event_level_to_alert(result["alert_level"])
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
