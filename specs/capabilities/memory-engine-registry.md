# memory-engine-registry Specification

## Purpose
TBD - created by archiving change memory-engine-refactor. Update Purpose after archive.

## Requirements
### Requirement: 引擎注册
系统 SHALL 提供 `MemoryEngineRegistry` 类，支持注册记忆引擎类。

#### Scenario: 注册引擎
- **WHEN** 调用 `MemoryEngineRegistry.register("mem0", Mem0MemoryEngine)`
- **THEN** 引擎类被存储在注册表中，可通过类型标识获取

#### Scenario: 重复注册覆盖
- **WHEN** 对同一 `engine_type` 多次调用 `register()`
- **THEN** 后注册的引擎类覆盖先前的

### Requirement: 获取引擎实例
系统 SHALL 提供 `get_engine(memory_space_id)` 方法，根据记忆空间 ID 返回对应的引擎实例。

#### Scenario: 获取已注册引擎
- **WHEN** 调用 `MemoryEngineRegistry.get_engine(memory_space_id)`，且该记忆空间的 `storage_type` 对应的引擎已注册
- **THEN** 返回该引擎类的实例，实例已使用记忆空间配置初始化

#### Scenario: 获取未注册引擎
- **WHEN** 调用 `get_engine(memory_space_id)`，且 `storage_type` 对应的引擎未注册
- **THEN** 抛出 `ValueError` 异常，消息包含未知的引擎类型

#### Scenario: 记忆空间不存在
- **WHEN** 调用 `get_engine(memory_space_id)`，且该 ID 不存在
- **THEN** 抛出 `MemorySpace.DoesNotExist` 异常

### Requirement: 列出所有引擎
系统 SHALL 提供 `list_engines()` 方法，返回所有已注册引擎的元信息列表。

#### Scenario: 列出引擎
- **WHEN** 调用 `MemoryEngineRegistry.list_engines()`
- **THEN** 返回列表，每项包含 `type`、`name`、`description` 字段

#### Scenario: 无引擎注册
- **WHEN** 调用 `list_engines()` 且无引擎注册
- **THEN** 返回空列表

### Requirement: 获取引擎 Schema
系统 SHALL 提供 `get_schema(engine_type)` 方法，返回指定引擎的参数定义。

#### Scenario: 获取已注册引擎 Schema
- **WHEN** 调用 `MemoryEngineRegistry.get_schema("mem0")`
- **THEN** 返回包含 `type`、`name`、`description`、`fields` 的字典

#### Scenario: 获取未注册引擎 Schema
- **WHEN** 调用 `get_schema("unknown")`
- **THEN** 抛出 `ValueError` 异常
