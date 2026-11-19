# memory-workflow-nodes Specification

## Purpose
TBD - created by archiving change memory-engine-refactor. Update Purpose after archive.

## Requirements
### Requirement: 记忆读取节点执行
记忆读取节点 SHALL 通过引擎注册表获取引擎实例执行读取操作。

#### Scenario: 读取记忆
- **WHEN** 执行记忆读取节点，配置了 `memory_space_id`
- **THEN** 通过 `MemoryEngineRegistry.get_engine(memory_space_id)` 获取引擎，调用 `engine.read(entity, query, top_k)`

#### Scenario: 返回上下文
- **WHEN** 引擎返回 `MemoryReadResult`
- **THEN** 将 `result.context` 作为节点输出的 `memory_context`

#### Scenario: 引擎不可用
- **WHEN** 引擎初始化失败（如 SDK 未安装）
- **THEN** 记录错误日志，返回空 `memory_context`

### Requirement: 记忆写入节点执行
记忆写入节点 SHALL 通过 Celery 异步任务调用引擎写入。

#### Scenario: 触发异步写入
- **WHEN** 执行记忆写入节点
- **THEN** 调用 `process_memory_write.delay(memory_space_id, entity, content, title)`，节点立即返回不阻塞

#### Scenario: 异步任务执行
- **WHEN** Celery 任务执行
- **THEN** 通过 `MemoryEngineRegistry.get_engine(memory_space_id)` 获取引擎，调用 `engine.write(entity, content, title)`

#### Scenario: 写入失败不影响主流程
- **WHEN** 引擎写入失败
- **THEN** 记录错误日志，主对话流程不受影响

### Requirement: 实体构建
工作流节点 SHALL 根据记忆空间 scope 构建 `MemoryEntity`。

#### Scenario: 个人记忆实体
- **WHEN** 记忆空间 `scope="personal"`
- **THEN** 构建 `MemoryEntity(user_id=current_user.username)`

#### Scenario: 组织记忆实体
- **WHEN** 记忆空间 `scope="team"`
- **THEN** 构建 `MemoryEntity(organization_id=current_organization_id)`


### 编排中心的执行身份

编排中心的记忆节点在本次执行组织内校验空间。个人记忆使用执行账号的用户名和域，团队记忆使用执行组织 ID。自动触发且没有已验证个人身份时，只能使用组织记忆。定时流程在发布时固定执行账号和组织，OpenAPI 与受信任的 NATS 用户调用沿用入口身份。
