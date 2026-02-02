# -- coding: utf-8 --
"""
规则适配器

提供规则的高级适配功能
"""
from typing import Dict, Any, List, Optional
from datetime import datetime

from apps.alerts.models import CorrelationRules
from apps.alerts.aggregation_v2.rules.converter import RuleConverter
from apps.core.logger import alert_logger as logger


class RuleAdapter:
    """
    规则适配器
    
    职责：
    1. 规则筛选和分组
    2. 规则优先级排序
    3. 规则依赖解析
    """
    
    @classmethod
    def get_active_rules(
        cls,
        window_type: Optional[str] = None,
        strategy_type: Optional[str] = None
    ) -> List[CorrelationRules]:
        """
        获取活跃的规则
        
        Args:
            window_type: 窗口类型过滤（可选）
            strategy_type: 策略类型过滤（可选）
            
        Returns:
            活跃规则列表
        """
        queryset = CorrelationRules.objects.all()
        
        if window_type:
            queryset = queryset.filter(window_type=window_type)
        
        if strategy_type:
            queryset = queryset.filter(strategy_type=strategy_type)
        
        rules = list(queryset.order_by('id'))
        
        logger.info(
            f"获取活跃规则: 总数={len(rules)}, "
            f"窗口={window_type or '全部'}, 策略={strategy_type or '全部'}"
        )
        
        return rules
    
    @classmethod
    def group_rules_by_window_type(
        cls,
        rules: Optional[List[CorrelationRules]] = None
    ) -> Dict[str, List[CorrelationRules]]:
        """
        按窗口类型分组规则
        
        Args:
            rules: 规则列表（默认获取所有活跃规则）
            
        Returns:
            按窗口类型分组的规则字典
        """
        if rules is None:
            rules = cls.get_active_rules()
        
        grouped = {}
        for rule in rules:
            window_type = rule.window_type
            if window_type not in grouped:
                grouped[window_type] = []
            grouped[window_type].append(rule)
        
        logger.debug(
            f"规则分组: {', '.join([f'{k}={len(v)}' for k, v in grouped.items()])}"
        )
        
        return grouped
    
    @classmethod
    def sort_rules_by_priority(
        cls,
        rules: List[CorrelationRules]
    ) -> List[CorrelationRules]:
        """
        按优先级排序规则
        
        优先级规则：
        1. 会话窗口 > 滑动窗口 > 固定窗口（时间敏感性）
        2. 同类型窗口按 ID 排序
        
        Args:
            rules: 规则列表
            
        Returns:
            排序后的规则列表
        """
        # 窗口类型优先级
        window_priority = {
            "session": 1,
            "sliding": 2,
            "fixed": 3
        }
        
        sorted_rules = sorted(
            rules,
            key=lambda r: (window_priority.get(r.window_type, 99), r.id)
        )
        
        return sorted_rules
    
    @classmethod
    def filter_rules_by_time(
        cls,
        rules: List[CorrelationRules],
        current_time: datetime
    ) -> List[CorrelationRules]:
        """
        按时间过滤规则（支持规则的生效时间段配置，如果有）
        
        Args:
            rules: 规则列表
            current_time: 当前时间
            
        Returns:
            过滤后的规则列表
        """
        # 当前模型没有时间段配置，直接返回
        # 预留接口，未来可扩展
        return rules
    
    @classmethod
    def get_rule_stats(cls) -> Dict[str, Any]:
        """
        获取规则统计信息
        
        Returns:
            统计信息字典
        """
        all_rules = CorrelationRules.objects.all()
        active_rules = all_rules.filter(is_active=True)
        
        # 按窗口类型统计
        window_stats = {}
        for window_type in ["fixed", "sliding", "session"]:
            count = active_rules.filter(window_type=window_type).count()
            window_stats[window_type] = count
        
        # 按策略类型统计
        strategy_stats = {}
        for strategy_type in ["threshold", "composite", "frequency"]:
            count = active_rules.filter(strategy_type=strategy_type).count()
            strategy_stats[strategy_type] = count
        
        stats = {
            "total": all_rules.count(),
            "active": active_rules.count(),
            "inactive": all_rules.filter(is_active=False).count(),
            "by_window": window_stats,
            "by_strategy": strategy_stats,
        }
        
        return stats
    
    @classmethod
    def validate_rule_compatibility(
        cls,
        correlation_rule: CorrelationRules
    ) -> Dict[str, Any]:
        """
        验证规则是否兼容 V2 系统
        
        Args:
            correlation_rule: 规则对象
            
        Returns:
            验证结果字典
        """
        issues = []
        warnings = []
        
        # 检查窗口配置
        if correlation_rule.window_type == "fixed":
            if not correlation_rule.window_size:
                issues.append("固定窗口缺少 window_size")
        elif correlation_rule.window_type == "sliding":
            if not correlation_rule.window_size:
                issues.append("滑动窗口缺少 window_size")
            if not correlation_rule.slide_interval:
                issues.append("滑动窗口缺少 slide_interval")
        elif correlation_rule.window_type == "session":
            if not correlation_rule.session_timeout:
                issues.append("会话窗口缺少 session_timeout")
            if not correlation_rule.max_window_size:
                warnings.append("会话窗口建议配置 max_window_size 防止无限扩展")
        
        # 检查策略配置
        if correlation_rule.strategy_type == "threshold":
            config = correlation_rule.threshold_config or {}
            if not config.get("field"):
                warnings.append("阈值策略建议配置 field")
            if not config.get("value"):
                warnings.append("阈值策略建议配置 value")
        elif correlation_rule.strategy_type == "composite":
            config = correlation_rule.composite_config or {}
            if not config.get("conditions"):
                issues.append("复合策略缺少 conditions")
        elif correlation_rule.strategy_type == "frequency":
            config = correlation_rule.frequency_config or {}
            if not config.get("count"):
                warnings.append("频率策略建议配置 count")
        
        compatible = len(issues) == 0
        
        return {
            "compatible": compatible,
            "issues": issues,
            "warnings": warnings,
            "rule_id": correlation_rule.id,
            "rule_name": correlation_rule.name
        }
