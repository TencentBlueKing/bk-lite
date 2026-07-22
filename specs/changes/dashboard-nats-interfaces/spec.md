# Dashboard Nats Interfaces

Status: in-progress

## Migration Context

- Legacy source: `openspec/changes/dashboard-nats-interfaces/`
- Legacy state: `active`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

## Why

运营分析仪表盘需要展示 CMDB 和告警的统计数据，包括单值组件（模型总数、实例总数、告警总数等）、趋势图（变更趋势、告警趋势）、饼状图（主机按 OS 统计、告警等级分布）和表格（模型统计、活跃告警 TOP 10）。

当前已有的 NATS 接口无法满足这些场景：
- CMDB 模块缺少统计类接口（模型/实例计数、变更趋势、分组统计）
- Alerts 模块仅有 `get_alert_trend_data` 趋势接口，缺少计数和分布统计接口

## What Changes

- 在 CMDB 模块新增 4 个 NATS 接口：统计数据、变更趋势、实例分组统计、模型实例统计
- 在 Alerts 模块新增 3 个 NATS 接口：告警统计、等级分布、活跃告警 TOP N
- 所有接口遵循现有 NATS 注册模式（`@nats_client.register`）
- CMDB 接口支持组织过滤（与 `query_asset_instances` 一致）
- Alerts 接口不加组织过滤（与 `get_alert_trend_data` 一致）

## Capabilities

### New Capabilities
- `cmdb-dashboard-statistics`: CMDB 仪表盘统计数据接口，支持模型/实例计数、变更趋势、分组统计
- `alerts-dashboard-statistics`: 告警仪表盘统计数据接口，支持告警/事件/事故计数、等级分布、活跃告警排行

### Modified Capabilities
- 无

## Impact

- `server/apps/cmdb/nats/nats.py`: 新增 4 个 NATS 接口
- `server/apps/alerts/nats/nats.py`: 新增 3 个 NATS 接口
- 依赖现有数据模型：`ChangeRecord`、`Alert`、`Event`、`Incident`
- 依赖现有服务：`ModelManage`、`ClassificationManage`、`InstanceManage`

## Implementation Decisions

## Overview

新增 7 个 NATS 接口，分别服务于 CMDB 和 Alerts 仪表盘场景。所有接口遵循现有 `@nats_client.register` 注册模式，返回格式与现有接口保持一致。

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        仪表盘 NATS 数据流                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   前端 Widget                                                               │
│       │                                                                     │
│       ▼                                                                     │
│   operation_analysis/views/datasource_view.py                               │
│       │                                                                     │
│       ▼                                                                     │
│   GetNatsData (NATS RPC Client)                                             │
│       │                                                                     │
│       ├──────────────────────┬──────────────────────┐                       │
│       ▼                      ▼                      ▼                       │
│   cmdb/nats/nats.py    alerts/nats/nats.py    monitor/nats/monitor.py      │
│   (4 new interfaces)   (3 new interfaces)     (existing)                   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Interface Design

### CMDB 模块接口（需要组织过滤）

#### 1. get_cmdb_statistics

```python
@nats_client.register
def get_cmdb_statistics(user_info=None, **kwargs):
    """
    获取 CMDB 统计数据

    Args:
        user_info: { team: int, user: str } - 由 operation_analysis 自动注入

    Returns:
        {
            "result": True,
            "data": {
                "model_count": 15,
                "instance_count": 1234,
                "classification_count": 5
            },
            "message": ""
        }
    """
```

数据源：
- `model_count`: `ModelManage.search_model()` 返回列表长度
- `instance_count`: 遍历所有模型调用 `InstanceManage.model_inst_count()` 求和
- `classification_count`: `ClassificationManage.search_model_classification()` 返回列表长度

#### 2. get_change_trend

```python
@nats_client.register
def get_change_trend(time, group_by="day", model_id=None, user_info=None, **kwargs):
    """
    获取 CMDB 变更趋势数据

    Args:
        time: [start_time, end_time] - 时间范围，格式 "YYYY-MM-DD HH:MM:SS"
        group_by: "day" | "hour" | "week" | "month" - 分组方式
        model_id: str | None - 可选，按模型过滤
        user_info: { team: int, user: str }

    Returns:
        {
            "result": True,
            "data": {
                "create": [["2026-04-15", 10], ["2026-04-16", 8]],
                "update": [["2026-04-15", 25], ["2026-04-16", 30]],
                "delete": [["2026-04-15", 2], ["2026-04-16", 1]]
            },
            "message": ""
        }
    """
```

数据源：
- `ChangeRecord` 模型
- 按 `type` 字段分组：`create_entity`, `update_entity`, `delete_entity`
- 按 `created_at` 时间截断分组统计

#### 3. get_instance_group_by

```python
@nats_client.register
def get_instance_group_by(model_id, field, user_info=None, **kwargs):
    """
    获取实例分组统计（饼状图用）

    Args:
        model_id: str - 模型 ID，如 "host"
        field: str - 分组字段，如 "os_type"
        user_info: { team: int, user: str }

    Returns:
        {
            "result": True,
            "data": [
                {"name": "Linux", "value": 100},
                {"name": "Windows", "value": 50},
                {"name": "AIX", "value": 5},
                {"name": "Unix", "value": 3},
                {"name": "Other", "value": 2}
            ],
            "message": ""
        }
    """
```

数据源：
- 图数据库查询，按指定字段 GROUP BY
- 对于枚举字段（如 `os_type`），需要将 ID 转换为显示名称

枚举映射（os_type）：
```python
os_type_map = {
    "1": "Linux",
    "2": "Windows",
    "3": "AIX",
    "4": "Unix",
    "other": "Other"
}
```

