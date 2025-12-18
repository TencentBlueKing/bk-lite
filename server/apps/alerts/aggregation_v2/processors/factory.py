# -- coding: utf-8 --
"""
窗口处理器工厂

创建和管理窗口处理器实例
"""
from typing import Type

from apps.alerts.models import CorrelationRules
from apps.alerts.constants import WindowType
from apps.alerts.aggregation_v2.processors.base import BaseWindowProcessor
from apps.core.logger import alert_logger as logger


class WindowProcessorFactory:
    """
    窗口处理器工厂
    
    职责：
    1. 根据窗口类型创建处理器
    2. 处理器缓存和复用
    3. 处理器注册管理
    """
    
    # 处理器注册表
    _processors = {}
    
    @classmethod
    def register(cls, window_type: str, processor_class: Type[BaseWindowProcessor]):
        """
        注册处理器
        
        Args:
            window_type: 窗口类型
            processor_class: 处理器类
        """
        cls._processors[window_type] = processor_class
        logger.debug(f"注册窗口处理器: {window_type} -> {processor_class.__name__}")
    
    @classmethod
    def create(cls, correlation_rule: CorrelationRules) -> BaseWindowProcessor:
        """
        创建处理器实例
        
        Args:
            correlation_rule: 关联规则对象
            
        Returns:
            窗口处理器实例
            
        Raises:
            ValueError: 未知的窗口类型
        """
        window_type = correlation_rule.window_type
        
        if window_type not in cls._processors:
            # 懒加载处理器类
            cls._lazy_load_processors()
        
        if window_type not in cls._processors:
            raise ValueError(f"不支持的窗口类型: {window_type}")
        
        processor_class = cls._processors[window_type]
        processor = processor_class(correlation_rule)
        
        logger.debug(
            f"创建窗口处理器: 规则={correlation_rule.name}, "
            f"类型={window_type}, 处理器={processor_class.__name__}"
        )
        
        return processor
    
    @classmethod
    def _lazy_load_processors(cls):
        """懒加载处理器类（避免循环导入）"""
        if not cls._processors:
            # 注意：这里使用懒加载避免模块初始化时的循环依赖
            from apps.alerts.aggregation_v2.processors.fixed import FixedWindowProcessor
            from apps.alerts.aggregation_v2.processors.sliding import SlidingWindowProcessor
            from apps.alerts.aggregation_v2.processors.session import SessionWindowProcessor
            
            cls.register(WindowType.FIXED, FixedWindowProcessor)
            cls.register(WindowType.SLIDING, SlidingWindowProcessor)
            cls.register(WindowType.SESSION, SessionWindowProcessor)
