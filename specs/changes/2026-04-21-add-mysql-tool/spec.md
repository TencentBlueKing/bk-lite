# 2026 04 21 Add Mysql Tool

Status: done

## Migration Context

- Legacy source: `openspec/changes/archive/2026-04-21-add-mysql-tool/`
- Legacy state: `archived`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

## Why

OpsPilot 已有 PostgreSQL、MSSQL、Redis 等数据库工具，但缺少 MySQL 工具。MySQL 是国内使用最广泛的关系型数据库之一，用户需要通过 LLM 对 MySQL 实例进行巡检、诊断、查询和优化。同时参照 Redis 工具的多实例架构，MySQL 工具需从设计之初就支持批量连接多个实例，实现一次调用巡检所有 MySQL 实例。

## What Changes

- 新增 `server/apps/opspilot/metis/llm/tools/mysql/` 工具包，包含约 35 个子工具，覆盖资源发现、动态查询、故障诊断、运行监控、优化建议、性能分析六大类
- 新增 MySQL 多实例连接管理（`connection.py`），复用 `common/credentials.py` 的 `NormalizedCredentials` + `execute_with_credentials()` 批量执行机制
- 在 `tools_loader.py` 中注册 `mysql` 工具模块
- 新增 `mysql-connector-python` 依赖
- 所有工具支持 `instance_name` / `instance_id` 参数，不指定时对所有已配置实例批量执行

## Capabilities

### New Capabilities
- `mysql-tool-multi-instance`: MySQL 工具的多实例配置、连接管理、批量执行能力，以及 35 个子工具（资源发现、动态查询、故障诊断、运行监控、优化建议、性能分析）

### Modified Capabilities
（无需修改现有 spec）

## Impact

- **代码**: `server/apps/opspilot/metis/llm/tools/` 新增 `mysql/` 目录（约 9 个文件）；`tools_loader.py` 新增注册项
- **依赖**: `server/pyproject.toml` 新增 `mysql-connector-python`
- **API**: 无外部 API 变更，工具通过现有 `tools_loader` 机制暴露给 LLM
- **安全**: 所有查询经过 `validate_sql_safety()` 校验，支持 `SET SESSION TRANSACTION READ ONLY`，敏感字段屏蔽
- **兼容性**: 纯新增功能，不影响现有工具

## Implementation Decisions

## Context

OpsPilot 的 LLM 工具体系已包含 PostgreSQL（44 个工具，单实例模式）、MSSQL（37 个工具，单实例模式）和 Redis（60+ 个工具，多实例模式）。MySQL 工具需要同时借鉴两个方向：

- **工具分类与 SQL 安全机制**：沿用 postgres/mssql 的子模块划分（resources、dynamic、diagnostics、monitoring、optimization、analysis）和 `validate_sql_safety()` 安全校验
- **多实例批量执行架构**：沿用 Redis 的 `NormalizedCredentials` + `execute_with_credentials()` 机制，通过 `common/credentials.py` 统一调度

当前 MSSQL 和 PostgreSQL 工具仍为单实例模式（`CONSTRUCTOR_PARAMS` 为平铺的 host/port/user/password 字段）。MySQL 工具从设计之初就采用多实例模式。

## Goals / Non-Goals

**Goals:**
- 提供 35 个 MySQL 运维工具，覆盖资源发现、动态查询、故障诊断、运行监控、优化建议、性能分析
- 支持多实例配置，不指定实例时批量巡检所有实例
- 支持 `instance_name` / `instance_id` 参数定向单个实例
- 兼容旧单实例平铺字段配置（legacy 模式）
- SQL 注入防护和只读事务保护

**Non-Goals:**
- 不改造现有 PostgreSQL/MSSQL 工具为多实例模式（后续单独变更）
- 不支持 MySQL 写操作（INSERT/UPDATE/DELETE）
- 不提供前端 UI 编辑器（本次仅后端工具层）
- 不支持 MySQL Group Replication / InnoDB Cluster 高级拓扑管理