#### 4. get_model_inst_statistics

```python
@nats_client.register
def get_model_inst_statistics(user_info=None, **kwargs):
    """
    获取模型实例统计（表格用）

    Args:
        user_info: { team: int, user: str }

    Returns:
        {
            "result": True,
            "data": [
                {"classification": "主机管理", "model": "主机", "model_id": "host", "count": 100},
                {"classification": "主机管理", "model": "物理服务器", "model_id": "physical_server", "count": 20},
                {"classification": "中间件", "model": "Nginx", "model_id": "nginx", "count": 15}
            ],
            "message": ""
        }
    """
```

数据源：
- `ClassificationManage.search_model_classification()` 获取分类
- `ModelManage.search_model()` 获取模型
- `InstanceManage.model_inst_count()` 获取各模型实例数

### Alerts 模块接口（不需要组织过滤）

#### 5. get_alert_statistics

```python
@nats_client.register
def get_alert_statistics(**kwargs):
    """
    获取告警统计数据

    Returns:
        {
            "result": True,
            "data": {
                "total_count": 500,
                "active_count": 45,
                "pending_count": 20,
                "processing_count": 25,
                "event_count": 1200,
                "incident_count": 8
            },
            "message": ""
        }
    """
```

数据源：
- `Alert.objects.count()` - 告警总数
- `Alert.objects.filter(status__in=AlertStatus.ACTIVATE_STATUS).count()` - 活跃告警
- `Alert.objects.filter(status=AlertStatus.PENDING).count()` - 未响应
- `Alert.objects.filter(status=AlertStatus.PROCESSING).count()` - 处理中
- `Event.objects.count()` - 事件总数
- `Incident.objects.count()` - 事故总数

#### 6. get_alert_level_distribution

```python
@nats_client.register
def get_alert_level_distribution(status_filter=None, **kwargs):
    """
    获取告警等级分布（饼状图用）

    Args:
        status_filter: "active" | None - 可选，仅统计活跃告警

    Returns:
        {
            "result": True,
            "data": [
                {"name": "致命", "value": 10},
                {"name": "严重", "value": 25},
                {"name": "预警", "value": 50},
                {"name": "提醒", "value": 15}
            ],
            "message": ""
        }
    """
```

数据源：
- `Alert.objects.values('level').annotate(count=Count('id'))`
- 如果 `status_filter="active"`，添加 `.filter(status__in=AlertStatus.ACTIVATE_STATUS)`

等级映射：
```python
level_map = {
    "fatal": "致命",
    "severity": "严重",
    "warning": "预警",
    "remain": "提醒"
}
```

#### 7. get_active_alert_top

```python
@nats_client.register
def get_active_alert_top(limit=10, **kwargs):
    """
    获取活跃告警持续时间 TOP N

    Args:
        limit: int - 返回数量，默认 10

    Returns:
        {
            "result": True,
            "data": [
                {
                    "alert_id": "ALERT-ABC123",
                    "title": "CPU使用率过高",
                    "level": "严重",
                    "status": "pending",
                    "duration_seconds": 86400,
                    "created_at": "2026-04-19 10:00:00",
                    "resource_name": "web-server-01"
                }
            ],
            "message": ""
        }
    """
```

数据源：
- `Alert.objects.filter(status__in=AlertStatus.ACTIVATE_STATUS)`
- 持续时间计算：`now() - created_at`（与现有告警页面一致）
- 按持续时间降序排序，取前 N 条

## Decisions

1. **组织过滤策略**：CMDB 接口需要组织过滤（与 `query_asset_instances` 一致），Alerts 接口不需要（与 `get_alert_trend_data` 一致）
2. **持续时间计算**：使用 `now() - created_at`，与现有告警页面 serializer 保持一致
3. **命名风格**：统一使用 `get_xxx` 前缀
4. **返回格式**：统一使用 `{"result": bool, "data": ..., "message": str}` 格式
5. **枚举显示**：将枚举 ID 转换为中文显示名称（如 os_type、level）

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-04-20
```

## Work Checklist

## 1. CMDB 统计接口

- [x] 1.1 在 `server/apps/cmdb/nats/nats.py` 中实现 `get_cmdb_statistics` 接口，返回模型总数、实例总数、分类总数
- [x] 1.2 在 `server/apps/cmdb/nats/nats.py` 中实现 `get_change_trend` 接口，基于 `ChangeRecord` 模型统计变更趋势（新增/修改/删除）
- [x] 1.3 在 `server/apps/cmdb/nats/nats.py` 中实现 `get_instance_group_by` 接口，支持按指定字段分组统计实例（如主机按 os_type 统计）
- [x] 1.4 在 `server/apps/cmdb/nats/nats.py` 中实现 `get_model_inst_statistics` 接口，返回模型统计表格数据（分类、模型、数量）

## 2. Alerts 统计接口

- [x] 2.1 在 `server/apps/alerts/nats/nats.py` 中实现 `get_alert_statistics` 接口，返回告警/事件/事故各类计数
- [x] 2.2 在 `server/apps/alerts/nats/nats.py` 中实现 `get_alert_level_distribution` 接口，返回告警等级分布（支持活跃/全部过滤）
- [x] 2.3 在 `server/apps/alerts/nats/nats.py` 中实现 `get_active_alert_top` 接口，返回活跃告警持续时间 TOP N

## 3. 验证

- [x] 3.1 执行 `cd server && make lint` 确保代码风格符合规范
- [ ] 3.2 手动验证：通过仪表盘数据源配置调用新接口，确认返回数据格式正确
