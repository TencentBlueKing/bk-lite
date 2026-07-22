# 2026 06 05 Add Mssql Multi Instance Tool

Status: done

## Migration Context

- Legacy source: `openspec/changes/archive/2026-06-05-add-mssql-multi-instance-tool/`
- Legacy state: `archived`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

## Why

OpsPilot 已有 Redis、MySQL、Oracle 三种内置数据库工具，均支持多实例配置。MSSQL 工具的后端 LLM 工具函数（30+ tools）已在 `server/apps/opspilot/metis/llm/tools/mssql/` 完成，但仍停留在单实例扁平参数模式（host/port/database/user/password），且未注册为内置工具、没有前端编辑器。需要将其升级为多实例协议并补齐注册与 UI，使 MSSQL 与其他数据库工具具备一致的配置和运行体验。

## What Changes

- 将 MSSQL 工具的 `CONSTRUCTOR_PARAMS` 从单实例扁平字段升级为 `mssql_instances` + `mssql_default_instance_id` 多实例协议
- 新增 `mssql/connection.py`，实现多实例解析、实例解析、测试连接、LLM 提示生成
- 在 `builtin_tools.py` 中注册 MSSQL 为内置工具（id=-4）
- 在 `chat_service.py` 中添加 MSSQL 内置工具分支
- 在 `llm_view.py` 中添加 `test_mssql_connection` API 端点
- 在 `tools_loader.py` 中为 MSSQL 启用 `enable_extra_prompt=True`
- 新增前端 `mssqlToolEditor.tsx` 多实例编辑器组件
- 在 `toolSelector.tsx` 中集成 MSSQL 工具检测与编辑器路由
- 在 `skill.ts` 中添加 `testMssqlConnection` API 调用
- 添加中英文 i18n 键

## Capabilities

### New Capabilities
- `mssql-tool-multi-instance`: MSSQL 数据库工具多实例配置能力，包括多实例持久化、默认实例与显式切换、批量执行、测试连接、前端编辑器、LLM 上下文注入

### Modified Capabilities
（无需修改现有能力）

## Impact

**后端代码变更:**
- 新增: `server/apps/opspilot/metis/llm/tools/mssql/connection.py`
- 修改: `server/apps/opspilot/metis/llm/tools/mssql/__init__.py`（CONSTRUCTOR_PARAMS 升级）
- 修改: `server/apps/opspilot/services/builtin_tools.py`（注册 id=-4）
- 修改: `server/apps/opspilot/services/chat_service.py`（添加 mssql 分支）
- 修改: `server/apps/opspilot/viewsets/llm_view.py`（添加测试端点）
- 修改: `server/apps/opspilot/metis/llm/tools/tools_loader.py`（enable_extra_prompt）

**前端代码变更:**
- 新增: `web/src/app/opspilot/components/skill/mssqlToolEditor.tsx`
- 修改: `web/src/app/opspilot/components/skill/toolSelector.tsx`
- 修改: `web/src/app/opspilot/api/skill.ts`
- 修改: `web/src/app/opspilot/locales/zh.json`、`en.json`

**依赖:** 无新增（pyodbc 已在 pyproject.toml 中）

