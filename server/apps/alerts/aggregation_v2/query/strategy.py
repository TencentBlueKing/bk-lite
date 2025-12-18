# -- coding: utf-8 --
"""
事件查询策略

根据窗口类型智能确定查询时间范围和优化查询
"""
from datetime import datetime, timedelta
from typing import Tuple, Optional
import pandas as pd

from django.utils import timezone

from apps.alerts.models import Event, CorrelationRules
from apps.alerts.constants import EventStatus, WindowType
from apps.alerts.aggregation_v2.utils.time_utils import TimeUtils
from apps.alerts.aggregation_v2.utils.fingerprint import FingerprintGenerator
from apps.alerts.aggregation_v2.config import AggregationV2Config
from apps.core.logger import alert_logger as logger


class EventQueryStrategy:
    """
    事件查询策略
    
    职责：
    1. 根据窗口类型计算合适的查询时间范围
    2. 优化查询性能（索引、批量、缓存）
    3. 提供增量查询支持
    """

    # 标准事件字段列表
    EVENT_FIELDS = [
        "event_id", "external_id", "item", "received_at", "status", "level",
        "source__name", "source_id", "title", "rule_id", "description",
        "resource_id", "resource_type", "resource_name", "value",
        "start_time", "end_time", "labels"
    ]

    @classmethod
    def calculate_query_range(
            cls,
            correlation_rule: CorrelationRules,
            current_time: Optional[datetime] = None
    ) -> Tuple[datetime, datetime]:
        """
        计算查询时间范围
        
        策略：
        1. 固定窗口：查询 2 × 窗口大小（包含未完成窗口 + 上一个完整窗口）
        2. 滑动窗口：查询 窗口大小 + 滑动间隔（包含所有重叠窗口）
        3. 会话窗口：查询 max_window_size（历史会话检查）
        
        Args:
            correlation_rule: 关联规则对象
            current_time: 当前时间（默认使用 timezone.now()）
            
        Returns:
            (start_time, end_time) 查询时间范围
            
        Examples:
            >>> rule = CorrelationRules.objects.get(id=1)
            >>> start, end = EventQueryStrategy.calculate_query_range(rule)
            >>> print(f"查询范围: {start} ~ {end}")
        """
        if current_time is None:
            current_time = timezone.now()

        window_type = correlation_rule.window_type

        if window_type == WindowType.FIXED:
            # 固定窗口：查询 2 倍窗口大小
            window_delta = TimeUtils.parse_time_str(correlation_rule.window_size)
            buffer_multiplier = AggregationV2Config.FIXED_WINDOW_BUFFER_MULTIPLIER
            start_time = current_time - (window_delta * buffer_multiplier)
            end_time = current_time

            logger.debug(
                f"固定窗口查询范围: {start_time} ~ {end_time} "
                f"(窗口={correlation_rule.window_size})"
            )

        elif window_type == WindowType.SLIDING:
            # 滑动窗口：查询 窗口大小 + 滑动间隔
            window_delta = TimeUtils.parse_time_str(correlation_rule.window_size)
            slide_delta = TimeUtils.parse_time_str(correlation_rule.slide_interval)

            start_time = current_time - window_delta - slide_delta
            end_time = current_time

            logger.debug(
                f"滑动窗口查询范围: {start_time} ~ {end_time} "
                f"(窗口={correlation_rule.window_size}, 滑动={correlation_rule.slide_interval})"
            )

        elif window_type == WindowType.SESSION:
            # 会话窗口：查询 max_window_size 或 2 倍 session_timeout
            if correlation_rule.max_window_size:
                max_delta = TimeUtils.parse_time_str(correlation_rule.max_window_size)
            else:
                # 如果没有配置，使用 2 倍 session_timeout
                timeout_delta = TimeUtils.parse_time_str(correlation_rule.session_timeout)
                max_delta = timeout_delta * 2

            start_time = current_time - max_delta
            end_time = current_time

            logger.debug(
                f"会话窗口查询范围: {start_time} ~ {end_time} "
                f"(最大窗口={correlation_rule.max_window_size or '2×timeout'})"
            )

        else:
            # 未知窗口类型，使用默认策略
            logger.warning(f"未知窗口类型 {window_type}，使用默认查询范围（1小时）")
            start_time = current_time - timedelta(hours=1)
            end_time = current_time

        return start_time, end_time

    @classmethod
    def get_events_for_correlation_rule(
            cls,
            correlation_rule: CorrelationRules,
            current_time: Optional[datetime] = None,
            include_processed: bool = False
    ) -> pd.DataFrame:
        """
        根据关联规则查询事件数据
        
        优化点：
        1. 只查询必要的时间范围
        2. 只查询未处理的事件
        3. 排除已屏蔽的事件
        4. 使用 select_related 减少 N+1 查询
        5. 添加必要的索引提示
        
        Args:
            correlation_rule: 关联规则对象
            current_time: 当前时间（默认使用 timezone.now()）
            include_processed: 是否包含已处理的事件
            
        Returns:
            包含事件数据的 DataFrame
            
        Examples:
            >>> rule = CorrelationRules.objects.get(id=1)
            >>> events_df = EventQueryStrategy.get_events_for_correlation_rule(rule)
            >>> print(f"查询到 {len(events_df)} 个事件")
        """
        if current_time is None:
            current_time = timezone.now()

        # 1. 计算查询范围
        start_time, end_time = cls.calculate_query_range(correlation_rule, current_time)

        # 2. 构建基础查询
        queryset = Event.objects.filter(
            received_at__gte=start_time,
            received_at__lt=end_time,
            source__is_active=True,
        )

        # 3. 过滤条件
        if not include_processed:
            # 只查询未处理的事件
            queryset = queryset.filter(status=EventStatus.RECEIVED)

        # 排除已屏蔽的事件
        queryset = queryset.exclude(status=EventStatus.SHIELD)

        # 注意：不排除已关联告警的事件，因为一个事件可以触发多个告警规则

        # 4. 优化查询
        queryset = queryset.select_related('source').values(*cls.EVENT_FIELDS)

        # 5. 执行查询
        logger.info(
            f"查询事件: 规则={correlation_rule.name}, "
            f"时间范围={start_time} ~ {end_time}"
        )

        events_list = list(queryset)

        # 6. 转换为 DataFrame
        events_df = pd.DataFrame(events_list)

        if events_df.empty:
            logger.info(
                f"规则 {correlation_rule.name} 在时间范围内没有事件"
            )
            return events_df

        # 7. 格式化 DataFrame
        events_df = cls._format_events_dataframe(events_df)

        logger.info(
            f"规则 {correlation_rule.name} 查询到 {len(events_df)} 个事件"
        )

        return events_df

    @classmethod
    def get_incremental_events(
            cls,
            correlation_rule: CorrelationRules,
            last_query_time: datetime,
            current_time: Optional[datetime] = None
    ) -> pd.DataFrame:
        """
        获取增量事件（自上次查询以来的新事件）
        
        用于滑动窗口的增量计算优化
        
        Args:
            correlation_rule: 关联规则对象
            last_query_time: 上次查询时间
            current_time: 当前时间
            
        Returns:
            增量事件的 DataFrame
        """
        if current_time is None:
            current_time = timezone.now()

        logger.info(
            f"增量查询: 规则={correlation_rule.name}, "
            f"时间范围={last_query_time} ~ {current_time}"
        )

        # 构建增量查询
        queryset = Event.objects.filter(
            received_at__gte=last_query_time,
            received_at__lt=current_time,
            source__is_active=True,
            status=EventStatus.RECEIVED
        ).select_related('source').values(*cls.EVENT_FIELDS)

        events_list = list(queryset)
        events_df = pd.DataFrame(events_list)

        if events_df.empty:
            logger.debug(f"规则 {correlation_rule.name} 没有增量事件")
            return events_df

        # 格式化
        events_df = cls._format_events_dataframe(events_df)

        logger.info(
            f"规则 {correlation_rule.name} 查询到 {len(events_df)} 个增量事件"
        )

        return events_df

    @classmethod
    def _format_events_dataframe(cls, events_df: pd.DataFrame) -> pd.DataFrame:
        """
        格式化事件 DataFrame
        
        添加派生字段：
        - alert_source: 告警源名称
        - fingerprint: 事件指纹
        - level: 转换为整数
        
        Args:
            events_df: 原始事件 DataFrame
            
        Returns:
            格式化后的 DataFrame
        """
        if events_df.empty:
            return events_df

        # 添加告警源字段
        events_df['alert_source'] = events_df['source__name']

        # 添加指纹字段 - 只传递必要的字段,避免字段名不匹配问题
        events_df['fingerprint'] = events_df.apply(
            lambda row: FingerprintGenerator.generate_event_fingerprint({
                "item": row["item"],
                "resource_id": row["resource_id"],
                "resource_type": row["resource_type"],
                "alert_source": row["alert_source"]  # 使用已添加的 alert_source 字段
            }),
            axis=1
        )

        # 转换 level 为整数
        events_df["level"] = events_df["level"].apply(lambda x: int(x))

        return events_df

    @classmethod
    def count_new_events(
            cls,
            since: datetime,
            until: Optional[datetime] = None
    ) -> int:
        """
        统计新事件数量（快速查询，用于判断是否需要处理）
        
        Args:
            since: 起始时间
            until: 结束时间（默认当前时间）
            
        Returns:
            新事件数量
        """
        if until is None:
            until = timezone.now()

        count = Event.objects.filter(
            received_at__gte=since,
            received_at__lt=until,
            status=EventStatus.RECEIVED
        ).count()

        return count
