# -- coding: utf-8 --
"""
性能指标收集

提供性能监控和指标收集功能
"""
import time
from typing import Dict, Any, Optional
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime

from apps.core.logger import alert_logger as logger


@dataclass
class PerformanceMetric:
    """性能指标数据类"""
    
    name: str
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    duration: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def finish(self):
        """完成计时"""
        self.end_time = time.time()
        self.duration = self.end_time - self.start_time
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'name': self.name,
            'duration_seconds': self.duration,
            'start_time': datetime.fromtimestamp(self.start_time).isoformat(),
            'end_time': datetime.fromtimestamp(self.end_time).isoformat() if self.end_time else None,
            'metadata': self.metadata
        }


class PerformanceMonitor:
    """性能监控器（可直接作为上下文管理器使用）"""
    
    def __init__(self, name: str = None, enabled: bool = True, **metadata):
        """
        初始化监控器
        
        Args:
            name: 指标名称（用于上下文管理器模式）
            enabled: 是否启用监控
            **metadata: 附加元数据
        """
        self.enabled = enabled
        self.metrics: Dict[str, PerformanceMetric] = {}
        
        # 用于上下文管理器模式
        self._current_name = name
        self._current_metadata = metadata
        self._current_metric: Optional[PerformanceMetric] = None
        self._start_time: Optional[float] = None
    
    def __enter__(self):
        """进入上下文"""
        if not self.enabled:
            return self
        
        self._start_time = time.time()
        
        if self._current_name:
            self._current_metric = PerformanceMetric(
                name=self._current_name,
                metadata=self._current_metadata
            )
            self.metrics[self._current_name] = self._current_metric
        
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出上下文"""
        if not self.enabled:
            return False
        
        if self._current_metric:
            self._current_metric.finish()
            self._log_metric(self._current_metric)
        
        return False
    
    @property
    def elapsed_ms(self) -> float:
        """获取耗时（毫秒）"""
        if self._start_time is None:
            return 0.0
        
        if self._current_metric and self._current_metric.duration:
            return self._current_metric.duration * 1000
        
        # 如果还在运行中，返回当前耗时
        return (time.time() - self._start_time) * 1000
    
    @contextmanager
    def measure(self, name: str, **metadata):
        """
        性能测量上下文管理器
        
        Args:
            name: 指标名称
            **metadata: 附加元数据
            
        Examples:
            >>> monitor = PerformanceMonitor()
            >>> with monitor.measure("query_events", rule_id="rule-123"):
            ...     # 执行查询
            ...     pass
        """
        if not self.enabled:
            yield None
            return
        
        metric = PerformanceMetric(name=name, metadata=metadata)
        self.metrics[name] = metric
        
        try:
            yield metric
        finally:
            metric.finish()
            self._log_metric(metric)
    
    def _log_metric(self, metric: PerformanceMetric):
        """记录指标日志"""
        from apps.alerts.aggregation_v2.utils.time_utils import TimeUtils
        
        duration_str = TimeUtils.format_duration(metric.duration)
        metadata_str = ", ".join(f"{k}={v}" for k, v in metric.metadata.items())
        
        log_message = f"[性能] {metric.name}: {duration_str}"
        if metadata_str:
            log_message += f" ({metadata_str})"
        
        logger.info(log_message)
    
    def get_summary(self) -> Dict[str, Any]:
        """
        获取性能摘要
        
        Returns:
            包含所有指标的字典
        """
        return {
            name: metric.to_dict()
            for name, metric in self.metrics.items()
        }
    
    def reset(self):
        """重置所有指标"""
        self.metrics.clear()


# 全局监控实例（可选）
_global_monitor: Optional[PerformanceMonitor] = None


def get_global_monitor() -> PerformanceMonitor:
    """获取全局监控实例"""
    global _global_monitor
    if _global_monitor is None:
        from apps.alerts.aggregation_v2.config import AggregationV2Config
        _global_monitor = PerformanceMonitor(
            enabled=AggregationV2Config.ENABLE_PERFORMANCE_MONITORING
        )
    return _global_monitor


@contextmanager
def measure_performance(name: str, **metadata):
    """
    便捷的性能测量装饰器
    
    Args:
        name: 指标名称
        **metadata: 附加元数据
        
    Examples:
        >>> with measure_performance("process_rules", window_type="fixed"):
        ...     # 执行处理
        ...     pass
    """
    monitor = get_global_monitor()
    with monitor.measure(name, **metadata) as metric:
        yield metric