## Implementation Decisions

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

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-04-22
```

## Capability Deltas

### mssql-tool-multi-instance

## ADDED Requirements

### Requirement: MSSQL 工具支持多实例配置

单个智能体中的 MSSQL 工具 SHALL 允许用户配置多个 MSSQL 实例，而不是仅支持一套连接参数。

#### Scenario: 配置多个 MSSQL 实例

- **WHEN** 用户通过 `mssql_instances` JSON 字段配置多个 MSSQL 实例
- **THEN** 系统 SHALL 解析并持久化所有实例配置
- **AND** 每个实例 SHALL 包含 `id`、`name`、`host`、`port`、`database`、`user`、`password` 字段

#### Scenario: 配置默认实例

- **WHEN** 用户通过 `mssql_default_instance_id` 指定默认实例
- **THEN** 系统 SHALL 将该实例作为未显式指定时的连接目标

### Requirement: MSSQL 实例具有独立测试连接状态

MSSQL 工具编辑器 SHALL 为每个实例提供独立的测试连接能力与状态反馈。

#### Scenario: 初始或字段变更后的状态

- **WHEN** 用户新建一个 MSSQL 实例或修改该实例任一连接字段
- **THEN** 该实例状态 SHALL 显示为未测试

#### Scenario: 测试连接成功

- **WHEN** 用户对某个 MSSQL 实例执行测试连接且后端验证成功
- **THEN** 该实例状态 SHALL 显示为测试成功

#### Scenario: 测试连接失败

- **WHEN** 用户对某个 MSSQL 实例执行测试连接且后端验证失败
- **THEN** 该实例状态 SHALL 显示为测试失败
- **AND** 系统 SHALL 返回可用于提示用户的问题信息

### Requirement: MSSQL 工具支持默认实例与显式实例切换

MSSQL 工具运行时 SHALL 在多个已配置实例之间稳定选择连接目标。

#### Scenario: 未显式指定实例时执行（单实例配置）

- **WHEN** 仅配置一个 MSSQL 实例且工具调用未提供实例标识
- **THEN** 系统 SHALL 使用该唯一实例建立连接
- **AND** 返回结果 SHALL 为单实例格式（不包装聚合结构）

#### Scenario: 未显式指定实例时执行（多实例配置）

- **WHEN** 配置多个 MSSQL 实例且工具调用未提供实例标识
- **THEN** 系统 SHALL 对所有已配置实例批量执行该工具
- **AND** 返回结果 SHALL 为聚合格式，包含 `mode`、`total`、`succeeded`、`failed`、`results` 字段

#### Scenario: 显式指定实例时执行

- **WHEN** 工具调用提供 `instance_id` 或 `instance_name`
- **THEN** 系统 SHALL 解析到对应 MSSQL 实例并仅使用该实例建立连接
- **AND** 返回结果 SHALL 为单实例格式

#### Scenario: 指定实例不存在

- **WHEN** 工具调用指定的实例标识无法匹配到已配置实例
- **THEN** 系统 SHALL 返回明确错误信息
- **AND** 系统 SHALL 不得静默回退到其他实例

### Requirement: 旧单实例 MSSQL 配置可被平滑升级

MSSQL 工具 SHALL 允许通过平铺字段（host/port/database/user/password）进行旧式单实例配置，并兼容新的多实例协议。

#### Scenario: 使用平铺字段配置

- **WHEN** 用户未配置 `mssql_instances`，而是通过平铺字段提供连接信息
- **THEN** 系统 SHALL 将其视为单实例配置
- **AND** 系统 SHALL 正常建立连接并执行工具

#### Scenario: 平铺字段与多实例配置冲突

- **WHEN** 用户同时提供 `mssql_instances` 和平铺字段
- **THEN** 系统 SHALL 优先使用 `mssql_instances`
- **AND** 系统 SHALL 忽略平铺字段

### Requirement: 批量执行中单个实例失败不影响其他实例

MSSQL 工具在多实例批量执行模式下 SHALL 保证单个实例的失败不阻断其他实例。

#### Scenario: 部分实例连接失败

- **WHEN** 批量执行时某个实例连接超时或认证失败
- **THEN** 系统 SHALL 在该实例结果中标记 `ok: false` 并记录错误信息
- **AND** 系统 SHALL 继续对剩余实例执行工具
- **AND** 聚合结果中 `failed` 字段 SHALL 正确反映失败数量

### Requirement: MSSQL 工具注册为内置工具

MSSQL 工具 SHALL 通过 `builtin_tools.py` 注册为内置工具（id=-4），支持前端发现和配置。

#### Scenario: 工具列表中包含 MSSQL

- **WHEN** 前端请求工具列表
- **THEN** 返回的内置工具列表 SHALL 包含 MSSQL 工具
- **AND** 工具 SHALL 包含完整的子工具列表和 CONSTRUCTOR_PARAMS 元数据

#### Scenario: 运行时工具构建

- **WHEN** 智能体配置了 MSSQL 内置工具并发起对话
- **THEN** `chat_service` SHALL 识别 MSSQL 工具并调用 `build_builtin_mssql_runtime_tool`
- **AND** 运行时工具 SHALL 携带 `extra_tools_prompt` 描述可用实例信息

### Requirement: LLM 获得多实例上下文提示

MSSQL 工具 SHALL 在多实例配置下向 LLM 注入可用实例信息。

#### Scenario: 生成实例提示

- **WHEN** 用户配置了多个 MSSQL 实例
- **THEN** `get_mssql_instances_prompt()` SHALL 返回包含默认实例名称和所有可用实例名称的提示文本
- **AND** 提示 SHALL 告知 LLM 可通过 `instance_name` 或 `instance_id` 切换实例

## Work Checklist

## 1. Backend Connection Module

- [x] 1.1 Create `server/apps/opspilot/metis/llm/tools/mssql/connection.py` — implement `MSSQL_INSTANCE_FIELDS`, `normalize_mssql_instance()`, `parse_mssql_instances()`, `get_mssql_instances_from_configurable()`, `resolve_mssql_instance()`, `test_mssql_instance()`, `get_mssql_instances_prompt()`, legacy flat-field compatibility
- [x] 1.2 Update `server/apps/opspilot/metis/llm/tools/mssql/__init__.py` — change CONSTRUCTOR_PARAMS from flat fields to `mssql_instances` + `mssql_default_instance_id`
- [x] 1.3 Update `server/apps/opspilot/metis/llm/tools/mssql/utils.py` — modify `prepare_context()` / `get_db_connection()` to use multi-instance resolution via `connection.py`

## 2. Backend Registration & Integration

- [x] 2.1 Update `server/apps/opspilot/services/builtin_tools.py` — add `BUILTIN_MSSQL_TOOL_ID = -4`, `BUILTIN_MSSQL_TOOL_NAME = "mssql"`, `build_builtin_mssql_tool()`, `build_builtin_mssql_runtime_tool()`
- [x] 2.2 Update `server/apps/opspilot/services/chat_service.py` — add MSSQL built-in tool name matching branch
- [x] 2.3 Update `server/apps/opspilot/viewsets/llm_view.py` — add `test_mssql_connection` endpoint and include MSSQL in tool list API
- [x] 2.4 Update `server/apps/opspilot/metis/llm/tools/tools_loader.py` — set `enable_extra_prompt=True` for mssql module

## 3. Frontend Editor Component

- [x] 3.1 Create `web/src/app/opspilot/components/skill/mssqlToolEditor.tsx` — multi-instance editor with left panel (instance list + add button) and right panel (name, host, port, database, user, password fields + test status badge)
- [x] 3.2 Update `web/src/app/opspilot/components/skill/toolSelector.tsx` — add `isMssqlTool()`, `parseMssqlToolConfig()`, `serializeMssqlToolConfig()`, `getDefaultMssqlInstance()`, `getNextMssqlInstanceName()`, state hooks, event handlers, and modal integration
- [x] 3.3 Update `web/src/app/opspilot/api/skill.ts` — add `testMssqlConnection` API function

## 4. Localization

- [x] 4.1 Update `web/src/app/opspilot/locales/zh.json` — add `tool.mssql.*` section (host, port, database, user, password, instance name, status labels, test connection, etc.)
- [x] 4.2 Update `web/src/app/opspilot/locales/en.json` — add corresponding English `tool.mssql.*` keys

## 5. Verification

- [x] 5.1 Run `cd server && make test` to verify no backend regressions
- [x] 5.2 Run `cd web && pnpm lint && pnpm type-check` to verify frontend compiles
