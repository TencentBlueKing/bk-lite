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
