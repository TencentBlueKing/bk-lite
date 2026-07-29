# memory-engine-zep Specification

## Purpose
TBD - created by archiving change memory-engine-refactor. Update Purpose after archive.

## Requirements
### Requirement: Zep 引擎读取记忆
Zep 引擎 SHALL 通过 Zep API 获取会话记忆。

#### Scenario: 获取会话记忆
- **WHEN** 调用 `read(entity, query, top_k)`
- **THEN** 调用 Zep `GET /sessions/{sessionId}/memory` API，返回 context 字符串

#### Scenario: 返回结构化结果
- **WHEN** Zep API 返回 `context` 和 `relevant_facts`
- **THEN** 将 `context` 作为 `MemoryReadResult.context`，`relevant_facts` 放入 `raw_memories`

### Requirement: Zep 引擎写入记忆
Zep 引擎 SHALL 通过 Zep API 添加会话记忆。

#### Scenario: 写入记忆
- **WHEN** 调用 `write(entity, content, title)`
- **THEN** 调用 Zep `POST /sessions/{sessionId}/memory` API，传入 messages 格式

#### Scenario: 消息格式转换
- **WHEN** 传入纯文本 content
- **THEN** 转换为 `[{"role": "user", "role_type": "user", "content": content}]` 格式

### Requirement: Zep 引擎删除记忆
Zep 引擎 SHALL 通过 Zep API 删除会话记忆。

#### Scenario: 删除会话记忆
- **WHEN** 调用 `delete(entity)`
- **THEN** 调用 Zep `DELETE /sessions/{sessionId}/memory` API

### Requirement: Zep 引擎配置 Schema
Zep 引擎 SHALL 定义所需的配置参数。

#### Scenario: 获取配置 Schema
- **WHEN** 调用 `ZepMemoryEngine.get_config_schema()`
- **THEN** 返回包含以下字段的列表：
  - `api_key`: password 类型，必填，加密存储
  - `base_url`: text 类型，可选，默认 `https://api.getzep.com`

### Requirement: Zep 引擎会话 ID 映射
Zep 引擎 SHALL 将 `MemoryEntity` 映射为 Zep 的 session_id。

#### Scenario: 个人记忆映射
- **WHEN** entity 包含 `user_id="alice@example.com"`
- **THEN** session_id 为 `"alice@example.com"`

#### Scenario: 组织记忆映射
- **WHEN** entity 包含 `organization_id=1`
- **THEN** session_id 为 `"org-1"`
