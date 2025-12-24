# 告警系统动态策略类型集成文档

本文档介绍了如何将阈值告警、突变告警、复合条件等多种策略类型动态集成到 Jinja2 模板系统中。

## 概述

告警系统现在支持以下几种策略类型：

- **阈值告警 (threshold)**: 当监控指标超过设定阈值时触发告警
- **突变告警 (mutation)**: 当监控指标在短时间内发生剧烈变化时触发告警  
- **复合条件 (composite)**: 满足多个复合条件时触发告警，支持AND/OR逻辑组合
- **频率告警 (frequency)**: 当特定事件在时间窗口内出现频次超过阈值时触发告警
- **趋势告警 (trend)**: 基于历史数据趋势，预测性检测异常情况
- **异常检测 (anomaly)**: 使用统计方法检测偏离正常模式的异常数据点

## 架构设计

### 1. 常量定义 (`apps/alerts/constants.py`)

```python
class AlertStrategyType:
    """告警策略类型"""
    THRESHOLD = "threshold"         # 阈值告警
    MUTATION = "mutation"           # 突变告警
    COMPOSITE = "composite"         # 复合条件
    FREQUENCY = "frequency"         # 频率告警
    TREND = "trend"                 # 趋势告警
    ANOMALY = "anomaly"             # 异常检测
```

### 2. 模型扩展 (`apps/alerts/models.py`)

`AggregationRules` 模型新增字段：

```python
class AggregationRules(MaintainerInfo, TimeInfo):
    # ... 现有字段 ...
    
    # 新增策略类型字段
    strategy_type = models.CharField(
        max_length=32, 
        choices=AlertStrategyType.CHOICES, 
        default=AlertStrategyType.COMPOSITE,
        help_text="告警策略类型"
    )
    strategy_config = JSONField(
        default=dict, 
        help_text="策略配置参数", 
        blank=True, 
        null=True
    )
```

### 3. 策略配置数据类

每种策略类型都有对应的配置类：

- `ThresholdConfig`: 阈值策略配置
- `MutationConfig`: 突变策略配置
- `FrequencyConfig`: 频率策略配置
- `CompositeConfig`: 复合条件策略配置
- 等等...

### 4. 模板上下文扩展

`TemplateContext` 类新增字段：

```python
@dataclass
class TemplateContext:
    # ... 现有字段 ...
    
    strategy_type: str = "composite"  # 策略类型
    strategy_config: Union[...] = None  # 策略配置
```

### 5. Jinja2 模板增强

`windows_template.jinja` 模板现在支持基于策略类型的条件分支：

```jinja2
{%- if strategy_type == 'threshold' -%}
    {# 阈值策略SQL生成逻辑 #}
{%- elif strategy_type == 'mutation' -%}
    {# 突变策略SQL生成逻辑 #}
{%- elif strategy_type == 'frequency' -%}
    {# 频率策略SQL生成逻辑 #}
{%- else -%}
    {# 默认复合条件策略 #}
{%- endif -%}
```

## 使用方法

### 1. 基本使用

```python
from apps.alerts.constants import AlertStrategyType
from apps.alerts.common.rules.template_engine import (
    TemplateContext, 
    AlertSQLTemplateEngine,
    strategy_factory
)

# 创建阈值策略配置
threshold_config = strategy_factory.create_threshold_config(
    metric_field="value",
    threshold_value=80.0,
    operator=">=",
    duration_minutes=2
)

# 创建模板上下文
context = TemplateContext(
    table="alerts_event",
    strategy_type=AlertStrategyType.THRESHOLD,
    strategy_config=threshold_config,
    window_size=5,
    window_type="fixed",
    # ... 其他配置
)

# 生成SQL
engine = AlertSQLTemplateEngine()
sql = engine.render_dynamic_window_sql(context)
```

### 2. 从模型实例创建上下文

```python
from apps.alerts.common.rules.strategy_examples import create_strategy_from_rule_model

# 假设有一个 AggregationRules 实例
rule = AggregationRules.objects.get(rule_id='my_rule')

# 从模型创建模板上下文
context = create_strategy_from_rule_model(rule)

# 生成SQL
sql = engine.render_dynamic_window_sql(context)
```

### 3. 不同策略类型示例

#### 阈值告警示例

