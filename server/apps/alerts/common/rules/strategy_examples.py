# -- coding: utf-8 --
"""
告警策略动态配置使用示例

展示如何使用不同类型的告警策略（阈值、突变、复合条件、频率等）
来配置和生成相应的SQL查询语句。
"""

from apps.alerts.constants import AlertStrategyType
from apps.alerts.common.rules.template_engine import (
    TemplateContext,
    FilterCondition,
    AggregationRules,
    AlertSQLTemplateEngine,
    ThresholdConfig,
    MutationConfig,
    FrequencyConfig,
    CompositeConfig,
    strategy_factory
)


def create_threshold_alert_example() -> TemplateContext:
    """
    创建阈值告警示例
    场景：CPU使用率超过80%时触发告警
    """
    # 创建阈值策略配置
    threshold_config = strategy_factory.create_threshold_config(
        metric_field="value",           # 监控指标字段
        threshold_value=80.0,           # CPU使用率阈值80%
        operator=">=",                  # 大于等于
        duration_minutes=2              # 持续2分钟
    )
    
    # 资源过滤条件：只监控主机资源的CPU相关事件
    resource_filters = [
        FilterCondition(field="resource_type", operator="=", value="'host'"),
        FilterCondition(field="item", operator="=", value="'cpu_usage'"),
    ]
    
    # 分组字段：按主机分组
    group_by_fields = ["resource_id", "resource_name", "item"]
    
    return TemplateContext(
        table="alerts_event",
        strategy_type=AlertStrategyType.THRESHOLD,
        strategy_config=threshold_config,
        window_size=5,                  # 5分钟窗口
        window_type="fixed",           # 固定窗口
        resource_filters=resource_filters,
        group_by_fields=group_by_fields,
        aggregation_rules=AggregationRules(min_event_count=1)
    )


def create_mutation_alert_example() -> TemplateContext:
    """
    创建突变告警示例
    场景：内存使用率在5分钟内增长超过50%时触发告警
    """
    # 创建突变策略配置
    mutation_config = strategy_factory.create_mutation_config(
        metric_field="value",                    # 监控指标字段
        change_rate_threshold=50.0,              # 变化率阈值50%
        comparison_window_minutes=5,             # 对比5分钟前的数据
        change_type="percent",                   # 百分比变化
        direction="increase"                     # 只检测增长
    )
    
    # 资源过滤条件：只监控内存相关事件
    resource_filters = [
        FilterCondition(field="item", operator="LIKE", value="'%memory%'"),
        FilterCondition(field="resource_type", operator="IN", value=["'host'", "'container'"]),
    ]
    
    group_by_fields = ["resource_id", "resource_name"]
    
    return TemplateContext(
        table="alerts_event",
        strategy_type=AlertStrategyType.MUTATION,
        strategy_config=mutation_config,
        window_size=10,                 # 10分钟窗口
        window_type="sliding",         # 滑动窗口，更敏感
        slide_interval=2,              # 每2分钟滑动
        resource_filters=resource_filters,
        group_by_fields=group_by_fields,
        aggregation_rules=AggregationRules(min_event_count=2)
    )


def create_frequency_alert_example() -> TemplateContext:
    """
    创建频率告警示例
    场景：5分钟内同一服务出现超过10个错误事件时触发告警
    """
    # 创建频率策略配置
    frequency_config = strategy_factory.create_frequency_config(
        event_count_threshold=10,        # 事件数量阈值
        time_window_minutes=5,          # 5分钟时间窗口
        group_by_fields=["resource_type", "resource_name", "alert_source"]
    )
    
    # 资源过滤条件：只监控错误级别事件
    resource_filters = [
        FilterCondition(field="level", operator="<=", value="1"),  # 级别1以上（严重错误）
        FilterCondition(field="status", operator="=", value="'received'"),
    ]
    
    return TemplateContext(
        table="alerts_event",
        strategy_type=AlertStrategyType.FREQUENCY,
        strategy_config=frequency_config,
        window_size=5,                  # 5分钟窗口
        window_type="fixed",           # 固定窗口
        resource_filters=resource_filters,
        group_by_fields=frequency_config.group_by_fields,
        aggregation_rules=AggregationRules(min_event_count=1)  # 策略内部会检查频率阈值
    )


