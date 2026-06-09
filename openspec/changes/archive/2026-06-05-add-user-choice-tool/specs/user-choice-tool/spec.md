## ADDED Requirements

### Requirement: LLM 可调用用户选择工具

系统 SHALL 提供 `request_user_choice` 工具，LLM 在需要用户从多个选项中选择时可调用此工具。

#### Scenario: LLM 调用选择工具请求单选

- **WHEN** LLM 调用 `request_user_choice` 工具，参数包含 `title="请选择要查询的表"`, `options=[{key:"orders", label:"orders 表"}, {key:"customers", label:"customers 表"}]`, `multiple=false`
- **THEN** 系统发射 `user_choice_request` SSE 事件，包含完整的选择请求数据
- **AND** 工具进入等待状态，轮询 Redis 获取用户选择结果

#### Scenario: LLM 调用选择工具请求多选

- **WHEN** LLM 调用 `request_user_choice` 工具，参数包含 `multiple=true`, `max_select=3`
- **THEN** 系统发射 `user_choice_request` SSE 事件，`multiple` 字段为 `true`
- **AND** 前端渲染复选框形式的选择界面

### Requirement: 用户选择结果返回给 LLM

系统 SHALL 将用户的选择结果以文本形式返回给 LLM，包含选中的选项标签和 key。

#### Scenario: 用户完成选择

- **WHEN** 用户在前端选择了 `orders` 选项并提交
- **THEN** 工具返回文本 `"用户选择了: orders 表 (keys: ['orders'])"`
- **AND** LLM 可根据返回的 key 继续执行后续操作

#### Scenario: 用户选择多个选项

- **WHEN** 用户在多选模式下选择了 `orders` 和 `customers` 两个选项
- **THEN** 工具返回文本 `"用户选择了: orders 表, customers 表 (keys: ['orders', 'customers'])"`

### Requirement: 超时自动使用默认值

系统 SHALL 在用户未在规定时间内选择时，自动使用默认选项继续流程。

#### Scenario: 超时使用指定默认值

- **WHEN** 用户 300 秒内未做出选择
- **AND** 工具调用时指定了 `default_keys=["orders"]`
- **THEN** 工具返回文本 `"用户未在规定时间内选择，已使用默认选项: orders 表 (keys: ['orders'])"`

#### Scenario: 超时使用第一个选项

- **WHEN** 用户 300 秒内未做出选择
- **AND** 工具调用时未指定 `default_keys`
- **THEN** 系统使用选项列表中的第一个选项作为默认值

### Requirement: 无人值守场景自动选择

系统 SHALL 在无人值守场景（定时任务）下不等待用户选择，直接使用默认值。

#### Scenario: 定时任务触发时自动选择

- **WHEN** `trigger_type="unattended"` 时调用选择工具
- **THEN** 工具立即返回默认选项，不发射 SSE 事件
- **AND** 返回文本包含 `"自动选择"` 标识

### Requirement: 选择请求数据结构

系统 SHALL 使用标准化的数据结构传递选择请求。

#### Scenario: SSE 事件包含完整数据

- **WHEN** 系统发射 `user_choice_request` 事件
- **THEN** 事件数据 MUST 包含以下字段：
  - `execution_id`: 执行标识
  - `node_id`: 节点标识
  - `choice_id`: 选择请求唯一标识
  - `title`: 选择标题
  - `options`: 选项列表，每个选项包含 `key`, `label`
  - `multiple`: 是否多选
  - `timeout_seconds`: 超时时间
  - `default_keys`: 默认选项 key 列表

### Requirement: 选择结果缓存

系统 SHALL 使用 Redis 缓存存储用户选择结果。

#### Scenario: 缓存 Key 格式

- **WHEN** 用户提交选择
- **THEN** 系统将结果存储到 Redis，Key 格式为 `choice:{execution_id}:{node_id}:{choice_id}`

#### Scenario: 缓存自动过期

- **WHEN** 选择结果存入 Redis
- **THEN** 缓存 TTL 设置为 600 秒（可通过环境变量 `CHOICE_CACHE_TTL` 配置）
