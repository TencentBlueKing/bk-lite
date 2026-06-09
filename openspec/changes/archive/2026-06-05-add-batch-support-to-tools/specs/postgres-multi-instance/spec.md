## ADDED Requirements

### Requirement: postgres 工具支持多实例配置

postgres 工具模块 SHALL 支持通过 `credentials` 列表配置多个 PostgreSQL 实例，对齐 mysql / mssql / oracle / redis 已有的多实例协议。

#### Scenario: 配置多个 postgres 实例

- **WHEN** 用户通过 `credentials` 字段配置多个 PostgreSQL 实例列表
- **THEN** 系统 SHALL 解析每个实例的 `host`、`port`、`database`、`user`、`password` 字段
- **AND** 每个实例 SHALL 可选提供 `name` 字段作为显示名称

#### Scenario: 未配置 credentials 时使用平铺字段

- **WHEN** 用户未提供 `credentials` 列表，而是通过平铺字段（host / port / database / user / password）提供连接信息
- **THEN** 系统 SHALL 将其视为旧式单实例配置并正常建立连接
- **AND** 现有 postgres 工具的行为 SHALL 完全不变

#### Scenario: credentials 与平铺字段同时存在时报错

- **WHEN** 用户同时提供 `credentials` 列表和平铺字段
- **THEN** 系统 SHALL 抛出 `CredentialConflictError`
- **AND** 系统 SHALL 不得执行任何数据库操作

### Requirement: postgres 工具运行时支持实例选择

postgres 工具 SHALL 在多实例配置下支持通过参数指定目标实例或对所有实例批量执行。

#### Scenario: 未显式指定实例时执行（单实例配置）

- **WHEN** 仅配置一个 PostgreSQL 实例且工具调用未提供实例标识
- **THEN** 系统 SHALL 使用该唯一实例建立连接
- **AND** 返回结果 SHALL 为单实例格式（不包装聚合结构）

#### Scenario: 未显式指定实例时执行（多实例配置）

- **WHEN** 配置多个 PostgreSQL 实例且工具调用未提供实例标识
- **THEN** 系统 SHALL 对所有已配置实例批量执行该工具
- **AND** 返回结果 SHALL 为聚合格式，包含 `mode`、`total`、`succeeded`、`failed`、`results` 字段

#### Scenario: 显式指定实例时执行

- **WHEN** 工具调用提供 `instance_id` 或 `instance_name`
- **THEN** 系统 SHALL 解析到对应 PostgreSQL 实例并仅使用该实例建立连接
- **AND** 返回结果 SHALL 为单实例格式

#### Scenario: 指定实例不存在

- **WHEN** 工具调用指定的实例标识无法匹配到已配置实例
- **THEN** 系统 SHALL 返回明确错误信息
- **AND** 系统 SHALL 不得静默回退到其他实例

### Requirement: postgres 多实例改造不破坏现有工具函数

postgres 工具模块 SHALL 通过新增 `connection.py` 实现多实例支持，原有 `utils.py` 中的 `prepare_context / get_db_connection / execute_readonly_query` 函数 SHALL 保持不变，现有工具函数继续正常工作。

#### Scenario: 现有 postgres 工具在旧式配置下正常工作

- **WHEN** 使用旧式平铺字段配置的 postgres 工具被调用
- **THEN** 系统 SHALL 通过 `utils.py` 的 `prepare_context` 正常建立连接
- **AND** 工具返回结果 SHALL 与改造前完全一致

#### Scenario: 新 batch 工具使用新连接层

- **WHEN** 调用 `execute_safe_select_batch` 等新增 batch 工具
- **THEN** 系统 SHALL 通过 `connection.py` 的 `build_postgres_normalized_from_runnable` 获取连接配置
- **AND** 单实例和多实例路径 SHALL 均正确工作

### Requirement: postgres 多实例执行中单个实例失败不影响其他实例

postgres 工具在多实例批量执行模式下 SHALL 保证单个实例的失败不阻断其他实例。

#### Scenario: 部分实例连接失败

- **WHEN** 批量执行时某个 postgres 实例连接超时或认证失败
- **THEN** 系统 SHALL 在该实例结果中标记 `ok: false` 并记录错误信息
- **AND** 系统 SHALL 继续对剩余实例执行工具
- **AND** 聚合结果中 `failed` 字段 SHALL 正确反映失败数量