## Decisions

### Decision 1: 驱动选择 `mysql-connector-python`

**选择**: `mysql-connector-python`（Oracle 官方维护）
**替代方案**: `pymysql`（纯 Python，社区维护）、`mysqlclient`（C 扩展，需编译环境）

**理由**:
- 纯 Python 实现，无需 C 编译环境，与仓库 Docker 构建流程兼容
- Oracle 官方维护，MySQL 8.x 新特性支持及时
- MCP Server 参考项目也使用此驱动，验证了可行性
- 支持 `charset`/`collation`/`sql_mode` 的细粒度配置

### Decision 2: 多实例架构复用 Redis 的 credentials 模式

**选择**: 复用 `common/credentials.py` 的 `NormalizedCredentials` + `execute_with_credentials()` + `CredentialAdapter` 协议

**替代方案**: 独立实现多实例管理（如 MSSQL/PG 当前的单实例模式）

**理由**:
- Redis 已验证该模式可稳定工作
- `execute_with_credentials()` 的单/多分发逻辑是通用的，无需重复实现
- `MysqlCredentialAdapter` 只需实现 4 个方法即可接入
- 保持工具体系内部一致性，后续 PG/MSSQL 升级多实例也可复用

### Decision 3: 只读保护策略

**选择**: 使用 `SET SESSION TRANSACTION READ ONLY` + `validate_sql_safety()` 双重防护

**替代方案**: 仅靠 `validate_sql_safety()` 关键词黑名单

**理由**:
- MySQL 5.6.5+ 支持 `SET SESSION TRANSACTION READ ONLY`，在数据库层面阻止写操作
- `validate_sql_safety()` 在应用层拦截危险 SQL（`DROP`/`ALTER`/`LOAD`/`FLUSH` 等）
- 双重防护比单一防护更安全

### Decision 4: MySQL 特有的禁止关键词列表

在通用禁止词（`DROP`/`ALTER`/`TRUNCATE`/`CREATE`/`GRANT`/`REVOKE`/`INSERT`/`UPDATE`/`DELETE`）基础上，新增 MySQL 特有：

```
LOAD, HANDLER, FLUSH, PURGE, RESET, CHANGE, INSTALL, UNINSTALL,
PREPARE, EXECUTE, DEALLOCATE, KILL, LOCK, UNLOCK
```

### Decision 5: 文件结构

```
mysql/
├── __init__.py          CONSTRUCTOR_PARAMS(多实例) + 导入 + __all__
├── connection.py        MysqlCredentialAdapter + 连接管理 + 实例提示
├── utils.py             prepare_context + 公共函数 + validate_sql_safety
├── resources.py         8 个工具（资源发现）
├── dynamic.py           5 个工具（动态查询）
├── diagnostics.py       7 个工具（故障诊断）
├── monitoring.py        8 个工具（运行监控）
├── optimization.py      4 个工具（优化建议）
└── analysis.py          3 个工具（性能分析）
```

### Decision 6: CONSTRUCTOR_PARAMS 设计

```python
CONSTRUCTOR_PARAMS = [
    {"name": "mysql_instances", "type": "string", "required": False,
     "description": "MySQL多实例JSON配置"},
    {"name": "mysql_default_instance_id", "type": "string", "required": False,
     "description": "默认MySQL实例ID"},
]
```

实例字段：`id`, `name`, `host`, `port`(3306), `database`(mysql), `user`, `password`, `charset`(utf8mb4), `collation`(utf8mb4_unicode_ci), `ssl`, `ssl_ca`, `ssl_cert`, `ssl_key`

### Decision 7: 连接配置借鉴 MCP Server

