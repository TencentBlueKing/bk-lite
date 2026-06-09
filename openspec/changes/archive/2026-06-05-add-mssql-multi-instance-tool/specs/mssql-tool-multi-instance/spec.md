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
