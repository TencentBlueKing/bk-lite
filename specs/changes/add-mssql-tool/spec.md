# Add Mssql Tool

Status: draft

## Migration Context

- Legacy source: `openspec/changes/add-mssql-tool/`
- Legacy state: `active`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

## Why

OpsPilot 的 Metis 智能体当前支持 PostgreSQL 数据库运维工具，但缺少对 Microsoft SQL Server (MSSQL) 的支持。企业用户普遍存在 MSSQL 数据库运维需求，新增 MSSQL 工具可以扩展 Metis 的数据库运维能力覆盖面，满足更多企业用户场景。

## What Changes

- 新增 `mssql` 工具模块，位于 `server/apps/opspilot/metis/llm/tools/mssql/`
- 参考 PostgreSQL 工具实现，提供完整的 MSSQL 运维工具集：
  - 基础资源查询（数据库、表、索引、Schema、角色）
  - 动态 SQL 安全查询
  - 故障诊断（慢查询、锁、连接问题）
  - 性能分析（配置、统计信息）
  - 监控指标采集
- 在 `tools_loader.py` 的 `TOOL_MODULES` 中注册 `mssql` 工具
- 新增 `pyodbc` 依赖到 server 的 `pyproject.toml`（opspilot optional-dependencies）

## Capabilities

### New Capabilities

- `mssql-tool`: Microsoft SQL Server 数据库运维工具集，包括资源查询、动态 SQL 执行、故障诊断、性能分析和监控指标采集功能

### Modified Capabilities

（无需修改现有能力）

## Impact

**代码变更:**
- 新增目录: `server/apps/opspilot/metis/llm/tools/mssql/`
- 修改文件: `server/apps/opspilot/metis/llm/tools/tools_loader.py`
- 修改文件: `server/apps/opspilot/metis/llm/tools/__init__.py`

**依赖变更:**
- 新增 `pyodbc>=5.2.0` 到 `server/pyproject.toml` 的 `[project.optional-dependencies] opspilot` 部分

**系统要求:**
- 需要在运行环境安装 ODBC Driver 17 for SQL Server（或更高版本）

**API 兼容性:**
- 新增工具，不影响现有 API
- 遵循现有工具的 CONSTRUCTOR_PARAMS 模式，支持 host、port、database、user、password 配置

## Implementation Decisions

## Context

OpsPilot 的 Metis 智能体目前通过 `server/apps/opspilot/metis/llm/tools/` 目录管理各类运维工具。PostgreSQL 工具已经实现了完整的数据库运维能力（8个子模块，40+工具函数），采用 `psycopg2` 作为驱动，通过 `@tool` 装饰器暴露 LangChain 工具。

当前架构特点：
- **工具加载**: `tools_loader.py` 通过 `TOOL_MODULES` 字典静态注册工具模块
- **连接管理**: 每个工具模块有独立的 `utils.py` 管理连接，使用 `RunnableConfig` 传递配置参数
- **安全机制**: 动态 SQL 工具实现了安全验证（禁止写操作、敏感字段过滤）
- **参数配置**: 通过 `CONSTRUCTOR_PARAMS` 元数据定义工具集的构造参数

项目中已存在 MSSQL 连接示例：`agents/stargazer/plugins/inputs/mssql/mssql_info.py` 使用 `pyodbc` 连接 MSSQL。

## Goals / Non-Goals

**Goals:**
- 实现 MSSQL 工具模块，与 PostgreSQL 工具保持一致的架构和使用体验
- 提供核心运维能力：资源查询、动态 SQL、故障诊断、监控指标
- 复用现有工具模式，最小化代码改动
- 使用 pyodbc 作为 MSSQL 驱动（项目已有使用先例）

**Non-Goals:**
- 不实现 PostgreSQL 特有功能（如 pg_stat_statements、WAL 监控等）
- 不实现 MSSQL 高级特性（如 AlwaysOn、Replication 详细监控）
- 不修改现有 PostgreSQL 工具的实现
- 不支持 SQL Server 2014 以下版本

## Decisions

### 1. 驱动选择：pyodbc

**决定**: 使用 `pyodbc>=5.2.0` 作为 MSSQL 连接驱动

**理由**:
- 项目中 `stargazer` 模块已使用 pyodbc 连接 MSSQL，有现成的使用模式
- pyodbc 是 ODBC 标准实现，稳定性好、兼容性强
- 支持 SQL Server 2016+ 的所有功能

