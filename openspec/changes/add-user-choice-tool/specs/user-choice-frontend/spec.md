## ADDED Requirements

### Requirement: 前端处理 user_choice_request 事件

前端 SHALL 监听并处理 `user_choice_request` SSE 事件，渲染用户选择卡片。

#### Scenario: 接收并渲染选择卡片

- **WHEN** 前端收到 `user_choice_request` 事件
- **THEN** AGUIMessageHandler 解析事件数据
- **AND** 在当前消息中渲染 UserChoiceCard 组件

#### Scenario: 保留已提交状态

- **WHEN** 用户已提交选择后，SSE 流继续推送更新
- **THEN** 前端 MUST 保留用户已提交的状态，不被后续更新覆盖

### Requirement: 交互模式自动适配

前端 SHALL 根据选项数量和多选配置自动选择最佳交互形式。

#### Scenario: 少量选项使用按钮

- **WHEN** `multiple=false` 且 `options.length <= 5`
- **THEN** 渲染按钮组形式，每个选项一个按钮

#### Scenario: 大量选项使用下拉菜单

- **WHEN** `multiple=false` 且 `options.length > 5`
- **THEN** 渲染下拉菜单形式

#### Scenario: 多选使用复选框

- **WHEN** `multiple=true`
- **THEN** 渲染复选框列表 + 确认按钮

### Requirement: 单选按钮点击即提交

前端 SHALL 在单选模式下，用户点击按钮后立即提交选择。

#### Scenario: 点击按钮直接提交

- **WHEN** 用户在单选按钮模式下点击某个选项
- **THEN** 前端立即调用 `/submit_choice/` API 提交选择
- **AND** 无需额外确认步骤

### Requirement: 多选需要确认提交

前端 SHALL 在多选模式下，用户需点击确认按钮才提交选择。

#### Scenario: 多选需要确认

- **WHEN** 用户在多选模式下勾选了多个选项
- **THEN** 用户 MUST 点击"确认"按钮才提交选择
- **AND** 确认按钮显示已选数量（如 "确认 (2/3)"）

#### Scenario: 最少选择数量校验

- **WHEN** 用户选择数量少于 `min_select`
- **THEN** 确认按钮 MUST 禁用
- **AND** 显示提示信息

### Requirement: 倒计时显示

前端 SHALL 显示剩余选择时间的倒计时。

#### Scenario: 显示剩余时间

- **WHEN** 选择卡片渲染时
- **THEN** 显示剩余秒数，每秒更新

#### Scenario: 倒计时归零

- **WHEN** 剩余时间归零
- **THEN** 选择卡片切换为"已超时"状态
- **AND** 显示使用的默认选项

### Requirement: 提交选择 API 调用

前端 SHALL 调用 `/api/proxy/opspilot/bot_mgmt/submit_choice/` 提交用户选择。

#### Scenario: 成功提交

- **WHEN** 用户完成选择并提交
- **THEN** 前端 POST 请求包含 `execution_id`, `node_id`, `choice_id`, `selected`
- **AND** 成功后更新卡片状态为"已提交"

#### Scenario: 提交失败

- **WHEN** API 调用失败
- **THEN** 显示错误提示
- **AND** 允许用户重试

### Requirement: 推荐选项高亮

前端 SHALL 对标记为推荐的选项进行视觉高亮。

#### Scenario: 显示推荐标签

- **WHEN** 选项的 `recommended=true`
- **THEN** 该选项显示"推荐"标签
- **AND** 使用高亮样式区分

### Requirement: 类型定义

前端 SHALL 定义完整的 TypeScript 类型。

#### Scenario: UserChoiceRequest 类型

- **WHEN** 定义 UserChoiceRequest 接口
- **THEN** MUST 包含以下字段：
  - `execution_id: string`
  - `node_id: string`
  - `choice_id: string`
  - `title: string`
  - `description?: string`
  - `options: UserChoiceOption[]`
  - `multiple: boolean`
  - `min_select: number`
  - `max_select: number`
  - `timeout_seconds: number`
  - `default_keys: string[]`
  - `display_hint: 'auto' | 'buttons' | 'dropdown' | 'checkbox'`
  - `received_at: number` (前端添加)
  - `status: 'pending' | 'submitted' | 'timeout'` (前端状态)
  - `selected?: string[]` (用户选择结果)

#### Scenario: UserChoiceOption 类型

- **WHEN** 定义 UserChoiceOption 接口
- **THEN** MUST 包含以下字段：
  - `key: string`
  - `label: string`
  - `description?: string`
  - `icon?: string`
  - `disabled?: boolean`
  - `recommended?: boolean`
