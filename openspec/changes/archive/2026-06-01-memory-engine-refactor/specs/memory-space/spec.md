## ADDED Requirements

### Requirement: 存储类型字段
`MemorySpace` 模型 SHALL 包含 `storage_type` 字段标识使用的记忆引擎。

#### Scenario: 默认存储类型
- **WHEN** 创建新记忆空间未指定 `storage_type`
- **THEN** 默认值为 `"local"`

#### Scenario: 指定存储类型
- **WHEN** 创建记忆空间指定 `storage_type="mem0"`
- **THEN** 保存该值

### Requirement: 存储配置字段
`MemorySpace` 模型 SHALL 包含 `storage_config` JSON 字段存储引擎配置。

#### Scenario: 默认配置
- **WHEN** 创建新记忆空间未指定 `storage_config`
- **THEN** 默认值为空字典 `{}`

#### Scenario: 保存配置
- **WHEN** 创建记忆空间指定 `storage_config={"api_key": "xxx", "base_url": "..."}`
- **THEN** 保存该配置

### Requirement: 敏感配置加密
`MemorySpace` 模型 SHALL 对 `storage_config` 中的敏感字段进行加密存储。

#### Scenario: 保存时加密
- **WHEN** 保存 `storage_config` 包含 `api_key` 字段
- **THEN** `api_key` 值被加密后存储到数据库

#### Scenario: 读取时解密
- **WHEN** 读取 `storage_config`
- **THEN** `api_key` 值被解密后返回

### Requirement: API 返回脱敏配置
记忆空间 API SHALL 对敏感配置字段进行脱敏处理。

#### Scenario: 列表 API 脱敏
- **WHEN** 调用 `GET /api/opspilot/memory_space/`
- **THEN** 返回的 `storage_config` 中 `api_key` 显示为 `"***"`

#### Scenario: 详情 API 脱敏
- **WHEN** 调用 `GET /api/opspilot/memory_space/{id}/`
- **THEN** 返回的 `storage_config` 中 `api_key` 显示为前缀 + `"***"`（如 `"m0-***"`）

### Requirement: 创建时指定引擎
记忆空间创建 API SHALL 支持指定存储类型和配置。

#### Scenario: 创建本地存储记忆空间
- **WHEN** 调用 `POST /api/opspilot/memory_space/`，body 包含 `{"name": "test", "storage_type": "local"}`
- **THEN** 创建成功，`storage_type` 为 `"local"`，`storage_config` 为 `{}`

#### Scenario: 创建 Mem0 记忆空间
- **WHEN** 调用 `POST /api/opspilot/memory_space/`，body 包含 `{"name": "test", "storage_type": "mem0", "storage_config": {"api_key": "xxx"}}`
- **THEN** 创建成功，配置被加密存储

### Requirement: 编辑时禁止切换引擎
记忆空间更新 API SHALL 禁止修改 `storage_type`。

#### Scenario: 尝试切换引擎类型
- **WHEN** 调用 `PUT /api/opspilot/memory_space/{id}/`，body 包含不同的 `storage_type`
- **THEN** 返回 400 错误，提示不允许切换存储类型

#### Scenario: 更新配置
- **WHEN** 调用 `PUT /api/opspilot/memory_space/{id}/`，body 包含新的 `storage_config`
- **THEN** 更新成功，新配置被加密存储