**备选方案**:
- `pymssql`: 纯 Python 实现，不需要 ODBC 驱动，但功能受限、维护不活跃
- `sqlalchemy`: 抽象层过重，不适合直接执行原生 SQL 查询

### 2. 模块结构：精简的 PostgreSQL 模式

**决定**: 采用精简的模块结构（5个子模块）

```
mssql/
├── __init__.py      # 工具集入口、CONSTRUCTOR_PARAMS、导出
├── utils.py         # 连接管理、通用工具函数
├── resources.py     # 基础资源查询（数据库/表/索引/Schema/角色）
├── dynamic.py       # 动态 SQL 安全查询
├── diagnostics.py   # 故障诊断（慢查询/锁/连接）
└── monitoring.py    # 监控指标采集
```

**理由**:
- MSSQL 系统视图与 PostgreSQL 不同，部分功能无法直接映射
- 精简模块降低初始实现复杂度，后续可按需扩展
- 保留核心运维能力，满足 80% 使用场景

**PostgreSQL 模块未映射**:
- `optimization.py`: MSSQL 优化建议需要不同的系统视图
- `tracing.py`: 依赖 Extended Events，实现复杂度高
- `analysis.py`: 部分功能可合并到 diagnostics

### 3. 连接管理模式

**决定**: 复用 PostgreSQL 的 `prepare_context` + `get_db_connection` 模式

```python
CONSTRUCTOR_PARAMS = [
    {"name": "host", "type": "string", "required": False, "description": "MSSQL服务器地址,默认localhost"},
    {"name": "port", "type": "integer", "required": False, "description": "端口,默认1433"},
    {"name": "database", "type": "string", "required": False, "description": "默认连接的数据库"},
    {"name": "user", "type": "string", "required": False, "description": "用户名"},
    {"name": "password", "type": "string", "required": False, "description": "密码"},
]
```

**理由**: 保持与 PostgreSQL 工具一致的配置体验，用户无需学习新的参数模式

### 4. ODBC 驱动配置

**决定**: 使用 "ODBC Driver 17 for SQL Server" 作为默认驱动，支持配置覆盖

**理由**:
- Driver 17 是微软推荐的最新稳定版本
- 支持 TLS 1.2、AlwaysOn 等现代特性
- 允许通过环境变量或配置覆盖驱动名称

### 5. 系统视图映射

**决定**: 使用 MSSQL 原生系统视图和 DMV（Dynamic Management Views）

| PostgreSQL | MSSQL |
|------------|-------|
| `pg_database` | `sys.databases` |
| `pg_tables` | `INFORMATION_SCHEMA.TABLES` |
| `pg_indexes` | `sys.indexes` + `sys.index_columns` |
| `pg_stat_activity` | `sys.dm_exec_sessions` + `sys.dm_exec_requests` |
| `pg_locks` | `sys.dm_tran_locks` |
| `pg_stat_statements` | `sys.dm_exec_query_stats` |

## Risks / Trade-offs

**[Risk] ODBC 驱动依赖**
→ 需要在运行环境安装 ODBC Driver 17 for SQL Server，增加部署复杂度
→ **Mitigation**: 文档中明确系统依赖，提供 Docker 镜像配置示例

**[Risk] SQL 方言差异**
→ MSSQL 的 T-SQL 与 PostgreSQL 语法有显著差异，动态 SQL 验证逻辑需要调整
→ **Mitigation**: 在 `dynamic.py` 中实现 MSSQL 特定的 SQL 安全验证函数

**[Risk] 权限要求**
→ 部分 DMV 需要 VIEW SERVER STATE 权限
→ **Mitigation**: 工具描述中标注权限要求，返回清晰的权限不足错误信息

**[Trade-off] 功能覆盖度**
→ 初始版本不包含所有 PostgreSQL 工具的对等功能
→ 优先实现高频使用的核心功能，后续根据用户反馈迭代

