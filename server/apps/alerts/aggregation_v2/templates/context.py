# -- coding: utf-8 --
"""
模板上下文构建器

根据规则配置构建模板渲染所需的上下文数据

设计原则：
1. 支持两层配置：strategy_config（表单配置）+ condition（详细配置）
2. strategy_config 用于表单快速配置和展示
3. condition 用于完整的执行逻辑，支持自定义 SQL
4. 优先使用 condition，strategy_config 作为补充
"""
from typing import Dict, Any, List, Optional
from datetime import datetime

from apps.alerts.models import CorrelationRules
from apps.alerts.constants import WindowType, AlertStrategyType
from apps.alerts.aggregation_v2.utils.time_utils import TimeUtils
from apps.core.logger import alert_logger as logger


class TemplateContext:
    """
    模板上下文构建器
    
    职责：
    1. 根据规则配置构建模板变量
    2. 处理不同窗口类型的参数转换
    3. 处理不同策略类型的条件构建
    """

    @classmethod
    def build_context(
            cls,
            correlation_rule: CorrelationRules,
            current_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        构建完整的模板上下文
        
        Args:
            correlation_rule: 关联规则对象
            current_time: 当前时间（用于时间对齐）
            
        Returns:
            模板上下文字典
            
        Examples:
            >>> rule = CorrelationRules.objects.get(id=1)
            >>> context = TemplateContext.build_context(rule)
            >>> print(context['window_type'])  # 'fixed'
        """
        window_type = correlation_rule.window_type
        strategy_type = correlation_rule.strategy_type

        # 基础上下文
        context = {
            # 窗口类型
            "window_type": window_type,
            "strategy_type": strategy_type,

            # 通用参数
            "rule_id": correlation_rule.id,
            "rule_name": correlation_rule.name,
        }

        # 添加窗口特定的上下文
        if window_type == WindowType.FIXED:
            context.update(cls._build_fixed_window_context(correlation_rule, current_time))
        elif window_type == WindowType.SLIDING:
            context.update(cls._build_sliding_window_context(correlation_rule, current_time))
        elif window_type == WindowType.SESSION:
            context.update(cls._build_session_window_context(correlation_rule, current_time))

        # 添加策略特定的上下文
        if strategy_type == AlertStrategyType.THRESHOLD:
            context.update(cls._build_threshold_strategy_context(correlation_rule))
        elif strategy_type == AlertStrategyType.COMPOSITE:
            context.update(cls._build_composite_strategy_context(correlation_rule))
        elif strategy_type == AlertStrategyType.FREQUENCY:
            context.update(cls._build_frequency_strategy_context(correlation_rule))

        logger.debug(f"模板上下文: {context}")

        return context

    # ==================== 窗口上下文构建 ====================

    @classmethod
    def _build_fixed_window_context(
            cls,
            correlation_rule: CorrelationRules,
            current_time: Optional[datetime]
    ) -> Dict[str, Any]:
        """构建固定窗口上下文"""
        window_size_seconds = TimeUtils.parse_time_str_to_seconds(
            correlation_rule.window_size
        )

        # 计算窗口对齐时间
        if current_time:
            window_start = TimeUtils.align_to_window(
                current_time,
                window_size_seconds,
                alignment='minute'  # 默认按分钟对齐
            )
        else:
            window_start = None

        return {
            "window_size": correlation_rule.window_size,
            "window_size_seconds": window_size_seconds,
            "window_start": window_start,
        }

    @classmethod
    def _build_sliding_window_context(
            cls,
            correlation_rule: CorrelationRules,
            current_time: Optional[datetime]
    ) -> Dict[str, Any]:
        """构建滑动窗口上下文"""
        window_size_seconds = TimeUtils.parse_time_str_to_seconds(
            correlation_rule.window_size
        )
        slide_interval_seconds = TimeUtils.parse_time_str_to_seconds(
            correlation_rule.slide_interval
        )

        return {
            "window_size": correlation_rule.window_size,
            "window_size_seconds": window_size_seconds,
            "slide_interval": correlation_rule.slide_interval,
            "slide_interval_seconds": slide_interval_seconds,
        }

    @classmethod
    def _build_session_window_context(
            cls,
            correlation_rule: CorrelationRules,
            current_time: Optional[datetime]
    ) -> Dict[str, Any]:
        """构建会话窗口上下文"""
        session_timeout_seconds = TimeUtils.parse_time_str_to_seconds(
            correlation_rule.session_timeout
        )

        # TODO 最大窗口大小（可选）
        max_window_size_seconds = None
        if correlation_rule.max_window_size:
            max_window_size_seconds = TimeUtils.parse_time_str_to_seconds(
                correlation_rule.max_window_size
            )

        return {
            "session_timeout": correlation_rule.session_timeout,
            "session_timeout_seconds": session_timeout_seconds,
            "max_window_size": correlation_rule.max_window_size,
            "max_window_size_seconds": max_window_size_seconds,
        }

    # ==================== 策略上下文构建 ====================

    @classmethod
    def _build_threshold_strategy_context(
            cls,
            correlation_rule: CorrelationRules
    ) -> Dict[str, Any]:
        """构建阈值策略上下文
        
        阈值策略示例：
        - CPU 使用率 > 80%
        - 内存使用 > 90%
        - QPS > 10000
        
        Returns:
            {
                "strategy_config": {...},      # 表单配置（简化）
                "filter_config": {...},         # 过滤条件
                "custom_aggregations": {...},   # 自定义聚合
                "min_event_count": 1,           # 最小事件数
                "custom_sql": None              # 自定义 SQL（如果有）
            }
        """
        agg_rule = correlation_rule.aggregation_rules.first()
        if not agg_rule:
            return {}
        
        # 1. 获取 strategy_config（表单配置）
        strategy_config = agg_rule.strategy_config or {}
        
        # 2. 获取 condition 详细配置
        condition = cls._get_first_condition(agg_rule)
        if not condition:
            return {"strategy_config": strategy_config}
        
        # 3. 提取配置
        filter_config = condition.get('filter', {})
        aggregation_rules = condition.get('aggregation_rules', {})
        custom_aggs = aggregation_rules.get('custom_aggregations', {})
        
        # 将 filter_config 转换为 filters 列表格式（与 SQL 模板匹配）
        filters = [filter_config] if filter_config else []
        
        return {
            "strategy_config": strategy_config,
            "filters": filters,  # SQL 模板需要的格式
            "aggregation_rules": aggregation_rules,
            "custom_aggregations": custom_aggs,
            "min_event_count": aggregation_rules.get('min_event_count', 1),
        }

    @classmethod
    def _build_composite_strategy_context(
            cls,
            correlation_rule: CorrelationRules
    ) -> Dict[str, Any]:
        """构建复合策略上下文
        
        复合策略示例：
        - CPU > 80% AND 内存 > 90%
        - 错误率 > 5% OR 超时率 > 10%
        
        Returns:
            {
                "strategy_config": {...},       # 表单配置（简化）
                "logic": "AND",                 # 组合逻辑
                "filters": [...],               # 所有过滤器
                "custom_aggregations": {...},   # 自定义聚合
                "aggregation_keys": [...],      # 分组键
                "session_close": {...}          # 会话关闭条件（如果有）
            }
        """
        # 1. 获取 strategy_config
        agg_rule = correlation_rule.aggregation_rules.first()
        if not agg_rule:
            return {}
        
        strategy_config = agg_rule.strategy_config or {}
        logic = strategy_config.get('logic', 'AND')
        
        # 2. 获取所有条件
        all_conditions = cls._get_all_conditions(correlation_rule)
        
        # 3. 提取配置
        filters = []
        aggregation_keys = []
        custom_aggregations = {}
        session_close = None
        
        for cond in all_conditions:
            # 过滤器
            filter_config = cond.get('filter', {})
            if filter_config:
                filters.append(filter_config)
            
            # 分组键
            agg_key = cond.get('aggregation_key', [])
            if agg_key and agg_key not in aggregation_keys:
                aggregation_keys.append(agg_key)
            
            # 自定义聚合
            agg_rules = cond.get('aggregation_rules', {})
            custom_aggs = agg_rules.get('custom_aggregations', {})
            custom_aggregations.update(custom_aggs)
            
            # 会话关闭条件
            if 'session_close' in cond:
                session_close = cond['session_close']
        
        return {
            "strategy_config": strategy_config,
            "logic": logic,
            "filters": filters,
            "aggregation_keys": aggregation_keys,
            "custom_aggregations": custom_aggregations,
            "condition_count": len(all_conditions),
            "session_close": session_close,
        }

    @classmethod
    def _build_frequency_strategy_context(
            cls,
            correlation_rule: CorrelationRules
    ) -> Dict[str, Any]:
        """构建频率策略上下文
        
        频率策略示例：
        - 5分钟内登录失败超过10次
        - 1小时内接口报错超过100次
        
        Returns:
            {
                "strategy_config": {...},       # 表单配置（简化）
                "count_threshold": 10,          # 次数阈值
                "time_window": "5min",          # 时间窗口
                "custom_aggregations": {...},   # 计数相关聚合
                "failure_count_expr": "COUNT(*)" # 计数表达式
            }
        """
        agg_rule = correlation_rule.aggregation_rules.first()
        if not agg_rule:
            return {}
        
        # 1. 获取 strategy_config
        strategy_config = agg_rule.strategy_config or {}
        
        # 2. 获取 condition 详细配置
        condition = cls._get_first_condition(agg_rule)
        if not condition:
            return {"strategy_config": strategy_config}
        
        aggregation_rules = condition.get('aggregation_rules', {})
        custom_aggs = aggregation_rules.get('custom_aggregations', {})
        
        # 获取过滤配置
        filter_config = condition.get('filter', {})
        filters = [filter_config] if filter_config else []
        
        # 3. 提取频率相关配置
        failure_count_expr = custom_aggs.get('failure_count', 'COUNT(*)')
        count_threshold = strategy_config.get('count_threshold', 
                                            aggregation_rules.get('min_event_count', 1))
        
        return {
            "strategy_config": strategy_config,
            "filters": filters,  # SQL 模板需要的格式
            "aggregation_rules": aggregation_rules,
            "custom_aggregations": custom_aggs,
            "count_threshold": count_threshold,
            "time_window": strategy_config.get('time_window', '1min'),
            "min_event_count": aggregation_rules.get('min_event_count', 1),
            "failure_count_expr": failure_count_expr,
        }
    
    # ==================== 辅助方法 ====================
    
    @classmethod
    def _get_first_condition(cls, agg_rule) -> Optional[Dict[str, Any]]:
        """获取第一个条件配置"""
        if not agg_rule or not agg_rule.condition:
            return None
        
        conditions = agg_rule.condition
        if isinstance(conditions, list) and len(conditions) > 0:
            return conditions[0]
        elif isinstance(conditions, dict):
            return conditions
        return None
    
    @classmethod
    def _get_all_conditions(cls, correlation_rule: CorrelationRules) -> List[Dict[str, Any]]:
        """获取所有条件配置"""
        all_conditions = []
        
        for agg_rule in correlation_rule.aggregation_rules.all():
            if not agg_rule.condition:
                continue
            
            conditions = agg_rule.condition
            if isinstance(conditions, list):
                all_conditions.extend(conditions)
            elif isinstance(conditions, dict):
                all_conditions.append(conditions)
        
        return all_conditions

    @classmethod
    def get_select_fields(cls, correlation_rule: CorrelationRules) -> List[str]:
        """
        获取 SELECT 字段列表
        
        Args:
            correlation_rule: 关联规则对象
            
        Returns:
            SELECT 字段列表
        """
        # 基础字段
        base_fields = [
            "fingerprint",
            "resource_id",
            "resource_name",
            "resource_type",
            "item",
            "source_id",
            "alert_source",
            "rule_id",
        ]

        # 聚合字段
        agg_fields = [
            "COUNT(*) AS event_count",
            "MAX(level) AS max_level",
            "MIN(received_at) AS first_event_time",
            "MAX(received_at) AS last_event_time",
        ]

        # 组合
        return base_fields + agg_fields
