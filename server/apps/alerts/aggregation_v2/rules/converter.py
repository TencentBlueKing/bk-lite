# -- coding: utf-8 --
"""
规则转换器

将 V1 规则配置转换为 V2 格式（兼容层）
"""
from typing import Dict, Any, List, Optional

from apps.alerts.models import CorrelationRules
from apps.alerts.constants import WindowType, AlertStrategyType
from apps.core.logger import alert_logger as logger


class RuleConverter:
    """
    规则转换器
    
    职责：
    1. 兼容 V1 规则配置格式
    2. 转换为 V2 标准格式
    3. 校验规则完整性
    """
    
    @classmethod
    def convert_rule(cls, correlation_rule: CorrelationRules) -> Dict[str, Any]:
        """
        转换规则配置
        
        Args:
            correlation_rule: 原始规则对象
            
        Returns:
            转换后的规则配置
        """
        converted = {
            "id": correlation_rule.id,
            "name": correlation_rule.name,
            "window_type": correlation_rule.window_type,
            "strategy_type": correlation_rule.strategy_type,
            "enabled": True,  # V2 使用 enabled 替代 is_active
        }
        
        # 转换窗口配置
        window_config = cls._convert_window_config(correlation_rule)
        converted.update(window_config)
        
        # 转换策略配置
        strategy_config = cls._convert_strategy_config(correlation_rule)
        converted.update(strategy_config)
        
        # 校验
        cls._validate_converted_rule(converted)
        
        return converted
    
    @classmethod
    def _convert_window_config(cls, rule: CorrelationRules) -> Dict[str, Any]:
        """转换窗口配置"""
        config = {}
        
        if rule.window_type == WindowType.FIXED:
            config["window_size"] = rule.window_size
            
        elif rule.window_type == WindowType.SLIDING:
            config["window_size"] = rule.window_size
            config["slide_interval"] = rule.slide_interval
            
        elif rule.window_type == WindowType.SESSION:
            config["session_timeout"] = rule.session_timeout
            config["max_window_size"] = rule.max_window_size
        
        return config
    
    @classmethod
    def _convert_strategy_config(cls, rule: CorrelationRules) -> Dict[str, Any]:
        """转换策略配置"""
        config = {}
        
        if rule.strategy_type == AlertStrategyType.THRESHOLD:
            config["threshold_config"] = rule.threshold_config or {}
            
        elif rule.strategy_type == AlertStrategyType.COMPOSITE:
            config["composite_config"] = rule.composite_config or {}
            
        elif rule.strategy_type == AlertStrategyType.FREQUENCY:
            config["frequency_config"] = rule.frequency_config or {}
        
        return config
    
    @classmethod
    def _validate_converted_rule(cls, rule_config: Dict[str, Any]) -> None:
        """
        校验转换后的规则
        
        Args:
            rule_config: 规则配置字典
            
        Raises:
            ValueError: 配置无效
        """
        # 检查必需字段
        required_fields = ["id", "name", "window_type", "strategy_type"]
        for field in required_fields:
            if field not in rule_config:
                raise ValueError(f"规则配置缺少必需字段: {field}")
        
        # 检查窗口配置
        window_type = rule_config["window_type"]
        if window_type == WindowType.FIXED:
            if "window_size" not in rule_config:
                raise ValueError("固定窗口缺少 window_size")
        elif window_type == WindowType.SLIDING:
            if "window_size" not in rule_config or "slide_interval" not in rule_config:
                raise ValueError("滑动窗口缺少 window_size 或 slide_interval")
        elif window_type == WindowType.SESSION:
            if "session_timeout" not in rule_config:
                raise ValueError("会话窗口缺少 session_timeout")
        
        logger.debug(f"规则配置校验通过: {rule_config['name']}")
    
    @classmethod
    def batch_convert_rules(cls, rules: List[CorrelationRules]) -> List[Dict[str, Any]]:
        """
        批量转换规则
        
        Args:
            rules: 规则列表
            
        Returns:
            转换后的规则配置列表
        """
        converted_rules = []
        
        for rule in rules:
            try:
                converted = cls.convert_rule(rule)
                converted_rules.append(converted)
            except Exception as e:
                logger.error(f"规则转换失败: {rule.name}, 错误={e}")
        
        logger.info(f"批量转换完成: 成功={len(converted_rules)}/{len(rules)}")
        
        return converted_rules
