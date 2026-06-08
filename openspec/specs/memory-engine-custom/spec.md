# memory-engine-custom Specification

## Purpose
TBD - created by archiving change memory-engine-refactor. Update Purpose after archive.

## Requirements
### Requirement: Custom API 引擎读取记忆
Custom API 引擎 SHALL 通过用户配置的 HTTP 端点读取记忆。

#### Scenario: 调用自定义读取端点
- **WHEN** 调用 `read(entity, query, top_k)`
- **THEN** 发送 POST 请求到配置的 `read_endpoint`，body 包含 `{"entity": {...}, "query": "...", "top_k": 5}`

#### Scenario: 解析响应
- **WHEN** 自定义端点返回 `{"context": "...", "memories": [...]}`
- **THEN** 映射为 `MemoryReadResult(context=response["context"], raw_memories=response["memories"])`

#### Scenario: 端点返回错误
- **WHEN** 自定义端点返回非 2xx 状态码
- **THEN** 记录错误日志，返回空结果

### Requirement: Custom API 引擎写入记忆
Custom API 引擎 SHALL 通过用户配置的 HTTP 端点写入记忆。

#### Scenario: 调用自定义写入端点
- **WHEN** 调用 `write(entity, content, title, metadata)`
- **THEN** 发送 POST 请求到配置的 `write_endpoint`，body 包含 `{"entity": {...}, "content": "...", "title": "...", "metadata": {...}}`

#### Scenario: 解析写入响应
- **WHEN** 自定义端点返回 `{"success": true, "memory_id": "..."}`
- **THEN** 返回 `MemoryWriteResult(success=True, memory_id=response["memory_id"])`

### Requirement: Custom API 引擎删除记忆
Custom API 引擎 SHALL 通过用户配置的 HTTP 端点删除记忆。

#### Scenario: 调用自定义删除端点
- **WHEN** 调用 `delete(entity, memory_id)`
- **THEN** 发送 DELETE 请求到配置的 `delete_endpoint`，body 包含 `{"entity": {...}, "memory_id": "..."}`

### Requirement: Custom API 引擎配置 Schema
Custom API 引擎 SHALL 定义所需的配置参数。

#### Scenario: 获取配置 Schema
- **WHEN** 调用 `CustomMemoryEngine.get_config_schema()`
- **THEN** 返回包含以下字段的列表：
  - `base_url`: text 类型，必填，API 基础地址
  - `read_endpoint`: text 类型，必填，读取端点路径（如 `/memory/read`）
  - `write_endpoint`: text 类型，必填，写入端点路径
  - `delete_endpoint`: text 类型，必填，删除端点路径
  - `api_key`: password 类型，可选，加密存储
  - `headers`: json 类型，可选，自定义请求头

### Requirement: Custom API 引擎请求认证
Custom API 引擎 SHALL 支持多种认证方式。

#### Scenario: Bearer Token 认证
- **WHEN** 配置了 `api_key`
- **THEN** 请求头包含 `Authorization: Bearer {api_key}`

#### Scenario: 自定义请求头
- **WHEN** 配置了 `headers` JSON
- **THEN** 将 headers 合并到请求头中
