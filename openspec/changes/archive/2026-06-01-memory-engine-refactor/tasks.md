## 1. 数据模型与迁移

- [x] 1.1 在 `MemorySpace` 模型添加 `storage_type` 字段（CharField，默认 `"local"`）
- [x] 1.2 在 `MemorySpace` 模型添加 `storage_config` 字段（JSONField，默认 `{}`）
- [x] 1.3 实现 `MemorySpace` 的 `EncryptMixin` 集成，加密 `storage_config` 中的敏感字段
- [x] 1.4 生成并执行数据库迁移

## 2. 引擎基础架构

- [x] 2.1 创建 `server/apps/opspilot/memory/` 目录结构
- [x] 2.2 实现 `BaseMemoryEngine` 抽象基类（`read/write/delete/get_engine_info/get_config_schema`）
- [x] 2.3 实现 `MemoryEntity` 数据类（`user_id`, `organization_id`）
- [x] 2.4 实现 `MemoryReadResult` 和 `MemoryWriteResult` 数据类
- [x] 2.5 实现 `MemoryEngineRegistry` 类（`register/get_engine/list_engines/get_schema`）

## 3. 引擎实现

- [x] 3.1 实现 `LocalMemoryEngine`（读取/写入/删除，复用现有 Django ORM 逻辑）
- [x] 3.2 实现 `Mem0MemoryEngine`（API 调用，实体映射，配置 schema）
- [x] 3.3 实现 `ZepMemoryEngine`（API 调用，会话 ID 映射，配置 schema）
- [x] 3.4 实现 `CustomMemoryEngine`（HTTP 请求，认证，配置 schema）

## 4. 引擎注册与初始化

- [x] 4.1 在 `apps.py` 的 `ready()` 方法中注册所有引擎
- [x] 4.2 实现引擎 SDK 可用性检测（`mem0`/`zep-python` 是否安装）
- [x] 4.3 添加可选依赖到 `pyproject.toml`（`mem0`, `zep-python`, `httpx`）

## 5. 引擎 API 端点

- [x] 5.1 创建 `MemoryEngineViewSet`（`list_engines`, `get_schema`, `test_connection`）
- [x] 5.2 注册 URL 路由（`/api/opspilot/memory_engines/`）
- [x] 5.3 实现连接测试逻辑（各引擎的 `test_connection` 方法）

## 6. 记忆空间 API 修改

- [x] 6.1 修改 `MemorySpaceSerializer` 添加 `storage_type` 和 `storage_config` 字段
- [x] 6.2 实现 `storage_config` 脱敏逻辑（列表/详情 API 返回时）
- [x] 6.3 实现更新时禁止切换 `storage_type` 的校验

## 7. 工作流节点改造

- [x] 7.1 修改 `memory_read.py` 使用 `MemoryEngineRegistry.get_engine()` 获取引擎
- [x] 7.2 修改 `memory_write.py` 使用引擎注册表
- [x] 7.3 修改 `process_memory_write` Celery 任务使用引擎注册表
- [x] 7.4 实现 `MemoryEntity` 构建逻辑（根据 scope 构建 user_id 或 organization_id）

## 8. 前端类型与 API

- [x] 8.1 更新 `MemorySpace` TypeScript 类型（添加 `storage_type`, `storage_config`）
- [x] 8.2 添加引擎 API hooks（`useMemoryEngines`, `useEngineSchema`, `useTestConnection`）
- [x] 8.3 添加引擎相关国际化文案

## 9. 前端动态配置表单

- [x] 9.1 实现 `EngineConfigForm` 组件（根据 schema 动态渲染）
- [x] 9.2 实现字段类型映射（text/password/number/select/json）
- [x] 9.3 实现必填校验和默认值填充
- [x] 9.4 实现敏感字段脱敏显示
- [x] 9.5 实现连接测试按钮

## 10. 前端页面集成

- [x] 10.1 修改记忆空间创建弹窗，添加引擎类型选择器
- [x] 10.2 修改记忆空间配置页面，集成 `EngineConfigForm`
- [x] 10.3 实现编辑时禁用引擎类型切换

## 11. 验证与清理

- [x] 11.1 验证本地引擎向后兼容（现有记忆空间正常工作）
- [x] 11.2 验证 Mem0 引擎端到端流程
- [x] 11.3 验证 Zep 引擎端到端流程
- [x] 11.4 验证 Custom API 引擎端到端流程
- [x] 11.5 验证前端动态表单渲染和提交
