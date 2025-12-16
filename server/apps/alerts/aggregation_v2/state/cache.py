# -- coding: utf-8 --
"""
窗口状态缓存管理

基于 Redis 实现窗口状态的持久化和追踪
"""
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import json

from django.core.cache import caches
from django.utils import timezone

from apps.alerts.aggregation_v2.config import AggregationV2Config
from apps.core.logger import alert_logger as logger


class WindowCache:
    """窗口缓存管理器"""
    
    def __init__(self):
        """初始化缓存"""
        self.cache = caches["redis"]
        self.config = AggregationV2Config
    
    def _make_state_key(self, rule_id: int, window_id: str) -> str:
        """生成窗口状态键"""
        return self.config.WINDOW_STATE_KEY_TEMPLATE.format(
            rule_id=rule_id,
            window_id=window_id
        )
    
    def _make_processed_key(self, rule_id: int, window_id: str) -> str:
        """生成已处理窗口键"""
        return self.config.PROCESSED_WINDOW_KEY_TEMPLATE.format(
            rule_id=rule_id,
            window_id=window_id
        )
    
    def _make_last_exec_key(self, rule_id: int) -> str:
        """生成上次执行时间键"""
        return self.config.LAST_EXECUTION_KEY_TEMPLATE.format(rule_id=rule_id)
    
    def save_window_state(
        self,
        rule_id: int,
        window_id: str,
        state_data: Dict[str, Any],
        ttl: Optional[int] = None
    ) -> bool:
        """
        保存窗口状态
        
        Args:
            rule_id: 规则ID
            window_id: 窗口ID
            state_data: 状态数据
            ttl: 过期时间（秒），默认使用配置值
            
        Returns:
            是否保存成功
            
        Examples:
            >>> cache = WindowCache()
            >>> cache.save_window_state(
            ...     rule_id=123,
            ...     window_id="SLIDING-1733841443-0",
            ...     state_data={"event_count": 5, "last_event_time": 1733841443}
            ... )
            True
        """
        if not self.config.ENABLE_WINDOW_TRACKING:
            return False
        
        try:
            cache_key = self._make_state_key(rule_id, window_id)
            ttl = ttl or self.config.SLIDING_WINDOW_STATE_TTL
            
            # 添加时间戳
            state_data['_saved_at'] = timezone.now().isoformat()
            
            self.cache.set(cache_key, json.dumps(state_data), timeout=ttl)
            
            if self.config.VERBOSE_LOGGING:
                logger.debug(f"保存窗口状态: rule={rule_id}, window={window_id}")
            
            return True
        except Exception as e:
            logger.error(f"保存窗口状态失败: {e}", exc_info=True)
            return False
    
    def get_window_state(
        self,
        rule_id: int,
        window_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        获取窗口状态
        
        Args:
            rule_id: 规则ID
            window_id: 窗口ID
            
        Returns:
            状态数据字典，不存在返回 None
        """
        if not self.config.ENABLE_WINDOW_TRACKING:
            return None
        
        try:
            cache_key = self._make_state_key(rule_id, window_id)
            data = self.cache.get(cache_key)
            
            if data:
                return json.loads(data) if isinstance(data, str) else data
            return None
        except Exception as e:
            logger.error(f"获取窗口状态失败: {e}", exc_info=True)
            return None
    
    def delete_window_state(self, rule_id: int, window_id: str) -> bool:
        """删除窗口状态"""
        try:
            cache_key = self._make_state_key(rule_id, window_id)
            self.cache.delete(cache_key)
            return True
        except Exception as e:
            logger.error(f"删除窗口状态失败: {e}", exc_info=True)
            return False
    
    def mark_window_processed(
        self,
        rule_id: int,
        window_id: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        标记窗口已处理
        
        Args:
            rule_id: 规则ID
            window_id: 窗口ID
            metadata: 附加元数据（如告警数量、处理时间等）
            
        Returns:
            是否标记成功
        """
        if not self.config.ENABLE_WINDOW_TRACKING:
            return False
        
        try:
            cache_key = self._make_processed_key(rule_id, window_id)
            
            data = {
                'processed_at': timezone.now().isoformat(),
                'window_id': window_id,
                'metadata': metadata or {}
            }
            
            # 保存24小时，防止重复处理
            self.cache.set(cache_key, json.dumps(data), timeout=86400)
            
            if self.config.VERBOSE_LOGGING:
                logger.debug(f"标记窗口已处理: rule={rule_id}, window={window_id}")
            
            return True
        except Exception as e:
            logger.error(f"标记窗口已处理失败: {e}", exc_info=True)
            return False
    
    def is_window_processed(self, rule_id: int, window_id: str) -> bool:
        """
        检查窗口是否已处理
        
        Returns:
            True 表示已处理，False 表示未处理
        """
        if not self.config.ENABLE_WINDOW_TRACKING:
            return False
        
        try:
            cache_key = self._make_processed_key(rule_id, window_id)
            return self.cache.get(cache_key) is not None
        except Exception as e:
            logger.error(f"检查窗口处理状态失败: {e}", exc_info=True)
            return False
    
    def update_last_execution(
        self,
        rule_id: int,
        execution_time: Optional[datetime] = None
    ) -> bool:
        """
        更新规则的上次执行时间
        
        Args:
            rule_id: 规则ID
            execution_time: 执行时间，默认当前时间
            
        Returns:
            是否更新成功
        """
        try:
            cache_key = self._make_last_exec_key(rule_id)
            timestamp = (execution_time or timezone.now()).isoformat()
            
            self.cache.set(cache_key, timestamp, timeout=None)  # 永久保存
            return True
        except Exception as e:
            logger.error(f"更新上次执行时间失败: {e}", exc_info=True)
            return False
    
    def get_last_execution(self, rule_id: int) -> Optional[datetime]:
        """
        获取规则的上次执行时间
        
        Args:
            rule_id: 规则ID
            
        Returns:
            上次执行时间，不存在返回 None
        """
        try:
            cache_key = self._make_last_exec_key(rule_id)
            timestamp = self.cache.get(cache_key)
            
            if timestamp:
                if isinstance(timestamp, str):
                    from dateutil import parser
                    return parser.isoparse(timestamp)
                return timestamp
            return None
        except Exception as e:
            logger.error(f"获取上次执行时间失败: {e}", exc_info=True)
            return None
    
    def clear_rule_cache(self, rule_id: int) -> int:
        """
        清除规则的所有缓存
        
        Args:
            rule_id: 规则ID
            
        Returns:
            清除的键数量
        """
        try:
            # Django cache 不支持模式匹配，需要手动追踪键
            # 这里提供基础实现，生产环境建议使用 Redis 原生接口
            cleared = 0
            
            # 清除上次执行时间
            last_exec_key = self._make_last_exec_key(rule_id)
            self.cache.delete(last_exec_key)
            cleared += 1
            
            logger.info(f"清除规则 {rule_id} 的缓存，共 {cleared} 个键")
            return cleared
        except Exception as e:
            logger.error(f"清除规则缓存失败: {e}", exc_info=True)
            return 0
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取缓存统计信息
        
        Returns:
            统计数据字典
        """
        # Django cache API 限制，提供基础统计
        return {
            'cache_backend': str(type(self.cache).__name__),
            'tracking_enabled': self.config.ENABLE_WINDOW_TRACKING,
            'state_ttl': self.config.SLIDING_WINDOW_STATE_TTL,
        }


# 全局缓存实例
_global_cache: Optional[WindowCache] = None


def get_window_cache() -> WindowCache:
    """获取全局窗口缓存实例"""
    global _global_cache
    if _global_cache is None:
        _global_cache = WindowCache()
    return _global_cache