**[Trade-off] 只读事务**
→ MSSQL 不支持 PostgreSQL 的 `BEGIN TRANSACTION READ ONLY` 语法
→ 使用 `SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED` 或 snapshot isolation 替代

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-03-02
```

## Capability Deltas

### mssql-tool

## ADDED Requirements

### Requirement: MSSQL 工具模块结构

系统 SHALL 在 `server/apps/opspilot/metis/llm/tools/mssql/` 目录下提供 MSSQL 工具模块，包含以下子模块：
- `__init__.py`: 工具集入口，定义 CONSTRUCTOR_PARAMS 和导出所有工具函数
- `utils.py`: 连接管理和通用工具函数
- `resources.py`: 基础资源查询工具
- `dynamic.py`: 动态 SQL 安全查询工具
- `diagnostics.py`: 故障诊断工具
- `monitoring.py`: 监控指标采集工具

#### Scenario: 模块加载成功
- **WHEN** 系统启动并加载 MSSQL 工具模块
- **THEN** `tools_loader.py` 的 `TOOL_MODULES` 字典中包含 `mssql` 键，且工具函数被正确注册

#### Scenario: CONSTRUCTOR_PARAMS 定义正确
- **WHEN** 获取 MSSQL 工具的构造参数元数据
- **THEN** 返回包含 host、port、database、user、password 的参数列表，与 PostgreSQL 工具格式一致

---

### Requirement: MSSQL 连接管理

系统 SHALL 通过 `utils.py` 提供 MSSQL 数据库连接管理功能，使用 pyodbc 驱动。

连接参数：
- host: MSSQL 服务器地址，默认 localhost
- port: 端口，默认 1433
- database: 默认连接的数据库
- user: 用户名
- password: 密码

#### Scenario: 成功建立数据库连接
- **WHEN** 调用 `get_db_connection` 函数并提供有效的连接参数
- **THEN** 返回 pyodbc 连接对象，连接超时设置为 10 秒

#### Scenario: 连接失败返回清晰错误
- **WHEN** 连接参数无效或服务器不可达
- **THEN** 抛出异常并记录错误日志，包含服务器地址和端口信息

#### Scenario: 使用 RunnableConfig 传递参数
- **WHEN** 工具函数通过 `config: RunnableConfig` 参数接收配置
- **THEN** `prepare_context` 函数从 `config.configurable` 中提取连接参数

---

### Requirement: 基础资源查询工具

系统 SHALL 在 `resources.py` 中提供以下基础资源查询工具，每个工具使用 `@tool` 装饰器：

| 工具函数 | 功能描述 |
|----------|----------|
| `list_mssql_databases` | 列出所有数据库及基本信息（大小、状态、兼容级别） |
| `list_mssql_tables` | 列出指定数据库的表（表名、行数估算、大小） |
| `list_mssql_indexes` | 列出表的索引信息（索引名、类型、列） |
| `list_mssql_schemas` | 列出数据库中的 Schema |
| `get_table_structure` | 获取表结构详情（列名、类型、约束） |
| `get_current_database_info` | 获取当前连接的数据库信息 |
| `list_mssql_logins` | 列出数据库登录名和角色 |

#### Scenario: 列出所有数据库
- **WHEN** 调用 `list_mssql_databases` 工具
- **THEN** 返回 JSON 格式结果，包含 `total_databases` 和 `databases` 数组，每个数据库包含 name、size、state、compatibility_level

#### Scenario: 查询指定数据库的表
- **WHEN** 调用 `list_mssql_tables(database="mydb", schema_name="dbo")`
- **THEN** 返回该数据库中 dbo schema 下所有表的列表，包含表名、行数估算、数据大小

#### Scenario: 获取表结构
- **WHEN** 调用 `get_table_structure(table="users", schema_name="dbo")`
- **THEN** 返回表的列定义、主键、外键、索引信息的 JSON 结构

---

### Requirement: 动态 SQL 安全查询工具

系统 SHALL 在 `dynamic.py` 中提供安全的动态 SQL 查询工具，实现与 PostgreSQL 相同的安全机制。

安全要求：
- 仅允许 SELECT 和 WITH 开头的查询
- 禁止 INSERT、UPDATE、DELETE、DROP、CREATE、ALTER 等写操作
- 禁止多语句执行（分号分隔）
- 禁止查询敏感字段（password、secret、token 等）
- 自动添加 LIMIT/TOP 限制

#### Scenario: 执行合法 SELECT 查询
- **WHEN** 调用 `execute_safe_select(sql="SELECT id, name FROM users WHERE status = 'active'", limit=100)`
- **THEN** 返回查询结果的 JSON 格式，包含 success、row_count、data 字段

#### Scenario: 拒绝写操作查询
- **WHEN** 调用 `execute_safe_select(sql="DELETE FROM users WHERE id = 1")`
- **THEN** 返回错误信息 "SQL包含禁止的关键字: delete"，不执行任何查询

#### Scenario: 拒绝 SELECT * 查询
- **WHEN** 调用 `execute_safe_select(sql="SELECT * FROM users")`
- **THEN** 返回错误信息提示必须明确指定列名

#### Scenario: 自动添加 TOP 限制
- **WHEN** 调用 `execute_safe_select(sql="SELECT id, name FROM users", limit=50)` 且 SQL 中无 TOP 子句
- **THEN** 系统自动将查询改写为 `SELECT TOP 50 id, name FROM users`

---

### Requirement: 故障诊断工具

系统 SHALL 在 `diagnostics.py` 中提供 MSSQL 故障诊断工具：

| 工具函数 | 功能描述 |
|----------|----------|
| `diagnose_slow_queries` | 诊断慢查询，使用 sys.dm_exec_query_stats |
| `diagnose_lock_conflicts` | 检测锁冲突和阻塞，使用 sys.dm_tran_locks |
| `diagnose_connection_issues` | 诊断连接问题，使用 sys.dm_exec_sessions |
| `check_database_health` | 数据库健康检查（状态、空间、备份） |

#### Scenario: 诊断慢查询
- **WHEN** 调用 `diagnose_slow_queries(threshold_ms=1000, limit=20)`
- **THEN** 返回平均执行时间超过 1000ms 的查询列表，包含查询文本、调用次数、平均/最大执行时间

#### Scenario: 检测锁冲突
- **WHEN** 存在活跃的锁等待时调用 `diagnose_lock_conflicts`
- **THEN** 返回阻塞关系列表，包含被阻塞的 session_id、阻塞者的 session_id、等待资源、等待时长

#### Scenario: 无锁冲突时返回空结果
- **WHEN** 无锁等待时调用 `diagnose_lock_conflicts`
- **THEN** 返回 `{"total_blocked_sessions": 0, "lock_conflicts": [], "has_conflicts": false}`

#### Scenario: 权限不足返回清晰错误
- **WHEN** 用户没有 VIEW SERVER STATE 权限时调用诊断工具
- **THEN** 返回错误信息 "需要 VIEW SERVER STATE 权限"

---

### Requirement: 监控指标采集工具

系统 SHALL 在 `monitoring.py` 中提供 MSSQL 监控指标采集工具：

| 工具函数 | 功能描述 |
|----------|----------|
| `get_database_metrics` | 获取数据库级别指标（大小、连接数、事务统计） |
| `get_instance_metrics` | 获取实例级别指标（CPU、内存、IO） |
| `get_wait_stats` | 获取等待统计信息 |

#### Scenario: 获取数据库指标
- **WHEN** 调用 `get_database_metrics`
- **THEN** 返回所有用户数据库的指标，包含 database_name、size_mb、active_connections、transactions_per_sec

#### Scenario: 获取实例性能指标
- **WHEN** 调用 `get_instance_metrics`
- **THEN** 返回 SQL Server 实例的性能指标，包含 cpu_usage、memory_usage_mb、buffer_cache_hit_ratio

#### Scenario: 获取等待统计
- **WHEN** 调用 `get_wait_stats(top_n=10)`
- **THEN** 返回前 10 个等待类型及其等待时间、等待次数

---

### Requirement: 工具函数文档规范

每个工具函数 SHALL 遵循以下文档规范：

- 使用中文 docstring 描述工具功能
- 包含 "**何时使用此工具:**" 段落说明使用场景
- 包含 "**工具能力:**" 段落说明功能范围
- Args 段落描述每个参数
- Returns 段落描述返回格式

#### Scenario: 工具描述符合 LangChain 规范
- **WHEN** 工具被加载到 LangChain agent
- **THEN** agent 可以正确理解工具的用途和参数，并在合适的场景调用

---

### Requirement: 错误处理规范

所有工具函数 SHALL 遵循统一的错误处理规范：

- 捕获数据库异常并返回 JSON 格式错误信息
- 错误信息包含 `error` 字段和描述性文本
- 连接错误包含服务器地址信息
- 权限错误提示所需权限
- 使用 loguru 记录错误日志

#### Scenario: 数据库连接错误
- **WHEN** 数据库连接失败
- **THEN** 返回 `{"error": "数据库连接失败: <详细原因>"}`

#### Scenario: 查询执行错误
- **WHEN** SQL 查询执行失败
- **THEN** 返回 `{"error": "查询执行失败: <详细原因>"}` 并回滚事务