从 `designcomputer/mysql_mcp_server` 借鉴以下连接配置实践：
- 默认 `charset=utf8mb4`，`collation=utf8mb4_unicode_ci`（避免不同 MySQL 版本的 utf8mb4_0900_ai_ci 兼容问题）
- `autocommit=True`（只读工具无需手动事务管理）
- `sql_mode` 可配置（默认 `TRADITIONAL`）

### Decision 8: 工具注册

在 `tools_loader.py` 中新增：
```python
from apps.opspilot.metis.llm.tools import mysql
"mysql": (mysql, False),
```

`enable_extra_prompt=False`，与 postgres/mssql 一致。多实例提示通过 `get_mysql_instances_prompt()` 注入。

## Risks / Trade-offs

**[Risk] mysql-connector-python 性能不如 mysqlclient** → 本工具面向运维诊断场景，非高并发查询，纯 Python 驱动的性能足够。若后续有性能瓶颈，可替换为 mysqlclient，连接接口兼容。

**[Risk] 批量巡检多实例时某个实例超时拖慢整体** → `execute_with_credentials()` 已实现 per-instance 异常捕获，单个实例失败不影响其他实例结果。可后续增加连接超时配置（`connect_timeout`）。

**[Risk] MySQL 5.x 与 8.x 的 SQL 兼容性差异** → 部分诊断 SQL 依赖 `performance_schema`（5.6+ 默认启用）和 `sys` schema（5.7+ 内置）。工具内部需对不支持的查询做 graceful fallback，返回提示而非报错。

**[Risk] 旧单实例配置升级到多实例** → 通过 `MysqlCredentialAdapter` 的 `build_from_flat_config` 支持 legacy 平铺字段，与 Redis 的升级策略一致。

