# -- coding: utf-8 --
from typing import List
from collections import defaultdict

from apps.alerts.models import Alert, Event
from apps.alerts.constants import AlertStatus, EventAction, SessionStatus
from apps.core.logger import alert_logger as logger


class AlertRecoveryChecker:
    """
    Alert 恢复状态检查器
    
    职责：
    1. 检查 Alert 下所有 CREATED 事件是否都被恢复
    2. 判断逻辑：CREATED 事件被恢复 = 存在相同 external_id 且 received_at 更晚的 RECOVERY/CLOSED 事件
    3. 如果所有 CREATED 都被恢复，则将 Alert 状态设置为 AUTO_RECOVERY
    4. 如果是会话窗口 Alert，同时更新 session_status 为 RECOVERED
    """

    @staticmethod
    def check_and_recover_alert(alert: Alert) -> bool:
        """
        检查 Alert 是否应该被自动恢复
        
        条件：Alert 下所有 CREATED 事件都有对应的"更晚到达"的 RECOVERY/CLOSED 事件
        
        算法优化：使用字典索引，时间复杂度 O(n)
        
        Args:
            alert: 待检查的 Alert 对象
            
        Returns:
            bool: 是否恢复了 Alert
        """
        # 1. 预加载所有事件（优化查询，包含外键关系）
        # 注意：当前代码未访问event.source等外键，但添加预加载增强健壮性
        all_events = list(alert.events.select_related('source').all())
        
        if not all_events:
            logger.debug(f"Alert {alert.alert_id} 没有关联事件")
            return False
        
        # 2. 按 action 分组，构建索引
        created_events = []
        recovery_by_external_id = defaultdict(list)  # external_id -> [recovery_events]
        for event in all_events:
            if event.action == EventAction.CREATED:
                created_events.append(event)
            elif event.action in [EventAction.RECOVERY, EventAction.CLOSED]:
                # 只记录有 external_id 的恢复事件
                if event.external_id:
                    recovery_by_external_id[event.external_id].append(event)
        # 3. 如果没有 CREATED 事件，无需恢复
        if not created_events and recovery_by_external_id.keys().__len__() == 0:
            logger.debug(f"Alert {alert.alert_id} 没有 CREATED 事件和 恢复事件，无需恢复")
            return False
        
        # 4. 检查每个 CREATED 事件是否都被恢复
        unrecovered_events = []
        
        for created_event in created_events:
            external_id = created_event.external_id
            
            if not external_id:
                # CREATED 事件没有 external_id，无法判断恢复状态
                logger.warning(
                    f"Alert {alert.alert_id} 的 CREATED 事件 {created_event.event_id} "
                    f"缺少 external_id，无法判断恢复状态"
                )
                unrecovered_events.append(created_event)
                continue
            
            # 查找相同 external_id 的 RECOVERY/CLOSED 事件
            recovery_events = recovery_by_external_id.get(external_id, [])
            
            # 检查是否有更晚的 RECOVERY/CLOSED 事件
            has_later_recovery = any(
                r.received_at > created_event.received_at 
                for r in recovery_events
            )
            
            if not has_later_recovery:
                unrecovered_events.append(created_event)
        
        # 5. 如果还有未恢复的 CREATED 事件，保持 Alert 活跃
        if unrecovered_events:
            logger.debug(
                f"Alert {alert.alert_id} 还有 {len(unrecovered_events)} 个未恢复的 CREATED 事件，"
                f"external_ids: {[e.external_id for e in unrecovered_events[:3]]}"
                f"{'...' if len(unrecovered_events) > 3 else ''}"
            )
            return False
        
        # 6. 所有 CREATED 事件都被恢复，设置 Alert 为自动恢复
        alert.status = AlertStatus.AUTO_RECOVERY
        
        # 7. 如果是会话窗口，更新会话状态
        if alert.is_session_alert and alert.session_status == SessionStatus.OBSERVING:
            alert.session_status = SessionStatus.RECOVERED
            alert.save(update_fields=['status', 'session_status', 'updated_at'])
            logger.info(
                f"会话 Alert {alert.alert_id} 已自动恢复 "
                f"(session_status={SessionStatus.RECOVERED}, "
                f"CREATED 事件数={len(created_events)})"
            )
        else:
            alert.save(update_fields=['status', 'updated_at'])
            logger.info(
                f"Alert {alert.alert_id} 已自动恢复 "
                f"(CREATED 事件数={len(created_events)})"
            )
        
        return True