```python
# CPU使用率超过80%
threshold_config = strategy_factory.create_threshold_config(
    metric_field="value",
    threshold_value=80.0,
    operator=">=",
    duration_minutes=2
)

context = TemplateContext(
    strategy_type=AlertStrategyType.THRESHOLD,
    strategy_config=threshold_config,
    resource_filters=[
        FilterCondition(field="item", operator="=", value="'cpu_usage'")
    ],
    # ...
)
```

#### 突变告警示例

```python
# 内存使用率5分钟内增长超过50%
mutation_config = strategy_factory.create_mutation_config(
    metric_field="value",
    change_rate_threshold=50.0,
    comparison_window_minutes=5,
    direction="increase"
)

context = TemplateContext(
    strategy_type=AlertStrategyType.MUTATION,
    strategy_config=mutation_config,
    # ...
)
```

#### 频率告警示例

```python
# 5分钟内出现超过10个错误事件
frequency_config = strategy_factory.create_frequency_config(
    event_count_threshold=10,
    time_window_minutes=5
)

context = TemplateContext(
    strategy_type=AlertStrategyType.FREQUENCY,
    strategy_config=frequency_config,
    # ...
)
```

## 配置参数说明

### 阈值策略配置 (ThresholdConfig)

| 参数 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `metric_field` | str | 监控指标字段名 | "value", "cpu_usage" |
| `threshold_value` | float | 阈值 | 80.0 |
| `operator` | str | 比较操作符 | ">=", ">", "<=", "<", "==", "!=" |
| `duration_minutes` | int | 持续时间(分钟) | 2 |

### 突变策略配置 (MutationConfig)

| 参数 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `metric_field` | str | 监控指标字段名 | "value" |
| `change_rate_threshold` | float | 变化率阈值(%) | 50.0 |
| `comparison_window_minutes` | int | 对比窗口时间(分钟) | 5 |
| `change_type` | str | 变化类型 | "percent", "absolute" |
| `direction` | str | 突变方向 | "increase", "decrease", "both" |

### 频率策略配置 (FrequencyConfig)

| 参数 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `event_count_threshold` | int | 事件数量阈值 | 10 |
| `time_window_minutes` | int | 时间窗口(分钟) | 5 |
| `group_by_fields` | List[str] | 分组字段 | ["resource_id", "item"] |

## 数据库迁移

运行以下命令应用新的字段：

```bash
python manage.py makemigrations alerts
python manage.py migrate alerts
```

## 模板自定义

如需自定义策略类型的SQL生成逻辑，可以修改 `windows_template.jinja` 文件中对应策略的条件分支。

每个策略分支都会生成特定的CTE (Common Table Expression)，并返回相应的聚合结果。

## 性能考量

- **阈值策略**: 性能最优，直接使用聚合函数检查阈值
- **频率策略**: 性能良好，主要依赖事件计数
- **复合条件**: 性能中等，需要复杂的条件判断
- **突变策略**: 性能较低，需要计算历史对比数据

建议根据实际业务需求选择合适的策略类型，并合理设置窗口大小和过滤条件。

## 扩展性

系统设计支持轻松添加新的策略类型：

1. 在 `AlertStrategyType` 中添加新的常量
2. 创建对应的配置数据类
3. 在 Jinja2 模板中添加新的条件分支
4. 在策略工厂中添加创建方法

## 故障排除

### 常见问题

1. **模板渲染失败**: 检查策略配置参数是否完整
2. **SQL语法错误**: 验证字段名和过滤条件的安全性
3. **性能问题**: 检查窗口大小和过滤条件是否合理

### 调试方法

```python
# 启用调试日志
import logging
logging.getLogger('apps.alerts.common.rules.template_engine').setLevel(logging.DEBUG)

# 验证模板上下文
context = TemplateContext(...)
try:
    context.__post_init__()  # 触发验证
    print("上下文验证通过")
except ValueError as e:
    print(f"上下文验证失败: {e}")
```

## 完整示例

参见 `apps/alerts/common/rules/strategy_examples.py` 文件，其中包含了所有策略类型的完整使用示例。

运行示例：

```bash
cd /path/to/project
python -c "
from apps.alerts.common.rules.strategy_examples import generate_sql_examples
generate_sql_examples()
"
```

这将输出所有策略类型生成的SQL示例。