**[Trade-off] 35 个工具 vs 更少的工具集** → 工具数量多但语义明确，LLM 可精确选择。比单一 `execute_sql` 更安全可控，代价是实现工作量较大。

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-04-21
```

## Capability Deltas

### mysql-tool-multi-instance

## ADDED Requirements

### Requirement: MySQL 工具支持多实例配置

单个智能体中的 MySQL 工具 SHALL 允许用户配置多个 MySQL 实例，而不是仅支持一套连接参数。

#### Scenario: 配置多个 MySQL 实例

- **WHEN** 用户通过 `mysql_instances` JSON 字段配置多个 MySQL 实例
- **THEN** 系统 SHALL 解析并持久化所有实例配置
- **AND** 每个实例 SHALL 包含 `id`、`name`、`host`、`port`、`database`、`user`、`password` 字段
- **AND** 每个实例 SHALL 可选配置 `charset`、`collation`、`ssl`、`ssl_ca`、`ssl_cert`、`ssl_key` 字段

#### Scenario: 配置默认实例

- **WHEN** 用户通过 `mysql_default_instance_id` 指定默认实例
- **THEN** 系统 SHALL 将该实例作为未显式指定时的连接目标

### Requirement: MySQL 工具支持默认实例与显式实例切换

MySQL 工具运行时 SHALL 在多个已配置实例之间稳定选择连接目标。

#### Scenario: 未显式指定实例时执行（单实例配置）

- **WHEN** 仅配置一个 MySQL 实例且工具调用未提供实例标识
- **THEN** 系统 SHALL 使用该唯一实例建立连接
- **AND** 返回结果 SHALL 为单实例格式（不包装聚合结构）

#### Scenario: 未显式指定实例时执行（多实例配置）

- **WHEN** 配置多个 MySQL 实例且工具调用未提供实例标识
- **THEN** 系统 SHALL 对所有已配置实例批量执行该工具
- **AND** 返回结果 SHALL 为聚合格式，包含 `mode`、`total`、`succeeded`、`failed`、`results` 字段

#### Scenario: 显式指定实例时执行

- **WHEN** 工具调用提供 `instance_id` 或 `instance_name`
- **THEN** 系统 SHALL 解析到对应 MySQL 实例并仅使用该实例建立连接
- **AND** 返回结果 SHALL 为单实例格式

#### Scenario: 指定实例不存在

- **WHEN** 工具调用指定的实例标识无法匹配到已配置实例
- **THEN** 系统 SHALL 返回明确错误信息
- **AND** 系统 SHALL 不得静默回退到其他实例

### Requirement: 旧单实例 MySQL 配置可被平滑升级

MySQL 工具 SHALL 允许通过平铺字段（host/port/database/user/password）进行旧式单实例配置，并兼容新的多实例协议。

#### Scenario: 使用平铺字段配置

- **WHEN** 用户未配置 `mysql_instances`，而是通过平铺字段提供连接信息
- **THEN** 系统 SHALL 将其视为单实例配置
- **AND** 系统 SHALL 正常建立连接并执行工具

#### Scenario: 平铺字段与多实例配置冲突

- **WHEN** 用户同时提供 `mysql_instances` 和平铺字段
- **THEN** 系统 SHALL 抛出 `CredentialConflictError`
- **AND** 系统 SHALL 不得执行任何数据库操作

### Requirement: 批量执行中单个实例失败不影响其他实例

MySQL 工具在多实例批量执行模式下 SHALL 保证单个实例的失败不阻断其他实例。

#### Scenario: 部分实例连接失败

- **WHEN** 批量执行时某个实例连接超时或认证失败
- **THEN** 系统 SHALL 在该实例结果中标记 `ok: false` 并记录错误信息
- **AND** 系统 SHALL 继续对剩余实例执行工具
- **AND** 聚合结果中 `failed` 字段 SHALL 正确反映失败数量

#### Scenario: 所有实例均失败

- **WHEN** 批量执行时所有实例均连接失败
- **THEN** 系统 SHALL 返回聚合结果，`succeeded` 为 0
- **AND** 每个实例的错误信息 SHALL 被独立保留

### Requirement: MySQL 工具提供资源发现能力

MySQL 工具 SHALL 提供数据库资源发现工具集，帮助 LLM 了解 MySQL 实例的基本结构。

#### Scenario: 获取数据库基本信息

- **WHEN** 调用 `get_current_database_info` 工具
- **THEN** 系统 SHALL 返回 MySQL 版本、字符集、当前数据库名、存储引擎等基本信息

#### Scenario: 列出所有数据库

- **WHEN** 调用 `list_mysql_databases` 工具
- **THEN** 系统 SHALL 返回实例上所有数据库的列表及大小信息

#### Scenario: 列出表结构

- **WHEN** 调用 `get_table_structure` 工具并指定表名
- **THEN** 系统 SHALL 返回该表的列定义、数据类型、约束、索引和注释

### Requirement: MySQL 工具提供安全的动态查询能力

MySQL 工具 SHALL 提供受保护的动态 SQL 查询工具，防止 SQL 注入和非授权写操作。

#### Scenario: 执行安全的 SELECT 查询

- **WHEN** 调用 `execute_safe_select` 工具并传入 SQL 语句
- **THEN** 系统 SHALL 通过 `validate_sql_safety()` 校验 SQL 安全性
- **AND** 系统 SHALL 在只读事务中执行查询（`SET SESSION TRANSACTION READ ONLY`）
- **AND** 系统 SHALL 屏蔽敏感字段（password、secret、token 等列）

#### Scenario: 拦截危险 SQL

- **WHEN** 调用 `execute_safe_select` 并传入包含 `DROP`/`ALTER`/`LOAD`/`FLUSH` 等禁止关键词的 SQL
- **THEN** 系统 SHALL 拒绝执行并返回安全校验错误
- **AND** 系统 SHALL 不向 MySQL 发送该 SQL

#### Scenario: 查看查询执行计划

- **WHEN** 调用 `explain_query_plan` 工具并传入 SELECT 语句
- **THEN** 系统 SHALL 执行 `EXPLAIN` 并返回执行计划详情

### Requirement: MySQL 工具提供故障诊断能力

MySQL 工具 SHALL 提供故障诊断工具集，帮助 DBA 快速定位常见问题。

#### Scenario: 诊断慢查询

- **WHEN** 调用 `diagnose_slow_queries` 工具
- **THEN** 系统 SHALL 从 `performance_schema` 或 `slow_query_log` 相关视图中获取慢查询信息
- **AND** 返回结果 SHALL 包含查询文本摘要、执行次数、平均耗时

#### Scenario: 诊断锁冲突

- **WHEN** 调用 `diagnose_lock_conflicts` 工具
- **THEN** 系统 SHALL 查询 InnoDB 锁等待信息并返回阻塞链

#### Scenario: 综合健康检查

- **WHEN** 调用 `check_database_health` 工具
- **THEN** 系统 SHALL 返回运行时间、线程数、连接使用率、缓冲池命中率等综合指标

#### Scenario: 诊断死锁

- **WHEN** 调用 `diagnose_deadlocks` 工具
- **THEN** 系统 SHALL 解析 `SHOW ENGINE INNODB STATUS` 中的最近死锁信息

### Requirement: MySQL 工具提供运行监控能力

MySQL 工具 SHALL 提供运行时监控指标采集工具集。

#### Scenario: 获取数据库级别指标

- **WHEN** 调用 `get_database_metrics` 工具
- **THEN** 系统 SHALL 返回 QPS、TPS、连接数、线程活跃数等核心运行指标

#### Scenario: 获取 InnoDB 状态

- **WHEN** 调用 `get_innodb_stats` 工具
- **THEN** 系统 SHALL 返回缓冲池使用率、脏页数、IO 读写量、行锁等待等 InnoDB 引擎指标

#### Scenario: 查看活跃会话

- **WHEN** 调用 `get_processlist` 工具
- **THEN** 系统 SHALL 返回当前活跃会话列表，包含用户、主机、命令、执行时间、SQL 文本

#### Scenario: 检查主从复制状态

- **WHEN** 调用 `check_replication_status` 工具
- **THEN** 系统 SHALL 返回复制线程状态、GTID 位点、延迟秒数等复制详情

### Requirement: MySQL 工具提供优化建议能力

MySQL 工具 SHALL 提供索引和配置优化建议工具集。

#### Scenario: 检测未使用的索引

- **WHEN** 调用 `check_unused_indexes` 工具
- **THEN** 系统 SHALL 基于 `performance_schema` 统计识别从未被使用的索引

#### Scenario: 配置调优建议

- **WHEN** 调用 `check_configuration_tuning` 工具
- **THEN** 系统 SHALL 检查 `innodb_buffer_pool_size`、`max_connections`、`query_cache`（5.x）等关键配置并给出调优建议

### Requirement: MySQL 工具提供性能分析能力

MySQL 工具 SHALL 提供性能分析工具集，帮助理解数据库负载特征。

#### Scenario: 分析缓冲池使用

- **WHEN** 调用 `analyze_buffer_pool_usage` 工具
- **THEN** 系统 SHALL 返回缓冲池命中率、淘汰率、页分布等分析结果

#### Scenario: 分析查询模式

- **WHEN** 调用 `analyze_query_patterns` 工具
- **THEN** 系统 SHALL 基于 `performance_schema.events_statements_summary_by_digest` 分析查询模式分布

### Requirement: MySQL 工具在 tools_loader 中正确注册

MySQL 工具 SHALL 通过现有 `tools_loader.py` 的 `TOOL_MODULES` 机制被发现和加载。

#### Scenario: 工具加载

- **WHEN** `tools_loader` 接收到 `xxx:mysql` 格式的工具服务 URL
- **THEN** 系统 SHALL 从 `mysql` 模块加载所有 `StructuredTool` 对象
- **AND** 加载的工具数量 SHALL 为 35 个

#### Scenario: 工具元数据查询

- **WHEN** 调用 `get_all_tools_metadata()` 且 MySQL 工具已注册
- **THEN** 返回的元数据 SHALL 包含 `mysql` 工具及其 `CONSTRUCTOR_PARAMS`（`mysql_instances`、`mysql_default_instance_id`）

### Requirement: LLM 获得多实例上下文提示

MySQL 工具 SHALL 在多实例配置下向 LLM 注入可用实例信息，使 LLM 能正确选择目标实例。

#### Scenario: 生成实例提示

- **WHEN** 用户配置了多个 MySQL 实例
- **THEN** `get_mysql_instances_prompt()` SHALL 返回包含默认实例名称和所有可用实例名称的中文提示文本
- **AND** 提示 SHALL 告知 LLM 可通过 `instance_name` 或 `instance_id` 切换实例

## Work Checklist

## 1. 项目结构与依赖

- [x] 1.1 在 `server/pyproject.toml` 中新增 `mysql-connector-python` 依赖
- [x] 1.2 创建 `server/apps/opspilot/metis/llm/tools/mysql/` 目录及 `__init__.py`，定义 `CONSTRUCTOR_PARAMS`（`mysql_instances`、`mysql_default_instance_id`）

## 2. 连接管理（connection.py）

- [x] 2.1 定义 `MYSQL_INSTANCE_FIELDS` 元组（id/name/host/port/database/user/password/charset/collation/ssl/ssl_ca/ssl_cert/ssl_key）
- [x] 2.2 实现 `parse_mysql_instances()`：解析 JSON 字符串为实例列表，含字段归一化和默认值（port=3306, database=mysql, charset=utf8mb4, collation=utf8mb4_unicode_ci）
- [x] 2.3 实现 `resolve_mysql_instance()`：按 instance_id/instance_name/default_instance_id 定位实例
- [x] 2.4 实现 `MysqlCredentialAdapter`（实现 `CredentialAdapter` 协议的 4 个方法）
- [x] 2.5 实现 `build_mysql_normalized_from_runnable()`：多实例 → NormalizedCredentials，含 legacy 平铺字段回退
- [x] 2.6 实现 `get_mysql_connection_from_item()`：从 CredentialItem 创建 mysql.connector 连接（含 charset/collation/autocommit/sql_mode 配置）
- [x] 2.7 实现 `get_mysql_instances_prompt()`：生成多实例上下文提示文本

## 3. 公共工具函数（utils.py）

- [x] 3.1 实现 `prepare_context()`：从 RunnableConfig 提取 configurable
- [x] 3.2 实现 `execute_readonly_query()`：`SET SESSION TRANSACTION READ ONLY` + 执行查询 + 返回结果
- [x] 3.3 实现 `validate_sql_safety()`：通用禁止词 + MySQL 特有禁止词（LOAD/HANDLER/FLUSH/PURGE/RESET/CHANGE/INSTALL/UNINSTALL/PREPARE/EXECUTE/DEALLOCATE/KILL/LOCK/UNLOCK）
- [x] 3.4 实现 `format_size()`、`format_duration()`、`parse_mysql_version()`、`safe_json_dumps()`、`calculate_percentage()`

## 4. 资源发现工具（resources.py）— 8 个工具

- [x] 4.1 实现 `get_current_database_info`：返回版本、字符集、引擎、运行时间等
- [x] 4.2 实现 `list_mysql_databases`：列出所有数据库及大小
- [x] 4.3 实现 `list_mysql_tables`：列出指定数据库的所有表
- [x] 4.4 实现 `list_mysql_indexes`：列出表的索引信息
- [x] 4.5 实现 `list_mysql_schemas`：列出 schema
- [x] 4.6 实现 `get_table_structure`：返回列定义、类型、约束、索引、注释
- [x] 4.7 实现 `list_mysql_users`：列出用户及权限概览
- [x] 4.8 实现 `get_database_config`：返回关键配置变量

## 5. 动态查询工具（dynamic.py）— 5 个工具

- [x] 5.1 实现 `get_table_schema_details`：获取表详细 schema（含注释、外键）
- [x] 5.2 实现 `search_tables_by_keyword`：按关键词搜索表名/列名
- [x] 5.3 实现 `execute_safe_select`：安全执行 SELECT（validate_sql_safety + 只读事务 + 敏感字段屏蔽）
- [x] 5.4 实现 `explain_query_plan`：执行 EXPLAIN 返回执行计划
- [x] 5.5 实现 `get_sample_data`：获取表样本数据（屏蔽敏感字段，禁止 SELECT *）

## 6. 故障诊断工具（diagnostics.py）— 7 个工具

- [x] 6.1 实现 `diagnose_slow_queries`：从 performance_schema 获取慢查询
- [x] 6.2 实现 `diagnose_lock_conflicts`：查询 InnoDB 锁等待信息
- [x] 6.3 实现 `diagnose_connection_issues`：连接数分析（当前/最大/异常）
- [x] 6.4 实现 `check_database_health`：综合健康检查
- [x] 6.5 实现 `check_replication_lag`：主从复制延迟检查
- [x] 6.6 实现 `diagnose_deadlocks`：解析 SHOW ENGINE INNODB STATUS 死锁信息
- [x] 6.7 实现 `get_failed_queries`：失败/错误查询统计

## 7. 运行监控工具（monitoring.py）— 8 个工具

- [x] 7.1 实现 `get_database_metrics`：QPS、TPS、连接数等核心指标
- [x] 7.2 实现 `get_table_metrics`：表行数、大小、碎片率
- [x] 7.3 实现 `get_innodb_stats`：缓冲池、脏页、IO、行锁等 InnoDB 指标
- [x] 7.4 实现 `get_io_stats`：磁盘 IO 统计（performance_schema）
- [x] 7.5 实现 `check_binary_log_status`：Binlog 状态与空间占用
- [x] 7.6 实现 `check_replication_status`：主从复制详细状态
- [x] 7.7 实现 `get_processlist`：当前活跃会话列表
- [x] 7.8 实现 `check_database_size_growth`：数据库空间增长趋势

## 8. 优化建议工具（optimization.py）— 4 个工具

- [x] 8.1 实现 `check_unused_indexes`：检测未使用的索引
- [x] 8.2 实现 `recommend_index_optimization`：冗余索引、缺失索引建议
- [x] 8.3 实现 `check_table_fragmentation`：表碎片分析与 OPTIMIZE 建议
- [x] 8.4 实现 `check_configuration_tuning`：配置调优建议

## 9. 性能分析工具（analysis.py）— 3 个工具

- [x] 9.1 实现 `analyze_buffer_pool_usage`：缓冲池命中率、淘汰率、页分布
- [x] 9.2 实现 `analyze_query_patterns`：基于 events_statements_summary_by_digest 的查询模式分析
- [x] 9.3 实现 `analyze_table_statistics`：表访问模式统计（读写比、全表扫描次数）

## 10. 工具注册与集成

- [x] 10.1 在 `tools_loader.py` 中添加 `from apps.opspilot.metis.llm.tools import mysql` 和 `"mysql": (mysql, False)` 注册
- [x] 10.2 在 `__init__.py` 中完成所有 35 个工具的导入和 `__all__` 导出

## 11. 验证

- [x] 11.1 验证 `tools_loader` 能正确加载 mysql 模块并发现 35 个 StructuredTool
- [x] 11.2 验证多实例配置下批量执行返回聚合结果格式正确
- [x] 11.3 验证单实例指定下返回非包装结果
- [x] 11.4 验证 legacy 平铺字段配置兼容性
- [x] 11.5 验证 `validate_sql_safety()` 拦截所有 MySQL 特有危险关键词
- [x] 11.6 执行 `cd server && make test` 确保无回归
