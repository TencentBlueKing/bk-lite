## ADDED Requirements

### Requirement: Redis 工具支持多个实例配置

单个智能体中的 Redis 工具 SHALL 允许用户配置多个 Redis 实例，而不是仅支持一套连接参数。

#### Scenario: 新增 Redis 实例

- **WHEN** 用户在 Redis 工具编辑器中点击“新增”
- **THEN** 系统 SHALL 新建一个 Redis 实例配置项
- **AND** 新实例 SHALL 获得默认名称 `Redis - n`
- **AND** 用户 SHALL 可以继续编辑该实例的连接字段

#### Scenario: 保存多个 Redis 实例

- **WHEN** 用户为同一个 Redis 工具配置多个 Redis 实例并保存
- **THEN** 系统 SHALL 持久化这些实例及默认实例信息
- **AND** 后端 SHALL 不再只保留最后一套 Redis 连接参数

### Requirement: Redis 实例具有独立测试连接状态

Redis 工具编辑器 SHALL 为每个实例提供独立的测试连接能力与状态反馈。

#### Scenario: 初始或字段变更后的状态

- **WHEN** 用户新建一个 Redis 实例或修改该实例任一连接字段
- **THEN** 该实例状态 SHALL 显示为未测试

#### Scenario: 测试连接成功

- **WHEN** 用户对某个 Redis 实例执行测试连接且后端验证成功
- **THEN** 该实例状态 SHALL 显示为测试成功

#### Scenario: 测试连接失败

- **WHEN** 用户对某个 Redis 实例执行测试连接且后端验证失败
- **THEN** 该实例状态 SHALL 显示为测试失败
- **AND** 系统 SHALL 返回可用于提示用户的问题信息

### Requirement: Redis 工具支持默认实例与显式实例切换

Redis 工具运行时 SHALL 在多个已配置实例之间稳定选择连接目标。

#### Scenario: 未显式指定实例时执行

- **WHEN** Redis 子工具调用未提供实例标识
- **THEN** 系统 SHALL 使用 Redis 工具的默认实例建立连接

#### Scenario: 显式指定实例时执行

- **WHEN** Redis 子工具调用提供 `instance_id` 或 `instance_name`
- **THEN** 系统 SHALL 解析到对应 Redis 实例并使用该实例建立连接

#### Scenario: 指定实例不存在

- **WHEN** Redis 子工具调用指定的实例标识无法匹配到已配置实例
- **THEN** 系统 SHALL 返回明确错误
- **AND** 系统 SHALL 不得静默回退到其他 Redis 实例

### Requirement: 旧单实例 Redis 配置可被平滑升级

Redis 工具配置协议升级后 SHALL 允许已存在的单实例配置被读取并转换到多实例协议。

#### Scenario: 打开旧配置的 Redis 工具

- **WHEN** 用户编辑一个仍使用旧单实例字段保存的 Redis 工具
- **THEN** 系统 SHALL 能读取该配置
- **AND** 编辑器 SHALL 将其表现为仅包含一个实例的多实例列表

#### Scenario: 重新保存旧配置

- **WHEN** 用户重新保存一个旧单实例 Redis 配置
- **THEN** 系统 SHALL 按新的多实例协议持久化该工具配置
