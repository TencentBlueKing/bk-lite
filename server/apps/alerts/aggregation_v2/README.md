# 告警聚合系统 V2

## 概述

全新设计的统一告警聚合引擎，基于 SQL 原生窗口计算，支持多种窗口类型和告警策略的组合。

## 核心特性

### 窗口类型支持

1. **固定窗口 (Fixed Window)**
    - 时间边界严格对齐
    - 窗口不重叠
    - 适合定期检查场景

2. **滑动窗口 (Sliding Window)**
    - 窗口可重叠
    - 支持增量计算
    - 适合实时监控场景

3. **会话窗口 (Session Window)**
    - 动态窗口大小
    - 基于时间间隙检测
    - 适合活动检测场景

### 策略类型支持

1. **阈值告警 (Threshold)**
    - 指标超过设定阈值时触发
    - 支持多种比较操作符

2. **复合条件 (Composite)**
    - 多条件组合逻辑
    - 支持 AND/OR 运算

3. **频率告警 (Frequency)**
    - 基于事件频次检测
    - 防止告警风暴

## 架构设计

```
aggregation_v2/
├── query/          # 查询策略：智能时间范围计算
├── duckdb/         # DuckDB 引擎：SQL 执行和优化
├── templates/      # Jinja2 模板：SQL 生成
├── rules/          # 规则转换：JSON → TemplateContext
├── processors/     # 窗口处理器：具体窗口逻辑
├── alert_builder/  # 告警构建：Event → Alert
├── state/          # 状态管理：缓存和追踪
├── tasks/          # Celery 任务：异步调度
└── utils/          # 工具函数：通用工具
```

## 核心优化

1. **SQL 原生窗口计算**
    - 窗口边界计算下推到 DuckDB
    - 利用 WINDOW 函数高性能处理
    - 减少应用层复杂度

2. **智能查询优化**
    - 窗口类型驱动的时间范围计算
    - 增量查询（仅查询新增事件）
    - 查询结果缓存

3. **状态管理优化**
    - 滑动窗口状态缓存（Redis）
    - 会话窗口简化管理
    - 已处理窗口追踪

4. **性能监控**
    - 各环节耗时统计
    - SQL 性能分析
    - 告警指标收集

## 使用示例

### 固定窗口 + 阈值告警

```python
from apps.alerts.aggregation_v2.processors.factory import WindowProcessorFactory
from apps.alerts.models import CorrelationRules

# 获取规则
rules = CorrelationRules.objects.filter(window_type='fixed')

# 处理
processor = WindowProcessorFactory.create_processor('fixed')
alerts_created, alerts_updated = processor.process_rules(rules)
```

### 滑动窗口 + 频率告警

```python
# 配置增量查询
from apps.alerts.aggregation_v2.query.strategy import EventQueryStrategy

# 智能时间范围计算
start_time, end_time = EventQueryStrategy.calculate_query_range(rule, current_time)

# 执行处理
processor = WindowProcessorFactory.create_processor('sliding')
alerts_created, alerts_updated = processor.process_rules(rules)
```

### 会话窗口 + 复合条件

```python
# 配置会话关闭条件
session_config = {
    'session_timeout': 300,  # 5 分钟
    'max_duration_seconds': 7200,  # 2 小时
    'close_on_recovery': True
}

# 执行处理
processor = WindowProcessorFactory.create_processor('session')
alerts_created, alerts_updated = processor.process_rules(rules)
```

## 配置说明

详见 `config.py` 文件。

## 测试

```bash
# 运行单元测试
pytest apps/alerts/aggregation_v2/

# 运行特定模块测试
pytest apps/alerts/aggregation_v2/query/tests/
```

## 性能基准

| 场景   | 事件数    | 窗口数 | 耗时   | 内存占用 |
|------|--------|-----|------|------|
| 固定窗口 | 10,000 | 10  | 0.5s | 50MB |
| 滑动窗口 | 10,000 | 100 | 1.2s | 80MB |
| 会话窗口 | 10,000 | 50  | 0.8s | 60MB |


