# 告警聚合规则字段指南

> **目标读者**: 需要创建和配置告警聚合规则的开发者和运维人员
> 
> **文档用途**: 详细说明规则字段定义、模板上下文转换逻辑、SQL 生成流程

---

## 📋 目录

1. [核心模型字段](#核心模型字段)
2. [配置结构](#配置结构)
3. [窗口类型详解](#窗口类型详解)
4. [模板上下文转换](#模板上下文转换)
5. [SQL 生成流程](#sql-生成流程)
6. [完整示例](#完整示例)

---

## 核心模型字段

### CorrelationRules（关联规则）

关联规则是聚合任务的顶层配置，管理窗口类型、时间参数和关联的聚合规则。

| 字段 | 类型 | 说明 | 示例 | 是否必填 |
|------|------|------|------|----------|
| `name` | CharField | 规则名称（唯一） | `"CPU高使用率告警"` | ✅ |
| `aggregation_rules` | ManyToMany | 关联的聚合规则（定义策略） | `AggregationRules` 对象 | ✅ |
| `scope` | CharField | 作用范围 | `"global"` / `"project"` | ✅ |
| `rule_type` | CharField | 规则类型 | `"alert"` / `"incident"` | ✅ |
| `window_type` | CharField | 窗口类型 | `"fixed"` / `"sliding"` / `"session"` | ✅ |
| `window_size` | CharField | 窗口大小 | `"10min"` / `"1h"` / `"30s"` | ✅ |
| `slide_interval` | CharField | 滑动间隔（仅 sliding） | `"1min"` / `"30s"` | sliding 时必填 |
| `alignment` | CharField | 对齐方式（仅 fixed） | `"minute"` / `"hour"` | ❌ |
| `session_timeout` | CharField | 会话超时（仅 session） | `"10min"` / `"5min"` | session 时必填 |
| `max_window_size` | CharField | 最大窗口限制（仅 session） | `"1h"` / `"2h"` | ❌ |
| `session_key_fields` | JSONField | 会话分组字段 | `["resource_id", "item"]` | ❌ |
| `close_time` | CharField | 自动关闭时间 | `"10min"` | ❌ |
| `description` | TextField | 规则描述 | `"监控服务器CPU..."` | ❌ |

### AggregationRules（聚合规则）

聚合规则定义具体的策略逻辑、过滤条件和聚合计算。

| 字段 | 类型 | 说明 | 示例 | 是否必填 |
|------|------|------|------|----------|
| `rule_id` | CharField | 规则唯一ID | `"cpu_alert_001"` | ✅ |
| `name` | CharField | 规则名称 | `"CPU阈值告警"` | ✅ |
| `strategy_type` | CharField | 策略类型 | `"threshold"` / `"composite"` / `"frequency"` | ✅ |
| `strategy_config` | JSONField | 策略配置（表单层） | 见下方详细说明 | ✅ |
| `condition` | JSONField | 执行条件（详细层） | JSON 数组，见下方详细说明 | ✅ |
| `window_config` | JSONField | **窗口推荐配置**（用于前端表单） | 推荐窗口类型和默认参数 | ✅ |
| `aggregation_type` | CharField | 聚合类型 | `"aggregation"` / `"composite"` | ✅ |
| `description` | TextField | 规则描述 | `"CPU超过80%时告警"` | ❌ |

**重要说明**: 
- `window_config` 是**推荐配置**，用于前端表单展示和参数预填充，**不用于实际执行**
- 实际执行时的窗口配置来自 `CorrelationRules` 模型（规则实例层）
- 这种设计使内置规则成为模板，包含最佳实践和专家知识

---

## 配置结构

### 三层配置架构

聚合规则采用**三层配置架构**，兼顾易用性、灵活性和可复用性：

```
┌─────────────────────────────────────────────────────┐
│  AggregationRules.window_config (推荐配置层)         │
│  - 推荐的窗口类型和默认参数                            │
│  - 用于前端表单智能推荐和预填充                        │
│  - 包含最佳实践和专家知识                             │
│  - 使内置规则成为可复用的模板                         │
└─────────────────────────────────────────────────────┘
                        ↓ 用户选择和调整
┌─────────────────────────────────────────────────────┐
│  CorrelationRules (规则实例层 - 唯一执行来源)        │
│  - 用户实际选择的窗口类型                             │
│  - 用户配置的窗口参数（可基于推荐修改）                │
│  - 实际执行时使用的配置                               │
└─────────────────────────────────────────────────────┘
                        ↓ 读取配置
┌─────────────────────────────────────────────────────┐
│  AggregationRules.strategy_config (策略配置层)       │
│  - 简化的策略配置                                     │
│  - 前端表单直接映射                                   │
│  - 用于快速配置和展示                                 │
└─────────────────────────────────────────────────────┘
                        ↓ 转换
┌─────────────────────────────────────────────────────┐
│  AggregationRules.condition (执行配置层)             │
│  - 完整的执行逻辑                                     │
│  - 支持复杂条件和自定义SQL                            │
│  - 不包含窗口配置（已移至 CorrelationRules）          │
### condition 配置结构

**重要**: `condition` 不再包含 `window_config`，窗口配置已移至 `CorrelationRules` 层

```python
"condition": [
    {
        # 1. 过滤条件
        "filter": {
            # 结构化过滤器
            "field_name": {
                "operator": "=",      # 运算符
                "value": "value"      # 值
            },
            # 或使用自定义SQL
            "custom_sql": "field1 > 10 AND field2 = 'test'"
        },
        
        # 2. 分组键（GROUP BY）
        "aggregation_key": ["fingerprint", "resource_id"],
        
        # 3. 聚合规则
        "aggregation_rules": {
            "min_event_count": 1,         # 最小事件数
            "custom_aggregations": {       # 自定义聚合表达式
                "avg_value": "AVG(value)",
                "max_value": "MAX(value)"
            }
        },
        
        # 4. 会话关闭条件（可选，仅session窗口）
        "session_close": {
            "enabled": True,
            "filter": {"status": {"operator": "=", "value": "success"}},
            "action": "close_session"
        }
    }
]
```

**设计说明**:
- ✅ 窗口配置统一在 `CorrelationRules` 层管理（规则实例）
- ✅ `window_config` 在 `AggregationRules` 层仅作推荐（规则模板）
- ✅ 避免配置冗余和不一致
- ✅ 保持单一数据源原则 
    # 不推荐的窗口类型
    "not_recommended": ["fixed"],
    
    # 不推荐的原因
    "reason": "该策略需要动态窗口边界"
}
```

**前端使用流程**:
1. 用户选择聚合策略模板（`AggregationRules`）
2. 前端读取 `window_config.recommended_types`，高亮推荐类型
3. 自动选择 `window_config.default_type`
4. 根据选择的窗口类型，从 `window_config.default_params` 预填充参数
5. 不推荐的类型显示警告提示
6. 用户可以调整参数或选择其他窗口类型
7. 最终配置保存到 `CorrelationRules`（规则实例）

### condition 配置结构

```python
"condition": [
    {
        # 1. 过滤条件
        "filter": {
            # 结构化过滤器
            "field_name": {
                "operator": "=",      # 运算符
                "value": "value"      # 值
            },
            # 或使用自定义SQL
            "custom_sql": "field1 > 10 AND field2 = 'test'"
        },
        
        # 2. 分组键（GROUP BY）
        "aggregation_key": ["fingerprint", "resource_id"],
        
        # 3. 窗口配置
        "window_config": {
            "window_type": "fixed",       # 窗口类型
            "window_size": 5,             # 窗口大小（分钟）
            "slide_interval": 1,          # 滑动间隔（仅sliding）
            "session_timeout": 10,        # 会话超时（仅session）
            "time_column": "received_at", # 时间字段
            "alignment": "minute"         # 对齐方式（仅fixed）
        },
        
        # 4. 聚合规则
        "aggregation_rules": {
            "min_event_count": 1,         # 最小事件数
            "custom_aggregations": {       # 自定义聚合表达式
                "avg_value": "AVG(value)",
                "max_value": "MAX(value)"
            }
        },
        
        # 5. 会话关闭条件（可选，仅session）
        "session_close": {
            "enabled": True,
            "filter": {"status": {"operator": "=", "value": "success"}},
            "action": "close_session"
        }
    }
]
```

---

## 窗口类型详解

### 1. Fixed Window（固定窗口）

**特点**：
- 时间边界严格对齐（如整点、整分钟）
- 窗口不重叠
- 适合定期检查场景

**必填字段**：
```python
# CorrelationRules
window_type = "fixed"
window_size = "10min"          # 窗口大小
alignment = "minute"           # 对齐方式：minute/hour/day
```

**可选字段**：
```python
# condition[0].window_config
time_column = "received_at"    # 使用哪个时间字段
```

**SQL 特征**：
```sql
-- 使用时间戳除法计算窗口ID
FLOOR(EPOCH(received_at) / 600) AS window_id
```

**示例场景**：
- 每5分钟统计一次API错误率
- 每小时计算一次服务器平均负载
- 每天汇总业务指标

---

### 2. Sliding Window（滑动窗口）

**特点**：
- 窗口可以重叠
- 支持增量计算
- 适合实时监控场景

**必填字段**：
```python
# CorrelationRules
window_type = "sliding"
window_size = "10min"          # 窗口大小
slide_interval = "1min"        # 滑动间隔（窗口移动步长）
```

**可选字段**：
```python
# condition[0].window_config
time_column = "received_at"
```

**SQL 特征**：
```sql
-- 使用 RANGE BETWEEN 实现滑动效果
received_at - INTERVAL '10 minutes' AS window_start,
received_at AS window_end,
FLOOR(EPOCH(received_at) / 60) AS window_id  -- 按滑动间隔对齐
```

**示例场景**：
- 实时监控最近10分钟的请求量
- 过去1小时内的错误趋势
- 近5分钟的QPS波动

---

### 3. Session Window（会话窗口）⭐

**特点**：
- 动态窗口大小（基于事件间隔）
- 自动检测活动开始和结束
- 适合会话/流程跟踪场景

**必填字段**：
```python
# CorrelationRules
window_type = "session"
session_timeout = "10min"      # 会话超时时间（事件间隔超过此值则新会话）
```

**可选字段**：
```python
# CorrelationRules
max_window_size = "1h"         # 最大会话时长（防止无限扩展）
session_key_fields = ["resource_id", "user_id"]  # 会话分组字段（默认用fingerprint）

# condition[0].session_close
session_close = {
    "enabled": True,
    "filter": {"status": {"operator": "=", "value": "success"}},
    "action": "close_session"
}
```

**SQL 特征**：
```sql
-- 使用 LAG() 计算事件间隔
LAG(received_at, 1, received_at) OVER (
    PARTITION BY fingerprint 
    ORDER BY received_at
) AS prev_event_time,

-- 标记会话边界
CASE 
    WHEN received_at - LAG(...) > INTERVAL '10 minutes' 
    THEN 1 ELSE 0 
END AS is_session_start,

-- 生成会话ID
SUM(is_session_start) OVER (
    PARTITION BY fingerprint 
    ORDER BY received_at
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
) AS session_id
```

**示例场景**：
- 用户登录会话跟踪（10分钟无操作则会话结束）
- CI/CD 构建流程监控（失败后10分钟无人工干预则告警）
- 故障排查会话（问题发生到解决的完整过程）
- 应用部署流程跟踪

---

## 模板上下文转换

模板上下文是连接配置和 SQL 的桥梁，由 `TemplateContext.build_context()` 生成。

### 转换流程

```
CorrelationRules + AggregationRules
          ↓
TemplateContext.build_context()
          ↓
context = {
    # 窗口参数
    "window_type": "session",
    "window_size": "10min",
    "window_size_seconds": 600,
    ...
    
    # 策略参数
    "strategy_type": "threshold",
    "filters": [...],
    "custom_aggregations": {...},
    ...
}
          ↓
TemplateEngine.render_sql(context)
          ↓
SQL 语句
```

### 上下文字段映射

#### 通用字段（所有窗口）

| 上下文字段 | 来源 | 说明 |
|-----------|------|------|
| `window_type` | `CorrelationRules.window_type` | 窗口类型 |
| `strategy_type` | `AggregationRules.strategy_type` | 策略类型 |
| `rule_id` | `CorrelationRules.id` | 规则ID |
| `rule_name` | `CorrelationRules.name` | 规则名称 |
| `filters` | `condition[0].filter` | 过滤条件数组 |
| `custom_aggregations` | `condition[0].aggregation_rules.custom_aggregations` | 自定义聚合 |
| `min_event_count` | `condition[0].aggregation_rules.min_event_count` | 最小事件数 |

#### Fixed Window 特有字段

| 上下文字段 | 来源 | 计算逻辑 |
|-----------|------|----------|
| `window_size` | `CorrelationRules.window_size` | 原始字符串（如 "10min"） |
| `window_size_seconds` | 计算 | `TimeUtils.parse_time_str_to_seconds("10min")` → 600 |
| `alignment` | `CorrelationRules.alignment` | 对齐方式（"minute" / "hour"） |
| `window_start` | 计算（可选） | `TimeUtils.align_to_window(current_time, 600, "minute")` |

#### Sliding Window 特有字段

| 上下文字段 | 来源 | 计算逻辑 |
|-----------|------|----------|
| `window_size` | `CorrelationRules.window_size` | 原始字符串 |
| `window_size_seconds` | 计算 | `parse_time_str_to_seconds(window_size)` |
| `slide_interval` | `CorrelationRules.slide_interval` | 原始字符串 |
| `slide_interval_seconds` | 计算 | `parse_time_str_to_seconds(slide_interval)` |

#### Session Window 特有字段

| 上下文字段 | 来源 | 计算逻辑 |
|-----------|------|----------|
| `session_timeout` | `CorrelationRules.session_timeout` | 原始字符串 |
| `session_timeout_seconds` | 计算 | `parse_time_str_to_seconds(session_timeout)` |
| `max_window_size` | `CorrelationRules.max_window_size` | 原始字符串（可选） |
| `max_window_size_seconds` | 计算 | `parse_time_str_to_seconds(max_window_size)` 或 None |

### 策略特有上下文

#### Threshold（阈值策略）

```python
{
    "strategy_config": {
        "field": "cpu_usage",
        "operator": ">=",
        "value": 80,
        "aggregation": "AVG"
    },
    "threshold_field": "cpu_usage",      # 从 strategy_config 提取
    "threshold_operator": ">=",          # 从 strategy_config 提取
    "threshold_value": 80,               # 从 strategy_config 提取
    "aggregation_function": "AVG"        # 从 strategy_config 提取
}
```

#### Composite（复合策略）

```python
{
    "strategy_config": {
        "logic": "AND",
        "conditions": [...]
    },
    "logic": "AND",                      # 组合逻辑
    "condition_count": 2,                # 条件数量
    "filters": [...],                    # 所有过滤器
    "aggregation_keys": [...]            # 分组键
}
```

#### Frequency（频率策略）

```python
{
    "strategy_config": {
        "count_threshold": 10,
        "time_window": "5min"
    },
    "count_threshold": 10,               # 次数阈值
    "time_window": "5min",               # 时间窗口
    "failure_count_expr": "COUNT(*)"     # 计数表达式
}
```

---

## SQL 生成流程

### Jinja2 模板结构

SQL 模板位于 `templates/unified_aggregation.jinja`，采用三层 CTE 架构：

```sql
WITH filtered_events AS (
  -- 第零层：事件过滤
  SELECT * FROM events WHERE ...
),

window_assignment AS (
  -- 第一层：窗口分配（根据窗口类型不同）
  {% if window_type == 'fixed' %}
    -- 固定窗口逻辑
  {% elif window_type == 'sliding' %}
    -- 滑动窗口逻辑
  {% elif window_type == 'session' %}
    -- 会话窗口逻辑
  {% endif %}
),

{% if window_type == 'session' %}
session_numbered AS (
  -- 第二层：会话编号（仅会话窗口）
  SELECT *, SUM(is_session_start) OVER (...) AS session_id
  FROM window_assignment
),
{% endif %}

strategy_metrics AS (
  -- 第三层：策略计算和聚合
  SELECT ..., COUNT(*) AS event_count, ...
  FROM {% if window_type == 'session' %}session_numbered{% else %}window_assignment{% endif %}
  GROUP BY ...
),

final_query AS (
  -- 第四层：最终过滤
  SELECT * FROM strategy_metrics
  WHERE event_count >= {{ min_event_count }}
)

SELECT * FROM final_query
ORDER BY window_start DESC, fingerprint
```

### 按窗口类型的 SQL 差异

#### Fixed Window SQL

```sql
window_assignment AS (
  SELECT *,
    -- 窗口 ID: 时间戳 / 窗口大小（秒）
    FLOOR(EPOCH(received_at) / {{ window_size_seconds }}) AS window_id,
    
    -- 窗口起始时间
    TO_TIMESTAMP(
      FLOOR(EPOCH(received_at) / {{ window_size_seconds }}) * {{ window_size_seconds }}
    ) AS window_start,
    
    -- 窗口结束时间
    TO_TIMESTAMP(
      (FLOOR(EPOCH(received_at) / {{ window_size_seconds }}) + 1) * {{ window_size_seconds }}
    ) AS window_end
  FROM filtered_events
)
```

**关键变量**：
- `{{ window_size_seconds }}`: 从 `window_size="10min"` 转换为 `600`
- 窗口ID计算：`FLOOR(EPOCH(received_at) / 600)` 确保时间对齐

#### Sliding Window SQL

```sql
window_assignment AS (
  SELECT *,
    -- 窗口起始时间（当前时间 - 窗口大小）
    received_at - INTERVAL '{{ window_size }}' AS window_start,
    
    -- 窗口结束时间（当前时间）
    received_at AS window_end,
    
    -- 窗口 ID（基于滑动间隔对齐）
    FLOOR(EPOCH(received_at) / {{ slide_interval_seconds }}) AS window_id
  FROM filtered_events
)
```

**关键变量**：
- `{{ window_size }}`: 字符串，如 `"10 minutes"`（直接用于 INTERVAL）
- `{{ slide_interval_seconds }}`: 数字，如 `60`（用于窗口ID计算）

#### Session Window SQL

```sql
window_assignment AS (
  SELECT *,
    -- 计算与上一个事件的时间间隔
    received_at - LAG(received_at, 1, received_at) OVER (
      PARTITION BY fingerprint 
      ORDER BY received_at
    ) AS time_since_last_event,
    
    -- 标记会话边界（间隔超过 timeout = 新会话）
    CASE 
      WHEN received_at - LAG(received_at, 1, received_at) OVER (
        PARTITION BY fingerprint 
        ORDER BY received_at
      ) > INTERVAL '{{ session_timeout }}' 
      THEN 1 
      ELSE 0 
    END AS is_session_start
  FROM filtered_events
),

session_numbered AS (
  SELECT *,
    -- 累计会话边界标记，生成会话 ID
    SUM(is_session_start) OVER (
      PARTITION BY fingerprint 
      ORDER BY received_at
      ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS session_id,
    
    -- 会话开始时间
    FIRST_VALUE(received_at) OVER (
      PARTITION BY fingerprint
      ORDER BY received_at
      ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS window_start
  FROM window_assignment
)
```

**关键变量**：
- `{{ session_timeout }}`: 字符串，如 `"10 minutes"`
- `{{ max_window_size }}`: 可选，用于最终过滤超长会话

**关键技术**：
1. `LAG()`: 获取上一个事件的时间
2. `SUM() OVER()`: 累计会话边界标记生成会话ID
3. `PARTITION BY fingerprint`: 按指纹分组，确保不同资源的会话独立

---

## 完整示例

### 示例1: Fixed Window + Threshold（CPU 阈值告警）

#### 1️⃣ 数据库配置

#### 1️⃣ 数据库配置

```python
# CorrelationRules（规则实例 - 实际执行配置）
{
    "name": "CPU高使用率告警",
    "window_type": "fixed",        # 用户选择的窗口类型（可基于推荐）
    "window_size": "5min",         # 用户配置的参数
    "alignment": "minute",
    "scope": "global",
    "rule_type": "alert"
}

# AggregationRules（规则模板 - 包含推荐配置）
{
    "rule_id": "cpu_threshold_001",
    "name": "CPU阈值检查",
    "strategy_type": "threshold",
    "strategy_config": {
        "field": "value",
        "operator": ">=",
        "value": 80,
        "aggregation": "AVG"
    },
    
    # 窗口推荐配置（用于前端表单）
    "window_config": {
        "recommended_types": ["fixed", "sliding"],
        "default_type": "fixed",
        "default_params": {
            "fixed": {
                "window_size": "5min",
                "alignment": "minute",
                "description": "每5分钟检查一次，适合定期巡检",
                "use_case": "定期统计"
            },
            "sliding": {
                "window_size": "10min",
                "slide_interval": "1min",
                "description": "实时滑动监控，反应更灵敏",
                "use_case": "实时监控"
            }
        },
        "not_recommended": ["session"],
        "reason": "性能指标监控是持续性的，不需要会话边界检测"
    },
    
    "condition": [{
        "filter": {
            "item": {"operator": "=", "value": "cpu_usage"},
            "resource_type": {"operator": "=", "value": "server"}
        },
        "aggregation_key": ["resource_id", "resource_name"],
        # 注意：不再包含 window_config
        "aggregation_rules": {
            "min_event_count": 3,
            "custom_aggregations": {
                "avg_cpu": "AVG(value)",
                "max_cpu": "MAX(value)",
                "min_cpu": "MIN(value)"
            }
        }
    }]
}
```# 2️⃣ 模板上下文

```python
context = {
    # 基础信息
    "window_type": "fixed",
    "strategy_type": "threshold",
    "rule_id": 1,
    "rule_name": "CPU高使用率告警",
    
    # 窗口参数
    "window_size": "5min",
    "window_size_seconds": 300,
    "alignment": "minute",
    
    # 过滤条件
    "filters": [{
        "item": {"operator": "=", "value": "cpu_usage"},
        "resource_type": {"operator": "=", "value": "server"}
    }],
    
    # 聚合配置
    "custom_aggregations": {
        "avg_cpu": "AVG(value)",
        "max_cpu": "MAX(value)",
        "min_cpu": "MIN(value)"
    },
    "min_event_count": 3,
    
    # 策略配置
    "strategy_config": {
        "field": "value",
        "operator": ">=",
        "value": 80,
        "aggregation": "AVG"
    }
}
```

#### 3️⃣ 生成的 SQL

```sql
WITH filtered_events AS (
  SELECT *
  FROM events
  WHERE 1=1
    AND item = 'cpu_usage'
    AND resource_type = 'server'
),

window_assignment AS (
  SELECT *,
    FLOOR(EPOCH(received_at) / 300) AS window_id,
    TO_TIMESTAMP(FLOOR(EPOCH(received_at) / 300) * 300) AS window_start,
    TO_TIMESTAMP((FLOOR(EPOCH(received_at) / 300) + 1) * 300) AS window_end
  FROM filtered_events
),

strategy_metrics AS (
  SELECT
    fingerprint,
    resource_id,
    resource_name,
    resource_type,
    source_id,
    alert_source,
    rule_id,
    window_id,
    window_start,
    window_end,
    
    -- 通用指标
    COUNT(*) AS event_count,
    MAX(level) AS max_level,
    LIST(event_id) AS event_ids,
    MIN(received_at) AS first_event_time,
    MAX(received_at) AS last_event_time,
    
    -- 自定义聚合
    AVG(value) AS avg_cpu,
    MAX(value) AS max_cpu,
    MIN(value) AS min_cpu
  
  FROM window_assignment
#### 1️⃣ 数据库配置

```python
# CorrelationRules（规则实例 - 实际执行配置）
{
    "name": "Jenkins构建失败会话",
    "window_type": "session",      # 用户选择：session（基于推荐）
    "session_timeout": "10min",    # 用户配置（基于推荐的默认值）
    "max_window_size": "1h",
    "scope": "global",
    "rule_type": "alert"
}

# AggregationRules（规则模板 - 包含推荐配置）
{
    "rule_id": "jenkins_failure_001",
    "name": "Jenkins构建失败监控",
    "strategy_type": "composite",
    "strategy_config": {
        "logic": "AND",
        "session_timeout": "10min",
        "success_closes_session": True
    },
    
    # 窗口推荐配置
    "window_config": {
        "recommended_types": ["session"],  # 强烈推荐会话窗口
        "default_type": "session",
        "default_params": {
            "session": {
                "session_timeout": "10min",
                "max_window_size": "1h",
                "description": "适合追踪完整的构建流程（从失败到修复）",
                "use_case": "监控CI/CD流程"
            }
        },
        "not_recommended": ["fixed", "sliding"],
        "reason": "构建流程有明确的开始和结束，需要会话窗口自动检测边界"
    },
    
    "condition": [{
        "filter": {
            "resource_type": {"operator": "=", "value": "jenkins"},
            "item": {"operator": "=", "value": "build_status"}
        },
        "aggregation_key": ["resource_id", "resource_name"],
        # 注意：不再包含 window_config
        "aggregation_rules": {
            "min_event_count": 1,
            "custom_aggregations": {
                "failure_count": "COUNT(*) FILTER (WHERE value = 0)",
                "success_count": "COUNT(*) FILTER (WHERE value = 1)",
                "session_duration_minutes": "EXTRACT(EPOCH FROM (MAX(received_at) - MIN(received_at))) / 60",
                "build_ids": "STRING_AGG(DISTINCT labels->>'build_id', ', ')"
            }
        },
        "session_close": {
            "enabled": True,
            "filter": {
                "value": {"operator": "=", "value": 1}
            },
            "action": "close_session"
        }
    }]
}
```     "aggregation_rules": {
            "min_event_count": 1,
            "custom_aggregations": {
                "failure_count": "COUNT(*) FILTER (WHERE value = 0)",
                "success_count": "COUNT(*) FILTER (WHERE value = 1)",
                "session_duration_minutes": "EXTRACT(EPOCH FROM (MAX(received_at) - MIN(received_at))) / 60",
                "build_ids": "STRING_AGG(DISTINCT labels->>'build_id', ', ')"
            }
        },
        "session_close": {
            "enabled": True,
            "filter": {
                "value": {"operator": "=", "value": 1}
            },
            "action": "close_session"
        }
    }]
}
```

#### 2️⃣ 模板上下文

```python
context = {
    # 基础信息
    "window_type": "session",
    "strategy_type": "composite",
    "rule_id": 2,
    "rule_name": "Jenkins构建失败会话",
    
    # 会话参数
    "session_timeout": "10min",
    "session_timeout_seconds": 600,
    "max_window_size": "1h",
    "max_window_size_seconds": 3600,
    
    # 过滤条件
    "filters": [{
        "resource_type": {"operator": "=", "value": "jenkins"},
        "item": {"operator": "=", "value": "build_status"}
    }],
    
    # 聚合配置
    "custom_aggregations": {
        "failure_count": "COUNT(*) FILTER (WHERE value = 0)",
        "success_count": "COUNT(*) FILTER (WHERE value = 1)",
        "session_duration_minutes": "EXTRACT(EPOCH FROM (MAX(received_at) - MIN(received_at))) / 60",
        "build_ids": "STRING_AGG(DISTINCT labels->>'build_id', ', ')"
    },
    "min_event_count": 1,
    
    # 策略配置
    "logic": "AND",
    "session_close": {
        "enabled": True,
        "filter": {"value": {"operator": "=", "value": 1}},
        "action": "close_session"
    }
}
```

#### 3️⃣ 生成的 SQL

```sql
WITH filtered_events AS (
  SELECT *
  FROM events
  WHERE 1=1
    AND resource_type = 'jenkins'
    AND item = 'build_status'
),

window_assignment AS (
  SELECT *,
    received_at - LAG(received_at, 1, received_at) OVER (
      PARTITION BY fingerprint 
      ORDER BY received_at
    ) AS time_since_last_event,
    
    CASE 
      WHEN received_at - LAG(received_at, 1, received_at) OVER (
        PARTITION BY fingerprint 
        ORDER BY received_at
      ) > INTERVAL '10 minutes' 
      THEN 1 
      ELSE 0 
    END AS is_session_start
  FROM filtered_events
),

session_numbered AS (
  SELECT *,
    SUM(is_session_start) OVER (
      PARTITION BY fingerprint 
      ORDER BY received_at
      ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS session_id,
    
    FIRST_VALUE(received_at) OVER (
      PARTITION BY fingerprint
      ORDER BY received_at
      ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS window_start
  FROM window_assignment
),

strategy_metrics AS (
  SELECT
    fingerprint,
    resource_id,
    resource_name,
    resource_type,
    source_id,
    alert_source,
    rule_id,
    session_id AS window_id,
    window_start,
    
    -- 通用指标
    COUNT(*) AS event_count,
    MAX(level) AS max_level,
### Step 1: 选择窗口类型

根据监控场景选择合适的窗口类型：

- **定期检查** → Fixed Window
- **实时监控** → Sliding Window  
- **会话/流程跟踪** → Session Window

**智能推荐**: 如果使用内置规则模板，前端会根据 `window_config` 自动推荐合适的窗口类型并预填充参数。

### Step 2: 配置 CorrelationRules（规则实例）

```python
from apps.alerts.models import CorrelationRules

# 用户根据推荐选择窗口类型和参数（或自定义）
rule = CorrelationRules.objects.create(
    name="规则名称",
    window_type="session",              # 用户选择（可基于推荐）
    session_timeout="10min",             # 用户配置（可使用推荐的默认值）
    max_window_size="1h",                # 可选参数
    scope="global",
    rule_type="alert"
)
```

### Step 3: 配置 AggregationRules（规则模板）

```python
from apps.alerts.models import AggregationRules

agg_rule = AggregationRules.objects.create(
    rule_id="unique_rule_id",
    name="聚合规则名称",
    strategy_type="threshold",
    
    # 策略配置
    strategy_config={
        "field": "value",
        "operator": ">=",
        "value": 80
    },
    
    # 窗口推荐配置（用于前端表单）
    window_config={
        "recommended_types": ["fixed", "sliding"],
        "default_type": "fixed",
        "default_params": {
            "fixed": {
                "window_size": "5min",
                "alignment": "minute",
                "description": "每5分钟检查一次",
                "use_case": "定期统计"
            }
        },
        "not_recommended": ["session"],
        "reason": "持续性指标不需要会话边界"
    },
    
    # 执行条件（不包含 window_config）
    condition=[{
        "filter": {
            "item": {"operator": "=", "value": "cpu_usage"}
        },
        "aggregation_key": ["resource_id"],
        "aggregation_rules": {
            "min_event_count": 3,
            "custom_aggregations": {
                "avg_value": "AVG(value)",
                "max_value": "MAX(value)"
            }
        }
    }]
)

# 关联规则
rule.aggregation_rules.add(agg_rule)
```m apps.alerts.models import AggregationRules

agg_rule = AggregationRules.objects.create(
    rule_id="unique_rule_id",
    name="聚合规则名称",
    strategy_type="threshold",          # 选择策略类型
    strategy_config={
        # 根据策略类型填写简化配置
        "field": "value",
        "operator": ">=",
        "value": 80
    },
    condition=[{
        "filter": {
            # 过滤条件
            "item": {"operator": "=", "value": "cpu_usage"}
        },
        "aggregation_key": ["resource_id"],
        "aggregation_rules": {
            "min_event_count": 3,
## 常见问题

### Q1: 窗口配置应该在哪里配置？

**答**: 
- **实际执行配置**: 在 `CorrelationRules` 模型中配置（规则实例）
- **推荐配置**: 在 `AggregationRules.window_config` 中配置（规则模板）
- **执行时**: 模板上下文**只读取** `CorrelationRules` 的配置
- **前端表单**: 读取 `window_config` 进行智能推荐和参数预填充

### Q2: 为什么 condition 不包含 window_config？

**答**: 
- ✅ **避免配置冗余**: 窗口配置在 `CorrelationRules` 统一管理
- ✅ **单一数据源**: 执行时只从 `CorrelationRules` 读取，避免不一致
- ✅ **职责清晰**: `CorrelationRules` 管理"如何聚合"，`condition` 管理"聚合什么"
- ✅ **易于维护**: 修改窗口配置只需修改一处

### Q3: 如何选择窗口类型？

| 场景 | 推荐窗口 | 原因 |
|------|---------|------|
| 定期统计（每5分钟） | Fixed | 窗口不重叠，统计清晰 |
| 实时监控（最近10分钟） | Sliding | 可重叠，反应灵敏 |
| 用户会话跟踪 | Session | 动态边界，自动检测 |
| CI/CD 流程 | Session | 流程有明确开始/结束 |

**提示**: 使用内置规则时，`window_config` 会提供推荐。

### Q4: custom_aggregations 支持哪些函数？

- JSON：`labels->>'key'`

### Q5: 如何实现复杂过滤？
# 使用测试工具验证
from apps.alerts.aggregation_v2.templates.engine import TemplateEngine
from apps.alerts.aggregation_v2.templates.context import TemplateContext

# 构建上下文
context = TemplateContext.build_context(rule)
print(context)

# 生成 SQL
engine = TemplateEngine()
sql = engine.render_sql(rule)
print(sql)
```

---

## 常见问题

### Q1: 如何选择窗口类型？

| 场景 | 推荐窗口 | 原因 |
|------|---------|------|
| 定期统计（每5分钟） | Fixed | 窗口不重叠，统计清晰 |
| 实时监控（最近10分钟） | Sliding | 可重叠，反应灵敏 |
}
```

### Q6: Session Window 如何防止无限扩展？函数？

所有 DuckDB 支持的聚合函数和表达式：
- 基础：`COUNT()`, `SUM()`, `AVG()`, `MAX()`, `MIN()`
- 字符串：`STRING_AGG()`, `LIST()`, `ARRAY_AGG()`
- 条件：`COUNT(*) FILTER (WHERE ...)`
- 时间：`EXTRACT(EPOCH FROM ...)`, `DATE_DIFF()`
- JSON：`labels->>'key'`

WHERE (last_event_time - first_event_time) <= INTERVAL '1 hour'
```

### Q7: 如何使用内置规则的推荐配置？

**前端实现示例**:
```javascript
// 1. 用户选择内置规则
const aggRule = await fetchAggregationRule(ruleId);

// 2. 读取推荐配置
const windowConfig = aggRule.window_config;

// 3. 显示推荐窗口类型
windowConfig.recommended_types.forEach(type => {
  showOption(type, { recommended: true });
});

// 4. 自动选择默认窗口类型
form.setValue('window_type', windowConfig.default_type);

// 5. 预填充默认参数
const defaultParams = windowConfig.default_params[windowConfig.default_type];
Object.keys(defaultParams).forEach(key => {
  if (key !== 'description' && key !== 'use_case') {
    form.setValue(key, defaultParams[key]);
  }
});

// 6. 显示说明
showTip(defaultParams.description);

// 7. 不推荐的类型显示警告
windowConfig.not_recommended.forEach(type => {
  showWarning(type, windowConfig.reason);
});
```

---

## 设计优势

### 新设计的优点

| 方面 | 优势 |
|------|------|
| **灵活性** | 用户可基于推荐选择，也可完全自定义 |
| **易用性** | 智能推荐 + 参数预填充，降低配置门槛 |
| **可维护性** | 推荐配置集中管理，便于更新最佳实践 |
| **数据一致性** | 执行配置单一来源（CorrelationRules） |
| **专家知识** | 内置规则包含最佳实践和使用建议 |
| **向后兼容** | 不影响现有执行逻辑 |

---

## 参考资料stom_sql": "(value > 80 AND level >= 3) OR (value > 90)"
}
```

### Q4: Session Window 如何防止无限扩展？

设置 `max_window_size`：
```python
max_window_size = "1h"  # 会话最长1小时
```

SQL 会自动过滤超时会话：
```sql
WHERE (last_event_time - first_event_time) <= INTERVAL '1 hour'
```

---

## 参考资料

- **完整示例**: `EXAMPLES.md`
- **配置架构**: `RULE_CONFIG_SCHEMA.md`
- **快速参考**: `QUICK_REFERENCE.md`
- **SQL 模板**: `templates/unified_aggregation.jinja`
- **上下文构建器**: `templates/context.py`

---
