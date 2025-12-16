# -- coding: utf-8 --
"""
规则配置验证器和辅助工具

提供规则配置的验证、转换和生成功能
"""
from typing import Dict, Any, List, Optional
from apps.alerts.constants import AlertStrategyType, WindowType


class RuleConfigValidator:
    """规则配置验证器"""
    
    # 必填字段定义
    REQUIRED_FIELDS = {"rule_id", "name", "strategy_type", "condition"}
    CONDITION_REQUIRED = {"filter", "aggregation_key", "window_config", "aggregation_rules"}
    
    # 有效的操作符
    VALID_OPERATORS = {"=", "!=", ">", "<", ">=", "<=", "in", "not_in", "like", "regex"}
    
    @classmethod
    def validate(cls, config: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """
        验证规则配置完整性
        
        Args:
            config: 规则配置字典
            
        Returns:
            (是否有效, 错误信息)
        """
        # 1. 检查必填字段
        missing_fields = cls.REQUIRED_FIELDS - set(config.keys())
        if missing_fields:
            return False, f"缺少必填字段: {', '.join(missing_fields)}"
        
        # 2. 检查策略类型有效性
        if config["strategy_type"] not in [
            AlertStrategyType.THRESHOLD,
            AlertStrategyType.COMPOSITE,
            AlertStrategyType.FREQUENCY,
            AlertStrategyType.MUTATION,
            AlertStrategyType.TREND,
            AlertStrategyType.ANOMALY,
        ]:
            return False, f"无效的策略类型: {config['strategy_type']}"
        
        # 3. 检查 condition 结构
        conditions = config.get("condition", [])
        if not isinstance(conditions, list) or len(conditions) == 0:
            return False, "condition 必须是非空数组"
        
        for idx, cond in enumerate(conditions):
            valid, error = cls._validate_condition(cond, idx)
            if not valid:
                return False, error
        
        return True, None
    
    @classmethod
    def _validate_condition(cls, condition: Dict[str, Any], index: int) -> tuple[bool, Optional[str]]:
        """验证单个条件配置"""
        # 检查必填字段
        missing = cls.CONDITION_REQUIRED - set(condition.keys())
        if missing:
            return False, f"条件[{index}]缺少字段: {', '.join(missing)}"
        
        # 验证过滤器
        filter_config = condition.get("filter", {})
        if not isinstance(filter_config, dict):
            return False, f"条件[{index}]的 filter 必须是字典"
        
        # 验证窗口配置
        window_config = condition.get("window_config", {})
        valid, error = cls._validate_window_config(window_config, index)
        if not valid:
            return False, error
        
        # 验证聚合规则
        agg_rules = condition.get("aggregation_rules", {})
        if not isinstance(agg_rules, dict):
            return False, f"条件[{index}]的 aggregation_rules 必须是字典"
        
        return True, None
    
    @classmethod
    def _validate_window_config(cls, config: Dict[str, Any], index: int) -> tuple[bool, Optional[str]]:
        """验证窗口配置"""
        window_type = config.get("window_type")
        
        if window_type not in [WindowType.FIXED, WindowType.SLIDING, WindowType.SESSION]:
            return False, f"条件[{index}]的窗口类型无效: {window_type}"
        
        # 不同窗口类型的特定验证
        if window_type == WindowType.FIXED:
            if "window_size" not in config:
                return False, f"条件[{index}]的固定窗口缺少 window_size"
        
        elif window_type == WindowType.SLIDING:
            if "window_size" not in config or "slide_interval" not in config:
                return False, f"条件[{index}]的滑动窗口缺少 window_size 或 slide_interval"
        
        elif window_type == WindowType.SESSION:
            if "session_timeout" not in config:
                return False, f"条件[{index}]的会话窗口缺少 session_timeout"
        
        return True, None


class RuleConfigConverter:
    """规则配置转换器"""
    
    @classmethod
    def strategy_config_to_condition(
        cls,
        strategy_type: str,
        strategy_config: Dict[str, Any],
        window_config: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        将简化的 strategy_config 转换为完整的 condition
        
        用于表单提交时自动生成详细配置
        
        Args:
            strategy_type: 策略类型
            strategy_config: 策略配置（表单层）
            window_config: 窗口配置
            
        Returns:
            condition 配置数组
        """
        if strategy_type == AlertStrategyType.THRESHOLD:
            return cls._build_threshold_condition(strategy_config, window_config)
        
        elif strategy_type == AlertStrategyType.COMPOSITE:
            return cls._build_composite_condition(strategy_config, window_config)
        
        elif strategy_type == AlertStrategyType.FREQUENCY:
            return cls._build_frequency_condition(strategy_config, window_config)
        
        else:
            # 默认返回空条件，需要用户手动填写
            return [{
                "filter": {},
                "aggregation_key": strategy_config.get("group_by", ["fingerprint"]),
                "window_config": window_config,
                "aggregation_rules": {
                    "min_event_count": 1,
                    "custom_aggregations": {}
                }
            }]
    
    @classmethod
    def _build_threshold_condition(
        cls,
        strategy_config: Dict[str, Any],
        window_config: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """构建阈值策略的 condition"""
        field = strategy_config.get("field", "value")
        operator = strategy_config.get("operator", ">=")
        value = strategy_config.get("value", 0)
        agg_func = strategy_config.get("aggregation", "AVG")
        
        return [{
            "filter": {
                "custom_sql": f"{agg_func}({field}) {operator} {value}"
            },
            "aggregation_key": strategy_config.get("group_by", ["fingerprint"]),
            "window_config": window_config,
            "aggregation_rules": {
                "min_event_count": 1,
                "custom_aggregations": {
                    f"{agg_func.lower()}_{field}": f"{agg_func}({field})",
                    f"max_{field}": f"MAX({field})",
                    f"min_{field}": f"MIN({field})",
                    "sample_count": "COUNT(*)"
                }
            }
        }]
    
    @classmethod
    def _build_composite_condition(
        cls,
        strategy_config: Dict[str, Any],
        window_config: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """构建复合策略的 condition"""
        conditions = strategy_config.get("conditions", [])
        logic = strategy_config.get("logic", "AND")
        
        # 构建 SQL 条件
        sql_parts = []
        custom_aggs = {}
        
        for cond in conditions:
            field = cond.get("field", "value")
            operator = cond.get("operator", ">=")
            value = cond.get("value", 0)
            agg_func = cond.get("aggregation", "AVG")
            
            sql_parts.append(f"{agg_func}({field}) {operator} {value}")
            custom_aggs[f"{agg_func.lower()}_{field}"] = f"{agg_func}({field})"
        
        custom_sql = f" {logic} ".join(sql_parts) if sql_parts else None
        
        return [{
            "filter": {
                "custom_sql": custom_sql
            },
            "aggregation_key": strategy_config.get("group_by", ["fingerprint"]),
            "window_config": window_config,
            "aggregation_rules": {
                "min_event_count": 1,
                "custom_aggregations": custom_aggs
            }
        }]
    
    @classmethod
    def _build_frequency_condition(
        cls,
        strategy_config: Dict[str, Any],
        window_config: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """构建频率策略的 condition"""
        count_threshold = strategy_config.get("count_threshold", 10)
        
        return [{
            "filter": {},
            "aggregation_key": strategy_config.get("group_by", ["fingerprint"]),
            "window_config": window_config,
            "aggregation_rules": {
                "min_event_count": count_threshold,
                "custom_aggregations": {
                    "event_count": "COUNT(*)",
                    "first_event": "MIN(start_time)",
                    "last_event": "MAX(start_time)",
                    "time_span_seconds": "EXTRACT(EPOCH FROM (MAX(start_time) - MIN(start_time)))"
                }
            }
        }]


class RuleConfigHelper:
    """规则配置辅助工具"""
    
    @staticmethod
    def extract_filter_fields(filter_config: Dict[str, Any]) -> List[str]:
        """
        从过滤器配置中提取所有字段名
        
        Args:
            filter_config: 过滤器配置
            
        Returns:
            字段名列表
        """
        fields = []
        
        for key, value in filter_config.items():
            if key == "custom_sql":
                continue
            
            if isinstance(value, dict) and "operator" in value:
                fields.append(key)
        
        return fields
    
    @staticmethod
    def build_filter_sql(filter_config: Dict[str, Any]) -> str:
        """
        将过滤器配置转换为 SQL WHERE 子句
        
        Args:
            filter_config: 过滤器配置
            
        Returns:
            SQL WHERE 子句（不含 WHERE 关键字）
        """
        # 如果有自定义 SQL，直接使用
        if "custom_sql" in filter_config and filter_config["custom_sql"]:
            return filter_config["custom_sql"]
        
        # 否则根据配置生成
        conditions = []
        
        for field, config in filter_config.items():
            if field == "custom_sql":
                continue
            
            if not isinstance(config, dict):
                continue
            
            operator = config.get("operator", "=")
            value = config.get("value")
            
            if operator in {"in", "not_in"}:
                value_list = ", ".join([f"'{v}'" if isinstance(v, str) else str(v) for v in value])
                op = "IN" if operator == "in" else "NOT IN"
                conditions.append(f"{field} {op} ({value_list})")
            
            elif operator == "like":
                conditions.append(f"{field} LIKE '{value}'")
            
            elif operator == "regex":
                conditions.append(f"{field} ~ '{value}'")
            
            else:
                if isinstance(value, str):
                    conditions.append(f"{field} {operator} '{value}'")
                else:
                    conditions.append(f"{field} {operator} {value}")
        
        return " AND ".join(conditions) if conditions else "TRUE"
    
    @staticmethod
    def generate_default_aggregations(
        strategy_type: str,
        fields: Optional[List[str]] = None
    ) -> Dict[str, str]:
        """
        根据策略类型生成默认的聚合配置
        
        Args:
            strategy_type: 策略类型
            fields: 相关字段列表
            
        Returns:
            自定义聚合配置
        """
        # 基础聚合（所有策略都需要）
        base_aggs = {
            "event_count": "COUNT(*)",
            "first_event_time": "MIN(start_time)",
            "last_event_time": "MAX(start_time)",
            "max_level": "MAX(level)",
        }
        
        # 根据策略类型添加特定聚合
        if strategy_type == AlertStrategyType.THRESHOLD:
            if fields:
                for field in fields:
                    base_aggs.update({
                        f"avg_{field}": f"AVG({field})",
                        f"max_{field}": f"MAX({field})",
                        f"min_{field}": f"MIN({field})",
                    })
        
        elif strategy_type == AlertStrategyType.FREQUENCY:
            base_aggs.update({
                "time_span_seconds": "EXTRACT(EPOCH FROM (MAX(start_time) - MIN(start_time)))",
                "avg_interval_seconds": "EXTRACT(EPOCH FROM (MAX(start_time) - MIN(start_time))) / NULLIF(COUNT(*) - 1, 0)",
            })
        
        elif strategy_type == AlertStrategyType.COMPOSITE:
            if fields:
                for field in fields:
                    base_aggs[f"avg_{field}"] = f"AVG({field})"
        
        return base_aggs
    
    @staticmethod
    def format_template_context(
        aggregation_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        格式化聚合结果用于模板渲染
        
        Args:
            aggregation_result: DuckDB 聚合结果
            
        Returns:
            格式化后的上下文字典
        """
        context = dict(aggregation_result)
        
        # 格式化时间
        for key in ["first_event_time", "last_event_time", "window_start", "window_end"]:
            if key in context and context[key]:
                # 确保是字符串格式
                context[key] = str(context[key])
        
        # 格式化数值（保留两位小数）
        for key, value in context.items():
            if isinstance(value, float) and "percent" in key.lower():
                context[key] = round(value, 2)
        
        return context


# 导出
__all__ = [
    "RuleConfigValidator",
    "RuleConfigConverter",
    "RuleConfigHelper",
]
