## Context

OpsPilot 的内置数据库工具（Redis id=-1、MySQL id=-2、Oracle id=-3）已全部采用多实例架构：
- **持久化协议**: `xxx_instances`（JSON 字符串）+ `xxx_default_instance_id`
- **连接管理**: `connection.py` 模块统一处理实例解析、归一化、测试连接、LLM 提示生成
- **前端编辑器**: 独立的 `xxxToolEditor.tsx` 组件，左侧实例列表 + 右侧配置表单
- **内置工具注册**: `builtin_tools.py` 定义 build/runtime 函数，`chat_service.py` 路由

MSSQL 工具的 LLM 工具函数已完成（30 个工具，分布在 resources/dynamic/diagnostics/monitoring 四个子模块），当前通过 `tools_loader.py` 注册但使用单实例扁平参数（host/port/database/user/password），未注册为内置工具，无前端编辑器。

## Goals / Non-Goals

**Goals:**
- 将 MSSQL 工具升级为多实例协议，与 MySQL/Oracle 保持一致的架构
- 注册为内置工具（id=-4），支持前端配置和测试连接
- 多实例批量执行：未指定实例时对所有实例执行，单实例时返回简单格式
- 前端多实例编辑器：实例列表 + 配置表单 + 测试连接状态

**Non-Goals:**
- 不新增或修改已有的 30 个 MSSQL LLM 工具函数
- 不支持 Windows 集成认证（仅 SQL Server 认证）
- 不支持 ODBC 驱动名称的前端配置（使用自动检测）

## Decisions

### 1. 内置工具 ID: -4

**决定**: MSSQL 使用 `BUILTIN_MSSQL_TOOL_ID = -4`

**理由**: 遵循现有递减编号惯例（Redis=-1, MySQL=-2, Oracle=-3）

### 2. CONSTRUCTOR_PARAMS 升级

**决定**: 从扁平字段升级为多实例协议

```python
# 旧
CONSTRUCTOR_PARAMS = [
    {"name": "host", ...}, {"name": "port", ...},
    {"name": "database", ...}, {"name": "user", ...}, {"name": "password", ...},
]

# 新
CONSTRUCTOR_PARAMS = [
    {"name": "mssql_instances", "type": "string", "required": False, "description": "MSSQL多实例JSON配置"},
    {"name": "mssql_default_instance_id", "type": "string", "required": False, "description": "默认MSSQL实例ID"},
]
```

**理由**: 与 Redis/MySQL/Oracle 一致，支持单工具管理多实例

### 3. 实例字段定义

**决定**: 每个 MSSQL 实例包含以下字段

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| id | string | uuid | 实例唯一标识 |
| name | string | `MSSQL - n` | 实例显示名称 |
| host | string | localhost | 服务器地址 |
| port | integer | 1433 | 端口 |
| database | string | master | 默认数据库 |
| user | string | sa | 用户名 |
| password | string | "" | 密码 |

**理由**: 与现有 MSSQL 工具的 `get_db_connection()` 参数一致，不引入额外字段

### 4. connection.py 模块结构

**决定**: 完全镜像 MySQL/Oracle 的 connection.py 模式

核心函数:
- `normalize_mssql_instance(instance)` — 归一化实例配置（类型转换、默认值）
- `parse_mssql_instances(raw)` — 解析 JSON 字符串/数组为实例列表
- `get_mssql_instances_from_configurable(configurable)` — 从 RunnableConfig 提取实例
- `resolve_mssql_instance(instances, default_id, name, id)` — 按优先级解析目标实例
- `test_mssql_instance(instance)` — 测试单个实例连接
- `get_mssql_instances_prompt(configurable)` — 生成 LLM 上下文提示

### 5. 前端编辑器

**决定**: 新建 `mssqlToolEditor.tsx`，完全参照 `oracleToolEditor.tsx` 的布局

- 左侧面板（260px）：实例列表 + 新增按钮
- 右侧面板（flex-1）：实例名称、host、port、database、user、password 表单
- 右上角：测试状态标记（未测试/成功/失败）
- 底部：测试连接按钮

**理由**: 保持所有数据库工具编辑器的一致体验

### 6. 工具函数中的连接获取方式

**决定**: 修改 `mssql/utils.py` 的 `prepare_context()` / `get_db_connection()` 从新协议读取连接参数

**理由**: 工具函数已使用 `RunnableConfig` 传参，只需在 connection 层面适配多实例解析即可，工具函数本身无需修改

## Risks / Trade-offs

**[Risk] 已有单实例配置的兼容性**
→ 升级 CONSTRUCTOR_PARAMS 后，如果有环境已保存旧格式的 MSSQL 工具配置，可能无法正确解析
→ **Mitigation**: `parse_mssql_instances()` 实现旧格式兼容（检测到扁平字段时自动转换为单实例列表）

**[Risk] ODBC 驱动依赖**
→ 测试连接需要运行环境已安装 ODBC Driver for SQL Server
→ **Mitigation**: 测试连接失败时返回清晰的驱动缺失提示信息

**[Trade-off] 不支持 Windows 认证**
→ 部分企业环境使用 Windows 集成认证
→ 初始版本仅支持 SQL Server 认证，后续可按需扩展
