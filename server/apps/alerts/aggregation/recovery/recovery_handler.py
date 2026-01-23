# -- coding: utf-8 --
from typing import List
from collections import defaultdict

from apps.alerts.models import Alert, Event
from apps.alerts.constants import AlertStatus, EventAction
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
        recovery_event_map = {}  # event_id -> Event
        
        for recovery_event in recovery_events:
            if recovery_event.external_id:
                external_ids.add(recovery_event.external_id)
                recovery_event_map[recovery_event.event_id] = recovery_event
            else:
                logger.warning(
                    f"恢复事件 {recovery_event.event_id} 缺少 external_id，跳过"
                )
        
        if not external_ids:
            logger.debug("所有恢复事件都缺少 external_id，跳过处理")
            return
        
        # 2. 批量查询所有相关 Alert（优化：1 次查询 + prefetch）
        affected_alerts = Alert.objects.filter(
            status__in=AlertStatus.ACTIVATE_STATUS,
            events__external_id__in=external_ids,
            events__action=EventAction.CREATED
        ).prefetch_related('events').distinct()
        
        if not affected_alerts.exists():
            logger.debug(
                f"未找到包含 external_ids={list(external_ids)[:5]}... "
                f"的活跃 Alert"
            )
            return
        
        # 3. 构建索引：external_id -> [Alert]
        alert_by_external_id = defaultdict(list)
        alert_existing_events = {}  # alert.pk -> set(event_id)
        
        for alert in affected_alerts:
            # 收集该 Alert 已关联的所有 event_id（避免重复查询）
            existing_event_ids = set(alert.events.values_list('event_id', flat=True))
            alert_existing_events[alert.pk] = existing_event_ids
            
            # 构建 external_id 索引
            for event in alert.events.all():
                if event.external_id in external_ids:
                    alert_by_external_id[event.external_id].append(alert)
        
        # 4. 批量处理恢复事件关联
        total_added = 0
        total_skipped = 0
        
        for recovery_event in recovery_events:
            external_id = recovery_event.external_id
            if not external_id:
                continue
            
            # 查找匹配的 Alert
            matching_alerts = alert_by_external_id.get(external_id, [])
            
            if not matching_alerts:
                logger.debug(
                    f"恢复事件 {recovery_event.event_id} "
                    f"未找到匹配的 Alert (external_id={external_id})"
                )
                continue
            
            # 批量添加到匹配的 Alert
            for alert in matching_alerts:
                # 检查是否已关联（使用预加载的数据，无额外查询）
                if recovery_event.event_id not in alert_existing_events[alert.pk]:
                    alert.events.add(recovery_event)
                    total_added += 1
                    logger.debug(
                        f"恢复事件 {recovery_event.event_id} "
                        f"已关联到 Alert {alert.alert_id}"
                    )
                else:
                    total_skipped += 1
        
        # 5. 汇总日志
        logger.info(
            f"恢复事件批量处理完成: "
            f"处理 {len(recovery_events)} 个恢复事件, "
            f"新增关联 {total_added} 个, "
            f"跳过重复 {total_skipped} 个"
        )
