# memory-engine-mem0 Specification

## Purpose
TBD - created by archiving change memory-engine-refactor. Update Purpose after archive.

## Requirements
### Requirement: Mem0 引擎读取记忆
Mem0 引擎 SHALL 通过 Mem0 API 搜索记忆。

#### Scenario: 语义搜索记忆
- **WHEN** 调用 `read(entity, query="用户的饮食偏好", top_k=5)`
- **THEN** 调用 Mem0 `/v3/memories/search/` API，返回语义相关的记忆

#### Scenario: 无 query 时获取最近记忆
- **WHEN** 调用 `read(entity, query=None, top_k=5)`
- **THEN** 使用默认 query "recent memories" 搜索

#### Scenario: API 调用失败
- **WHEN** Mem0 API 返回错误或超时
- **THEN** 记录错误日志，返回空结果 `MemoryReadResult(context="", raw_memories=[], source="mem0")`

### Requirement: Mem0 引擎写入记忆
Mem0 引擎 SHALL 通过 Mem0 API 添加记忆。

#### Scenario: 写入记忆
- **WHEN** 调用 `write(entity, content, title)`
- **THEN** 调用 Mem0 `/v3/memories/add/` API，传入 messages 格式的内容

#### Scenario: 异步处理
- **WHEN** Mem0 API 返回 `event_id`
- **THEN** 返回 `MemoryWriteResult(success=True, event_id=<event_id>)`

### Requirement: Mem0 引擎删除记忆
Mem0 引擎 SHALL 通过 Mem0 API 删除记忆。

#### Scenario: 删除指定记忆
- **WHEN** 调用 `delete(entity, memory_id="mem-123")`
- **THEN** 调用 Mem0 `DELETE /v1/memories/{memory_id}/` API

### Requirement: Mem0 引擎配置 Schema
Mem0 引擎 SHALL 定义所需的配置参数。

#### Scenario: 获取配置 Schema
- **WHEN** 调用 `Mem0MemoryEngine.get_config_schema()`
- **THEN** 返回包含以下字段的列表：
  - `api_key`: password 类型，必填，加密存储
  - `base_url`: text 类型，可选，默认 `https://api.mem0.ai`
  - `org_id`: text 类型，可选
  - `project_id`: text 类型，可选

### Requirement: Mem0 引擎实体映射
Mem0 引擎 SHALL 将 `MemoryEntity` 映射为 Mem0 的 filter 格式。

#### Scenario: 个人记忆映射
- **WHEN** entity 包含 `user_id="alice@example.com"`
- **THEN** 映射为 `{"user_id": "alice@example.com"}`

#### Scenario: 组织记忆映射
- **WHEN** entity 包含 `organization_id=1`
- **THEN** 映射为 `{"agent_id": "org-1"}`
