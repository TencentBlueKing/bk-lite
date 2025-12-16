# -- coding: utf-8 --
"""
基础窗口处理器

定义窗口处理器的接口和公共逻辑
"""
from abc import ABC, abstractmethod
from typing import List
import pandas as pd

from apps.alerts.models import CorrelationRules, Alert
from apps.core.logger import alert_logger as logger


class BaseWindowProcessor(ABC):
    """
    窗口处理器基类
    
    职责：
    1. 定义窗口处理接口
    2. 提供公共的处理流程
    3. 协调查询、模板、DuckDB、告警构建
    """
    
    def __init__(self, correlation_rule: CorrelationRules):
        """
        初始化处理器
        
        Args:
            correlation_rule: 关联规则对象
        """
        self.correlation_rule = correlation_rule
        self.rule_id = correlation_rule.id
        self.rule_name = correlation_rule.name
    
    @abstractmethod
    def process(self) -> List[Alert]:
        """
        处理窗口聚合
        
        Returns:
            生成的告警列表
        """
        pass
    
    def _log_processing_start(self) -> None:
        """记录处理开始"""
        logger.info(
            f"开始处理: 规则={self.rule_name}({self.rule_id}), "
            f"窗口={self.correlation_rule.window_type}, "
            f"策略={self.correlation_rule.strategy_type}"
        )
    
    def _log_processing_end(self, alert_count: int, duration_ms: float) -> None:
        """记录处理结束"""
        logger.info(
            f"处理完成: 规则={self.rule_name}, "
            f"生成告警={alert_count}, 耗时={duration_ms:.2f}ms"
        )
    
    def _validate_result(self, result_df: pd.DataFrame) -> bool:
        """
        验证查询结果
        
        Args:
            result_df: 查询结果 DataFrame
            
        Returns:
            True=有效，False=无效
        """
        if result_df.empty:
            logger.debug(f"规则 {self.rule_name} 没有符合条件的聚合结果")
            return False
        
        # 检查必需字段
        required_fields = [
            "fingerprint", "window_id", "event_count",
            "first_event_time", "last_event_time"
        ]
        
        missing_fields = [f for f in required_fields if f not in result_df.columns]
        if missing_fields:
            logger.error(f"查询结果缺少必需字段: {missing_fields}")
            return False
        
        return True
