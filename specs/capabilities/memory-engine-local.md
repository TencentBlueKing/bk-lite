# memory-engine-local Specification

## Purpose
TBD - created by archiving change memory-engine-refactor. Update Purpose after archive.

## Requirements
### Requirement: 引擎基类接口
所有记忆引擎 SHALL 继承 `BaseMemoryEngine` 并实现以下抽象方法：
- `read(entity, query, top_k) -> MemoryReadResult`
- `write(entity, content, title, metadata) -> MemoryWriteResult`
- `delete(entity, memory_id) -> bool`
- `get_engine_info() -> dict` (类方法)
- `get_config_schema() -> list` (类方法)

#### Scenario: 引擎实现完整接口
- **WHEN** 创建继承 `BaseMemoryEngine` 的引擎类
- **THEN** 必须实现所有抽象方法，否则无法实例化

### Requirement: Local 引擎读取记忆
Local 引擎 SHALL 从 PostgreSQL 数据库读取记忆条目。

#### Scenario: 读取个人记忆
- **WHEN** 调用 `read(entity, query, top_k=5)`，entity 包含 `user_id="alice@example.com"`，记忆空间 scope 为 `personal`
- **THEN** 返回该用户在该记忆空间的最近 5 条记忆，按 `updated_at` 降序

#### Scenario: 读取组织记忆
- **WHEN** 调用 `read(entity, query, top_k=5)`，entity 包含 `organization_id=1`，记忆空间 scope 为 `team`
- **THEN** 返回该组织在该记忆空间的最近 5 条记忆

#### Scenario: 无匹配记忆
- **WHEN** 调用 `read()` 但无匹配记忆
- **THEN** 返回 `MemoryReadResult(context="", raw_memories=[], source="local")`

### Requirement: Local 引擎写入记忆
Local 引擎 SHALL 将记忆写入 PostgreSQL 数据库，支持智能合并。

#### Scenario: 写入新记忆（无现有记忆）
- **WHEN** 调用 `write(entity, content, title)`，该实体在该记忆空间无现有记忆
- **THEN** 创建新的 `Memory` 记录，返回 `MemoryWriteResult(success=True, memory_id=<new_id>)`

#### Scenario: 合并现有记忆
- **WHEN** 调用 `write(entity, content, title)`，该实体已有记忆
- **THEN** 使用 LLM 智能合并新旧内容，更新现有记忆记录

#### Scenario: 无 LLM 配置时简单追加
- **WHEN** 调用 `write()` 但记忆空间未配置 `default_model`
- **THEN** 将新内容追加到现有记忆末尾（用 `---` 分隔）

### Requirement: Local 引擎删除记忆
Local 引擎 SHALL 支持删除记忆条目。

#### Scenario: 删除指定记忆
- **WHEN** 调用 `delete(entity, memory_id="123")`
- **THEN** 删除 ID 为 123 的记忆记录，返回 `True`

#### Scenario: 删除实体所有记忆
- **WHEN** 调用 `delete(entity, memory_id=None)`
- **THEN** 删除该实体在该记忆空间的所有记忆，返回 `True`

#### Scenario: 删除不存在的记忆
- **WHEN** 调用 `delete()` 但目标记忆不存在
- **THEN** 返回 `False`

### Requirement: Local 引擎元信息
Local 引擎 SHALL 提供引擎元信息和空的配置 schema。

#### Scenario: 获取引擎信息
- **WHEN** 调用 `LocalMemoryEngine.get_engine_info()`
- **THEN** 返回 `{"type": "local", "name": "本地存储", "description": "使用 PostgreSQL 数据库存储记忆"}`

#### Scenario: 获取配置 Schema
- **WHEN** 调用 `LocalMemoryEngine.get_config_schema()`
- **THEN** 返回空列表 `[]`（本地存储无需额外配置）
