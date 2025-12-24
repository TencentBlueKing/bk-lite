# -- coding: utf-8 --
"""
会话窗口状态管理

管理会话窗口的生命周期和状态
"""
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from dataclasses import dataclass, field

from django.utils import timezone

from apps.alerts.aggregation_v2.config import AggregationV2Config
from apps.alerts.aggregation_v2.state.cache import WindowCache
from apps.core.logger import alert_logger as logger


@dataclass
class SessionWindow:
    """会话窗口数据类"""
    
    session_id: int
    fingerprint: str
    start_time: datetime
    last_event_time: datetime
    event_count: int = 0
    event_ids: List[int] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def duration(self) -> timedelta:
        """会话持续时间"""
        return self.last_event_time - self.start_time
    
    @property
    def is_expired(self) -> bool:
        """会话是否过期（基于配置的最大持续时间）"""
        max_duration = timedelta(seconds=AggregationV2Config.SESSION_DEFAULT_MAX_DURATION)
        return self.duration > max_duration
    
    @property
    def is_full(self) -> bool:
        """会话是否已满（达到最大事件数）"""
        return self.event_count >= AggregationV2Config.SESSION_DEFAULT_MAX_EVENTS
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'session_id': self.session_id,
            'fingerprint': self.fingerprint,
            'start_time': self.start_time.isoformat(),
            'last_event_time': self.last_event_time.isoformat(),
            'event_count': self.event_count,
            'event_ids': self.event_ids,
            'duration_seconds': self.duration.total_seconds(),
            'metadata': self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SessionWindow':
        """从字典创建"""
        from dateutil import parser
        
        return cls(
            session_id=data['session_id'],
            fingerprint=data['fingerprint'],
            start_time=parser.isoparse(data['start_time']),
            last_event_time=parser.isoparse(data['last_event_time']),
            event_count=data.get('event_count', 0),
            event_ids=data.get('event_ids', []),
            metadata=data.get('metadata', {})
        )


