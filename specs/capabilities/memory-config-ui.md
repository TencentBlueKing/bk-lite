# memory-config-ui Specification

## Purpose
TBD - created by archiving change memory-engine-refactor. Update Purpose after archive.

## Requirements
### Requirement: 动态引擎配置表单
前端 SHALL 提供 `EngineConfigForm` 组件，根据后端返回的 schema 动态渲染配置表单。

#### Scenario: 渲染 text 字段
- **WHEN** schema 包含 `{"name": "base_url", "type": "text", "label": "API 地址"}`
- **THEN** 渲染 `<Input />` 组件，label 为 "API 地址"

#### Scenario: 渲染 password 字段
- **WHEN** schema 包含 `{"name": "api_key", "type": "password", "label": "API Key"}`
- **THEN** 渲染 `<Input.Password />` 组件

#### Scenario: 渲染 number 字段
- **WHEN** schema 包含 `{"name": "timeout", "type": "number", "label": "超时时间"}`
- **THEN** 渲染 `<InputNumber />` 组件

#### Scenario: 渲染 select 字段
- **WHEN** schema 包含 `{"name": "version", "type": "select", "options": [{"value": "v1", "label": "V1"}, {"value": "v2", "label": "V2"}]}`
- **THEN** 渲染 `<Select />` 组件，包含指定选项

#### Scenario: 渲染 json 字段
- **WHEN** schema 包含 `{"name": "headers", "type": "json", "label": "自定义请求头"}`
- **THEN** 渲染 `<Input.TextArea />` 组件，提交时校验 JSON 格式

### Requirement: 必填字段校验
动态表单 SHALL 根据 schema 的 `required` 属性进行校验。

#### Scenario: 必填字段为空
- **WHEN** 用户未填写 `required: true` 的字段并提交
- **THEN** 显示校验错误，阻止提交

#### Scenario: 可选字段为空
- **WHEN** 用户未填写 `required: false` 的字段并提交
- **THEN** 允许提交

### Requirement: 默认值填充
动态表单 SHALL 使用 schema 的 `default` 属性填充初始值。

#### Scenario: 新建时填充默认值
- **WHEN** 创建新记忆空间，选择 Mem0 引擎
- **THEN** `base_url` 字段自动填充 `https://api.mem0.ai`

#### Scenario: 编辑时显示已保存值
- **WHEN** 编辑已有记忆空间
- **THEN** 表单显示已保存的配置值，而非默认值

### Requirement: 敏感字段脱敏显示
动态表单 SHALL 对已保存的敏感字段进行脱敏显示。

#### Scenario: 编辑时显示脱敏 API Key
- **WHEN** 编辑已有记忆空间，`api_key` 已保存为 `m0-abc123xyz`
- **THEN** 显示为 `m0-***` 或占位符

#### Scenario: 修改敏感字段
- **WHEN** 用户在脱敏字段中输入新值
- **THEN** 提交时使用新值覆盖

### Requirement: 连接测试按钮
动态表单 SHALL 提供连接测试功能。

#### Scenario: 测试连接成功
- **WHEN** 用户点击"测试连接"按钮，配置有效
- **THEN** 显示成功提示 "连接成功"

#### Scenario: 测试连接失败
- **WHEN** 用户点击"测试连接"按钮，配置无效
- **THEN** 显示错误提示，包含失败原因

### Requirement: 引擎选择器
记忆空间创建/编辑页面 SHALL 提供引擎类型选择器。

#### Scenario: 创建时选择引擎
- **WHEN** 用户创建新记忆空间
- **THEN** 显示引擎类型下拉框，选项从 `/memory_engines/` API 获取

#### Scenario: 切换引擎类型
- **WHEN** 用户切换引擎类型
- **THEN** 动态加载对应引擎的配置表单

#### Scenario: 编辑时禁用引擎切换
- **WHEN** 用户编辑已有记忆空间
- **THEN** 引擎类型下拉框禁用，不允许切换
