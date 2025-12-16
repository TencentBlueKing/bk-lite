# -- coding: utf-8 --
"""
时间工具函数

提供时间相关的辅助功能
"""
from datetime import datetime, timedelta
from typing import Tuple
from django.utils import timezone

from datetime import timedelta


class WindowCalculator:
    """窗口时间计算器"""

    @staticmethod
    def parse_time_str(time_str: str) -> timedelta:
        """解析时间字符串为timedelta对象"""
        if time_str.endswith('min'):
            return timedelta(minutes=int(time_str[:-3]))
        elif time_str.endswith('h'):
            return timedelta(hours=int(time_str[:-1]))
        elif time_str.endswith('d'):
            return timedelta(days=int(time_str[:-1]))
        elif time_str.endswith('s'):
            return timedelta(seconds=int(time_str[:-1]))
        else:
            # 默认按分钟处理
            return timedelta(minutes=int(time_str))


class TimeUtils:
    """时间工具类"""

    @staticmethod
    def parse_time_str(time_str: str) -> timedelta:
        """
        解析时间字符串为 timedelta
        
        Args:
            time_str: 时间字符串，如 "5min", "1h", "30s"
            
        Returns:
            timedelta 对象
            
        Examples:
            >>> TimeUtils.parse_time_str("5min")
            timedelta(minutes=5)
            >>> TimeUtils.parse_time_str("2h")
            timedelta(hours=2)
        """
        # 复用现有的 WindowCalculator
        return WindowCalculator.parse_time_str(time_str)

    @staticmethod
    def parse_time_str_to_seconds(time_str: str) -> int:
        """
        解析时间字符串为秒数
        
        Args:
            time_str: 时间字符串，如 "5min", "1h", "30s"
            
        Returns:
            秒数（整数）
            
        Examples:
            >>> TimeUtils.parse_time_str_to_seconds("5min")
            300
            >>> TimeUtils.parse_time_str_to_seconds("1h")
            3600
        """
        delta = TimeUtils.parse_time_str(time_str)
        return int(delta.total_seconds())

    @staticmethod
    def get_current_time() -> datetime:
        """
        获取当前时间（带时区）
        
        Returns:
            当前时间的 datetime 对象
        """
        return timezone.now()

    @staticmethod
    def align_to_minute(dt: datetime) -> datetime:
        """
        对齐到分钟（去掉秒和微秒）
        
        Args:
            dt: 原始时间
            
        Returns:
            对齐后的时间
            
        Examples:
            >>> dt = datetime(2025, 12, 10, 14, 37, 45, 123456)
            >>> TimeUtils.align_to_minute(dt)
            datetime(2025, 12, 10, 14, 37, 0, 0)
        """
        return dt.replace(second=0, microsecond=0)

    @staticmethod
    def align_to_hour(dt: datetime) -> datetime:
        """
        对齐到小时（去掉分钟、秒和微秒）
        
        Args:
            dt: 原始时间
            
        Returns:
            对齐后的时间
        """
        return dt.replace(minute=0, second=0, microsecond=0)

    @staticmethod
    def align_to_day(dt: datetime) -> datetime:
        """
        对齐到天（去掉时分秒）
        
        Args:
            dt: 原始时间
            
        Returns:
            对齐后的时间
        """
        return dt.replace(hour=0, minute=0, second=0, microsecond=0)

    @staticmethod
    def align_to_window(
            dt: datetime,
            window_size_seconds: int,
            alignment: str = 'minute'
    ) -> datetime:
        """
        将时间对齐到窗口边界
        
        Args:
            dt: 原始时间
            window_size_seconds: 窗口大小（秒）
            alignment: 对齐方式 ('second', 'minute', 'hour', 'day')
            
        Returns:
            对齐后的时间
            
        Examples:
            >>> dt = datetime(2025, 12, 11, 14, 37, 45)
            >>> TimeUtils.align_to_window(dt, 300, 'minute')  # 5分钟窗口
            datetime(2025, 12, 11, 14, 35, 0, 0)
            
            >>> TimeUtils.align_to_window(dt, 3600, 'hour')  # 1小时窗口
            datetime(2025, 12, 11, 14, 0, 0, 0)
        """
        # 先根据对齐方式进行基础对齐
        if alignment == 'second':
            aligned = dt.replace(microsecond=0)
        elif alignment == 'minute':
            aligned = dt.replace(second=0, microsecond=0)
        elif alignment == 'hour':
            aligned = dt.replace(minute=0, second=0, microsecond=0)
        elif alignment == 'day':
            aligned = dt.replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            aligned = dt.replace(second=0, microsecond=0)

        # 如果窗口大小大于对齐单位，进一步对齐到窗口边界
        if window_size_seconds > 0:
            # 转换为时间戳
            timestamp = aligned.timestamp()
            # 对齐到窗口边界（向下取整）
            aligned_timestamp = (timestamp // window_size_seconds) * window_size_seconds
            # 转换回 datetime（保持时区）
            from datetime import datetime as dt_class
            if dt.tzinfo:
                aligned = dt_class.fromtimestamp(aligned_timestamp, tz=dt.tzinfo)
            else:
                aligned = dt_class.fromtimestamp(aligned_timestamp)

        return aligned

    @staticmethod
    def calculate_window_range(
            current_time: datetime,
            window_size: timedelta,
            window_type: str = 'fixed'
    ) -> Tuple[datetime, datetime]:
        """
        计算窗口的时间范围
        
        Args:
            current_time: 当前时间
            window_size: 窗口大小
            window_type: 窗口类型
            
        Returns:
            (start_time, end_time)
        """
        if window_type == 'fixed':
            # 固定窗口：向前推2倍窗口大小
            start_time = current_time - (window_size * 2)
            end_time = current_time
        elif window_type == 'sliding':
            # 滑动窗口：窗口大小 + 缓冲
            start_time = current_time - window_size - timedelta(minutes=1)
            end_time = current_time
        else:
            # 默认
            start_time = current_time - window_size
            end_time = current_time

        return start_time, end_time

    @staticmethod
    def format_duration(seconds: float) -> str:
        """
        格式化持续时间为人类可读格式
        
        Args:
            seconds: 秒数
            
        Returns:
            格式化的字符串
            
        Examples:
            >>> TimeUtils.format_duration(65.5)
            "1m 5.5s"
            >>> TimeUtils.format_duration(3661)
            "1h 1m 1s"
        """
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60

        parts = []
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")
        if secs > 0 or not parts:
            parts.append(f"{secs:.1f}s")

        return " ".join(parts)
