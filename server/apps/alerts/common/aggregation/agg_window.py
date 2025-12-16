# -- coding: utf-8 --
# @File: agg_window.py
# @Time: 2025/7/4 14:37
# @Author: windyzhao

"""
聚合窗口处理器模块
包含滑动窗口、固定窗口、会话窗口的独立处理器
"""
from typing import List, Tuple

from apps.alerts.common.aggregation.window_processor.base import BaseWindowProcessor
from apps.alerts.common.aggregation.window_processor.sliding import SlidingWindowProcessor
from apps.alerts.common.aggregation.window_processor.fixed import FixedWindowProcessor
from apps.alerts.common.aggregation.window_processor.session import SessionWindowAggProcessor
from apps.alerts.models import CorrelationRules


class WindowProcessorFactory:
    """窗口处理器工厂类"""

    _processors = {
        'sliding': SlidingWindowProcessor,
        'fixed': FixedWindowProcessor,
        'session': SessionWindowAggProcessor  # 修复：使用重命名的类
    }

    @classmethod
    def create_processor(cls, window_type: str, window_size: str = "10min") -> BaseWindowProcessor:
        """
        创建窗口处理器实例
        
        Args:
            window_type: 窗口类型 (sliding/fixed/session)
            window_size: 窗口大小（仅用于初始化，实际处理时会根据规则动态调整）
            
        Returns:
            窗口处理器实例
            
        Raises:
            ValueError: 不支持的窗口类型
        """
        if window_type not in cls._processors:
            raise ValueError(f"不支持的窗口类型: {window_type}")

        processor_class = cls._processors[window_type]
        return processor_class(window_size=window_size)

    @classmethod
    def get_supported_window_types(cls) -> List[str]:
        """获取支持的窗口类型列表"""
        return list(cls._processors.keys())

    @classmethod
    def process_window_type_rules(cls, window_type: str, rules: List[CorrelationRules]) -> Tuple[int, int]:
        """
        便捷方法：直接处理指定窗口类型的规则
        
        Args:
            window_type: 窗口类型
            rules: 规则列表（每个规则有自己的窗口大小配置）
            
        Returns:
            Tuple[int, int]: (新建告警数, 更新告警数)
        """
        # 创建处理器时使用默认窗口大小，实际处理时会根据每个规则的配置动态调整
        processor = cls.create_processor(window_type)
        return processor.process_rules(rules)
