# -- coding: utf-8 --
# @File: util.py
# @Time: 2025/9/28 14:30
# @Author: windyzhao
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