def create_composite_alert_example() -> TemplateContext:
    """
    创建复合条件告警示例
    场景：同时满足多个条件时触发告警
    - CPU使用率 > 70%
    - 内存使用率 > 60%
    - 在5分钟内至少出现3次事件
    """
    # 复合条件配置
    composite_conditions = [
        {
            "field": "item",
            "value": "cpu_usage",
            "operator": "=",
            "threshold": {"field": "value", "operator": ">", "value": 70}
        },
        {
            "field": "item", 
            "value": "memory_usage",
            "operator": "=",
            "threshold": {"field": "value", "operator": ">", "value": 60}
        }
    ]
    
    composite_config = strategy_factory.create_composite_config(
        conditions=composite_conditions,
        logic_operator="AND",           # 同时满足所有条件
        evaluation_window_minutes=5
    )
    
    # 资源过滤条件
    resource_filters = [
        FilterCondition(field="resource_type", operator="=", value="'host'"),
        FilterCondition(field="item", operator="IN", value=["'cpu_usage'", "'memory_usage'"]),
    ]
    
    # 阈值条件：事件数量要求
    threshold_conditions = [
        FilterCondition(field="event_count", operator=">=", value="3"),
    ]
    
    return TemplateContext(
        table="alerts_event",
        strategy_type=AlertStrategyType.COMPOSITE,
        strategy_config=composite_config,
        window_size=5,
        window_type="fixed",
        resource_filters=resource_filters,
        threshold_conditions=threshold_conditions,
        group_by_fields=["resource_id", "resource_name"],
        aggregation_rules=AggregationRules(min_event_count=3)
    )


def generate_sql_examples():
    """生成所有策略类型的SQL示例"""
    engine = AlertSQLTemplateEngine()
    
    examples = [
        ("阈值告警", create_threshold_alert_example()),
        ("突变告警", create_mutation_alert_example()),
        ("频率告警", create_frequency_alert_example()),
        ("复合条件告警", create_composite_alert_example()),
    ]
    
    results = {}
    
    for name, context in examples:
        try:
            sql = engine.render_dynamic_window_sql(context)
            results[name] = {
                "strategy_type": context.strategy_type,
                "sql": sql,
                "config": context.strategy_config.__dict__ if hasattr(context.strategy_config, '__dict__') else context.strategy_config
            }
            print(f"\n=== {name} ===")
            print(f"策略类型: {context.strategy_type}")
            print(f"配置参数: {results[name]['config']}")
            print("生成的SQL:")
            print(sql)
            print("-" * 50)
            
        except Exception as e:
            print(f"生成{name}SQL失败: {str(e)}")
            results[name] = {"error": str(e)}
    
    return results


def create_strategy_from_rule_model(aggregation_rule) -> TemplateContext:
    """
    从AggregationRules模型实例创建TemplateContext
    
    Args:
        aggregation_rule: AggregationRules模型实例
        
    Returns:
        TemplateContext: 模板上下文对象
    """
    # 从模型获取策略类型，默认为复合条件
    strategy_type = getattr(aggregation_rule, 'strategy_type', AlertStrategyType.COMPOSITE)
    
    # 从模型获取策略配置，默认为空字典
    strategy_config_dict = getattr(aggregation_rule, 'strategy_config', {})
    
    # 根据策略类型创建相应的配置对象
    strategy_config = None
    if strategy_type == AlertStrategyType.THRESHOLD and strategy_config_dict:
        strategy_config = ThresholdConfig(**strategy_config_dict)
    elif strategy_type == AlertStrategyType.MUTATION and strategy_config_dict:
        strategy_config = MutationConfig(**strategy_config_dict)
    elif strategy_type == AlertStrategyType.FREQUENCY and strategy_config_dict:
        strategy_config = FrequencyConfig(**strategy_config_dict)
    elif strategy_type == AlertStrategyType.COMPOSITE and strategy_config_dict:
        strategy_config = CompositeConfig(**strategy_config_dict)
    else:
        # 使用字典形式的配置
        strategy_config = strategy_config_dict or {}
    
    # 从关联的CorrelationRules获取窗口配置
    correlation_rule = aggregation_rule.correlation_rules.last()
    window_size = 5  # 默认值
    window_type = "fixed"  # 默认值
    
    if correlation_rule:
        from apps.alerts.utils.util import window_size_to_int
        window_size = window_size_to_int(correlation_rule.window_size)
        window_type = correlation_rule.window_type
    
    # 从条件配置中提取过滤条件
    resource_filters = []
    threshold_conditions = []
    group_by_fields = []
    
    if aggregation_rule.condition and isinstance(aggregation_rule.condition, list):
        for condition in aggregation_rule.condition:
            if isinstance(condition, dict):
                # 提取资源过滤条件
                if 'filter' in condition:
                    for field, value in condition['filter'].items():
                        resource_filters.append(FilterCondition(field=field, operator="=", value=f"'{value}'"))
                
                # 提取分组字段
                if 'aggregation_key' in condition:
                    group_by_fields.extend(condition['aggregation_key'])
    
    return TemplateContext(
        table="alerts_event",
        strategy_type=strategy_type,
        strategy_config=strategy_config,
        window_size=window_size,
        window_type=window_type,
        resource_filters=resource_filters,
        threshold_conditions=threshold_conditions,
        group_by_fields=list(set(group_by_fields)),  # 去重
        aggregation_rules=AggregationRules(min_event_count=1)
    )


if __name__ == "__main__":
    # 运行示例
    print("告警策略动态配置系统使用示例")
    print("=" * 60)
    
    generate_sql_examples()