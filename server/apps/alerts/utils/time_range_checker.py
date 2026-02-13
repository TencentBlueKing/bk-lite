# -- coding: utf-8 --
# @File: time_range_checker.py
# @Time: 2025/2/9
# @Author: Refactored from shield.py and assignment.py
"""
通用时间范围检查工具

用于检查指定时间是否在配置的时间范围内。
支持四种时间类型：
- one: 一次性时间范围
- day: 每日时间范围
- week: 每周时间范围
- month: 每月时间范围
"""

import datetime
from typing import Dict, Any, Optional

from django.utils import timezone

from apps.core.logger import alert_logger as logger


class TimeRangeChecker:
    """
    时间范围检查器

    用于检查指定时间是否在配置的时间范围内。
    支持一次性时间范围、每日、每周、每月时间范围。
    """

    def __init__(self, config: Dict[str, Any], check_time: Optional[datetime.datetime] = None):
        """
        初始化时间范围检查器

        Args:
            config: 时间配置字典，包含以下字段：
                - type: 时间类型，支持 "one", "day", "week", "month"
                - start_time: 开始时间
                - end_time: 结束时间
                - week_month: 周/月配置（week类型时为周几列表，month类型时为日期列表）
            check_time: 要检查的时间，如果为None则使用当前时间
        """
        self.config = config or {}
        self.check_time = check_time if check_time else timezone.now()

    def is_in_range(self) -> bool:
        """
        检查时间是否在配置的时间范围内

        Returns:
            bool: 是否在时间范围内
        """
        if not self.config:
            return True

        time_type = self.config.get("type", "one")

        try:
            if time_type == "one":
                return self._check_one_time_range()
            elif time_type == "day":
                return self._check_day_range()
            elif time_type == "week":
                return self._check_week_range()
            elif time_type == "month":
                return self._check_month_range()
            else:
                logger.warning(f"Unknown time type: {time_type}")
                return True

        except ValueError as e:
            logger.error(f"Error parsing time format: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Error checking time range: {str(e)}")
            return False

    def _check_one_time_range(self) -> bool:
        """检查一次性时间范围"""
        start_time_str = self.config.get("start_time")
        end_time_str = self.config.get("end_time")

        if not start_time_str or not end_time_str:
            logger.warning("One-time range missing start_time or end_time")
            return False

        start_time = datetime.datetime.strptime(start_time_str, "%Y-%m-%d %H:%M:%S")
        end_time = datetime.datetime.strptime(end_time_str, "%Y-%m-%d %H:%M:%S")

        # 转换为带时区的时间
        start_time = timezone.make_aware(start_time)
        end_time = timezone.make_aware(end_time)

        return start_time <= self.check_time <= end_time

    def _check_day_range(self) -> bool:
        """检查每日时间范围"""
        start_time_str = self.config.get("start_time")
        end_time_str = self.config.get("end_time")

        if not start_time_str or not end_time_str:
            logger.warning("Day-time range missing start_time or end_time")
            return False

        check_time_str = self.check_time.strftime("%H:%M:%S")
        return start_time_str <= check_time_str <= end_time_str

    def _check_week_range(self) -> bool:
        """检查每周时间范围"""
        week_day = self.config.get("week_month")
        current_weekday = str(self.check_time.weekday() + 1)  # Monday is 1

        # 检查是否是指定的周几
        if not self._is_day_matched(week_day, current_weekday):
            return False

        # 检查时间范围
        return self._check_time_of_day_range()

    def _check_month_range(self) -> bool:
        """检查每月时间范围"""
        month_day = self.config.get("week_month")
        current_day = str(self.check_time.day)

        # 检查是否是指定的日期
        if not self._is_day_matched(month_day, current_day):
            return False

        # 检查时间范围
        return self._check_time_of_day_range()

    def _is_day_matched(self, day_config, current_day: str) -> bool:
        """
        检查当前日期是否匹配配置

        Args:
            day_config: 日期配置（可能是列表或字符串）
            current_day: 当前日期字符串

        Returns:
            bool: 是否匹配
        """
        if day_config is None:
            return True

        # 处理列表类型（week_month 可能是整数列表）
        if isinstance(day_config, list):
            return int(current_day) in day_config

        # 处理字符串类型
        if isinstance(day_config, str):
            return current_day in day_config

        return False

    def _check_time_of_day_range(self) -> bool:
        """
        检查当天的时间范围

        Returns:
            bool: 是否在时间范围内
        """
        start_time_str = self.config.get("start_time")
        end_time_str = self.config.get("end_time")

        # 如果没有配置时间范围，则只要日期匹配就符合条件
        if not start_time_str or not end_time_str:
            return True

        # 只比较时间部分（HH:MM:SS）
        start_time_str = self._extract_time_part(start_time_str)
        end_time_str = self._extract_time_part(end_time_str)

        check_time_str = self.check_time.strftime("%H:%M:%S")
        return start_time_str <= check_time_str <= end_time_str

    @staticmethod
    def _extract_time_part(time_str: str) -> str:
        """
        从时间字符串中提取时间部分

        Args:
            time_str: 时间字符串（可能包含日期）

        Returns:
            str: 时间部分（HH:MM:SS格式）
        """
        if len(time_str) > 8:  # 包含日期的格式
            if " " in time_str:
                return time_str.split(" ")[1]
            return time_str[-8:]
        return time_str


def check_time_range(
    config: Dict[str, Any],
    check_time: Optional[datetime.datetime] = None
) -> bool:
    """
    检查指定时间是否在配置的时间范围内

    便捷函数，用于快速调用时间范围检查。

    Args:
        config: 时间配置字典
        check_time: 要检查的时间，如果为None则使用当前时间

    Returns:
        bool: 是否在时间范围内
    """
    checker = TimeRangeChecker(config, check_time)
    return checker.is_in_range()
