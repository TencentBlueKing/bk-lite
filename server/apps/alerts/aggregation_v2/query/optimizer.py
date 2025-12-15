# -- coding: utf-8 --
"""
查询优化器

提供查询性能优化策略
"""
from typing import Dict, Optional
from datetime import datetime

from django.core.cache import cache
from django.utils import timezone

from apps.core.logger import alert_logger as logger
from apps.alerts.aggregation_v2.config import AggregationV2Config


class QueryOptimizer:
    """
    查询优化器
    
    职责：
    1. 查询结果缓存（避免重复查询）
    2. 智能调度（避免空运行）
    3. 批量查询（减少数据库连接）
    """

    # 缓存键前缀
    CACHE_PREFIX = "agg_v2:query:"

    @classmethod
    def should_skip_query(
            cls,
            rule_id: int,
            current_time: Optional[datetime] = None
    ) -> bool:
        """
        判断是否可以跳过查询（智能调度优化）
        
        策略：
        1. 检查自上次查询以来是否有新事件
        2. 如果没有新事件，可以跳过查询
        
        Args:
            rule_id: 规则 ID
            current_time: 当前时间
            
        Returns:
            True=可以跳过，False=需要查询
        """
        return False
        if not AggregationV2Config.ENABLE_SMART_SCHEDULING:
            return False

        if current_time is None:
            current_time = timezone.now()

        # 获取上次查询时间
        cache_key = f"{cls.CACHE_PREFIX}last_query:{rule_id}"
        last_query_time = cache.get(cache_key)

        if last_query_time is None:
            # 首次查询，不能跳过
            return False

        # 检查是否有新事件
        from apps.alerts.aggregation_v2.query.strategy import EventQueryStrategy
        new_event_count = EventQueryStrategy.count_new_events(
            since=last_query_time,
            until=current_time
        )

        if new_event_count == 0:
            logger.debug(
                f"规则 {rule_id} 自 {last_query_time} 以来没有新事件，跳过查询"
            )
            return True

        logger.debug(
            f"规则 {rule_id} 发现 {new_event_count} 个新事件，执行查询"
        )
        return False

    @classmethod
    def update_last_query_time(
            cls,
            rule_id: int,
            query_time: Optional[datetime] = None
    ) -> None:
        """
        更新上次查询时间（用于智能调度）
        
        Args:
            rule_id: 规则 ID
            query_time: 查询时间（默认当前时间）
        """
        if query_time is None:
            query_time = timezone.now()

        cache_key = f"{cls.CACHE_PREFIX}last_query:{rule_id}"
        cache.set(
            cache_key,
            query_time,
            timeout=AggregationV2Config.QUERY_CACHE_TTL
        )

    @classmethod
    def cache_query_result(
            cls,
            cache_key: str,
            result: any,
            ttl: Optional[int] = None
    ) -> None:
        """
        缓存查询结果
        
        Args:
            cache_key: 缓存键
            result: 查询结果
            ttl: 过期时间（秒，默认使用配置值）
        """
        if ttl is None:
            ttl = AggregationV2Config.QUERY_CACHE_TTL

        full_key = f"{cls.CACHE_PREFIX}{cache_key}"
        cache.set(full_key, result, timeout=ttl)

    @classmethod
    def get_cached_result(cls, cache_key: str) -> Optional[any]:
        """
        获取缓存的查询结果
        
        Args:
            cache_key: 缓存键
            
        Returns:
            缓存的结果，如果不存在返回 None
        """
        full_key = f"{cls.CACHE_PREFIX}{cache_key}"
        return cache.get(full_key)

    @classmethod
    def clear_cache_for_rule(cls, rule_id: int) -> None:
        """
        清除规则的所有缓存
        
        Args:
            rule_id: 规则 ID
        """
        # 清除上次查询时间
        cache_key = f"{cls.CACHE_PREFIX}last_query:{rule_id}"
        cache.delete(cache_key)

        logger.info(f"已清除规则 {rule_id} 的查询缓存")

    @classmethod
    def build_query_stats(
            cls,
            rule_id: int,
            event_count: int,
            query_duration: float,
            window_type: str
    ) -> Dict:
        """
        构建查询统计信息
        
        Args:
            rule_id: 规则 ID
            event_count: 查询到的事件数量
            query_duration: 查询耗时（毫秒）
            window_type: 窗口类型
            
        Returns:
            统计信息字典
        """
        stats = {
            "rule_id": rule_id,
            "event_count": event_count,
            "query_duration_ms": query_duration,
            "window_type": window_type,
            "timestamp": timezone.now().isoformat()
        }

        # 记录到 Redis（用于监控）
        if AggregationV2Config.ENABLE_PERFORMANCE_MONITORING:
            cache_key = f"query_stats:{rule_id}:{timezone.now().strftime('%Y%m%d%H%M')}"
            cls.cache_query_result(cache_key, stats, ttl=3600)  # 保留1小时

        return stats