class SessionStateManager:
    """会话窗口状态管理器"""
    
    def __init__(self, cache: Optional[WindowCache] = None):
        """
        初始化管理器
        
        Args:
            cache: 缓存实例，默认使用全局缓存
        """
        from apps.alerts.aggregation_v2.state.cache import get_window_cache
        self.cache = cache or get_window_cache()
        self.config = AggregationV2Config
    
    def _make_session_key(self, rule_id: int, fingerprint: str, session_id: int) -> str:
        """生成会话键"""
        from apps.alerts.aggregation_v2.utils.fingerprint import FingerprintGenerator
        session_key = FingerprintGenerator.generate_session_key(fingerprint, session_id)
        return f"session:{rule_id}:{session_key}"
    
    def create_session(
        self,
        rule_id: int,
        fingerprint: str,
        session_id: int,
        start_time: datetime,
        initial_event_id: Optional[int] = None
    ) -> SessionWindow:
        """
        创建新会话
        
        Args:
            rule_id: 规则ID
            fingerprint: 事件指纹
            session_id: 会话序号
            start_time: 会话开始时间
            initial_event_id: 初始事件ID
            
        Returns:
            会话窗口对象
        """
        session = SessionWindow(
            session_id=session_id,
            fingerprint=fingerprint,
            start_time=start_time,
            last_event_time=start_time,
            event_count=1 if initial_event_id else 0,
            event_ids=[initial_event_id] if initial_event_id else []
        )
        
        # 保存到缓存
        self.save_session(rule_id, session)
        
        if self.config.VERBOSE_LOGGING:
            logger.debug(
                f"创建会话: rule={rule_id}, fingerprint={fingerprint}, "
                f"session_id={session_id}"
            )
        
        return session
    
    def get_session(
        self,
        rule_id: int,
        fingerprint: str,
        session_id: int
    ) -> Optional[SessionWindow]:
        """
        获取会话
        
        Args:
            rule_id: 规则ID
            fingerprint: 事件指纹
            session_id: 会话序号
            
        Returns:
            会话窗口对象，不存在返回 None
        """
        window_id = self._make_session_key(rule_id, fingerprint, session_id)
        state_data = self.cache.get_window_state(rule_id, window_id)
        
        if state_data:
            try:
                return SessionWindow.from_dict(state_data)
            except Exception as e:
                logger.error(f"解析会话数据失败: {e}", exc_info=True)
                return None
        return None
    
    def save_session(self, rule_id: int, session: SessionWindow) -> bool:
        """
        保存会话
        
        Args:
            rule_id: 规则ID
            session: 会话窗口对象
            
        Returns:
            是否保存成功
        """
        window_id = self._make_session_key(rule_id, session.fingerprint, session.session_id)
        return self.cache.save_window_state(
            rule_id=rule_id,
            window_id=window_id,
            state_data=session.to_dict(),
            ttl=self.config.SESSION_DEFAULT_MAX_DURATION * 2  # 保留2倍时间
        )
    
    def add_event_to_session(
        self,
        rule_id: int,
        session: SessionWindow,
        event_id: int,
        event_time: datetime
    ) -> SessionWindow:
        """
        向会话添加事件
        
        Args:
            rule_id: 规则ID
            session: 会话窗口对象
            event_id: 事件ID
            event_time: 事件时间
            
        Returns:
            更新后的会话对象
        """
        session.event_ids.append(event_id)
        session.event_count += 1
        session.last_event_time = event_time
        
        # 更新缓存
        self.save_session(rule_id, session)
        
        return session
    
    def should_close_session(
        self,
        session: SessionWindow,
        gap_threshold: timedelta,
        current_time: Optional[datetime] = None
    ) -> bool:
        """
        判断会话是否应该关闭
        
        Args:
            session: 会话窗口对象
            gap_threshold: 时间间隙阈值
            current_time: 当前时间，默认为当前时间
            
        Returns:
            是否应该关闭
        """
        current_time = current_time or timezone.now()
        
        # 检查时间间隙
        time_gap = current_time - session.last_event_time
        if time_gap > gap_threshold:
            return True
        
        # 检查是否过期
        if session.is_expired:
            if self.config.VERBOSE_LOGGING:
                logger.debug(f"会话超过最大持续时间: session_id={session.session_id}")
            return True
        
        # 检查是否已满
        if session.is_full:
            if self.config.VERBOSE_LOGGING:
                logger.debug(f"会话达到最大事件数: session_id={session.session_id}")
            return True
        
        return False
    
    def close_session(
        self,
        rule_id: int,
        session: SessionWindow,
        mark_processed: bool = True
    ) -> bool:
        """
        关闭会话
        
        Args:
            rule_id: 规则ID
            session: 会话窗口对象
            mark_processed: 是否标记为已处理
            
        Returns:
            是否关闭成功
        """
        window_id = self._make_session_key(rule_id, session.fingerprint, session.session_id)
        
        # 标记已处理
        if mark_processed:
            metadata = {
                'event_count': session.event_count,
                'duration_seconds': session.duration.total_seconds(),
                'start_time': session.start_time.isoformat(),
                'end_time': session.last_event_time.isoformat()
            }
            self.cache.mark_window_processed(rule_id, window_id, metadata)
        
        # 删除状态缓存
        success = self.cache.delete_window_state(rule_id, window_id)
        
        if self.config.VERBOSE_LOGGING:
            logger.debug(
                f"关闭会话: rule={rule_id}, session_id={session.session_id}, "
                f"events={session.event_count}, duration={session.duration}"
            )
        
        return success
    
    def get_active_sessions(
        self,
        rule_id: int,
        fingerprints: Optional[List[str]] = None
    ) -> List[SessionWindow]:
        """
        获取活跃会话列表
        
        注意：由于 Django cache API 限制，此方法需要应用层追踪会话ID
        实际使用中建议在处理器中维护会话列表
        
        Args:
            rule_id: 规则ID
            fingerprints: 指纹列表，None 表示获取所有
            
        Returns:
            活跃会话列表
        """
        # 这是简化实现，生产环境建议使用 Redis 的 SCAN 命令
        logger.warning("get_active_sessions 需要应用层追踪，当前返回空列表")
        return []
    
    def cleanup_expired_sessions(self, rule_id: int) -> int:
        """
        清理过期会话
        
        Args:
            rule_id: 规则ID
            
        Returns:
            清理的会话数量
        """
        # 依赖 TTL 自动过期
        logger.info(f"会话清理依赖 Redis TTL 机制: rule={rule_id}")
        return 0


# 全局管理器实例
_global_manager: Optional[SessionStateManager] = None


def get_session_manager() -> SessionStateManager:
    """获取全局会话管理器实例"""
    global _global_manager
    if _global_manager is None:
        _global_manager = SessionStateManager()
    return _global_manager
