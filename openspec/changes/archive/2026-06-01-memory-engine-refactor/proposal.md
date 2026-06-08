## Why

当前记忆功能仅支持本地 PostgreSQL 存储，无法对接 Mem0、Zep 等第三方记忆系统。企业用户需要灵活选择记忆存储后端，利用第三方系统的高级能力（如语义搜索、知识图谱、自动事实提取）。本次改造引入引擎注册机制，支持多种记忆系统的即插即用。

## What Changes

- **新增记忆引擎注册中心**：`MemoryEngineRegistry` 管理所有已注册的记忆引擎
- **新增引擎基类**：`BaseMemoryEngine` 定义统一的 `read/write/delete` 接口
- **内置 4 种引擎**：Local（现有逻辑迁移）、Mem0、Zep、Custom API
- **新增引擎 API**：
  - `GET /memory_engines/` 列出所有引擎
  - `GET /memory_engines/{type}/schema/` 获取引擎参数定义
  - `POST /memory_engines/{type}/test/` 测试引擎连接
- **MemorySpace 模型新增字段**：`storage_type`（引擎类型）、`storage_config`（引擎配置 JSON）
- **前端动态配置表单**：根据引擎 schema 动态渲染配置界面
- **工作流节点改造**：`memory_read/write` 节点通过 Registry 获取引擎实例

## Capabilities

### New Capabilities
- `memory-engine-registry`: 记忆引擎注册中心，管理引擎注册、获取、列表、schema 查询
- `memory-engine-local`: 本地存储引擎，迁移现有 PostgreSQL 存储逻辑
- `memory-engine-mem0`: Mem0 云端记忆引擎，支持语义搜索和自动事实提取
- `memory-engine-zep`: Zep 记忆引擎，支持知识图谱和会话记忆
- `memory-engine-custom`: 自定义 API 引擎，支持对接任意 HTTP 接口
- `memory-engine-api`: 引擎管理 REST API，提供引擎列表、schema、测试连接接口
- `memory-config-ui`: 前端动态配置组件，根据 schema 渲染引擎配置表单

### Modified Capabilities
- `memory-space`: 新增 `storage_type` 和 `storage_config` 字段，支持选择和配置记忆引擎
- `memory-workflow-nodes`: 改造 `memory_read/write` 节点，通过 Registry 获取引擎实例执行操作

## Impact

### 后端
- `server/apps/opspilot/models/memory_mgmt.py` - 新增字段
- `server/apps/opspilot/memory/` - 新增目录，包含引擎基类、注册中心、各引擎实现
- `server/apps/opspilot/viewsets/memory_engine_view.py` - 新增引擎 API
- `server/apps/opspilot/urls.py` - 新增路由
- `server/apps/opspilot/tasks.py` - 改造 `process_memory_write` 使用引擎
- `server/apps/opspilot/utils/chat_flow_utils/nodes/memory/` - 改造节点

### 前端
- `web/src/app/opspilot/api/memoryEngine.ts` - 新增引擎 API hooks
- `web/src/app/opspilot/api/memory.ts` - 更新类型定义
- `web/src/app/opspilot/components/memory/EngineConfigForm.tsx` - 新增动态配置组件
- `web/src/app/opspilot/(pages)/memory/page.tsx` - 新增时选择引擎类型
- `web/src/app/opspilot/(pages)/memory/detail/config/page.tsx` - 动态渲染引擎配置

### 数据库
- 新增迁移：`MemorySpace` 表添加 `storage_type`、`storage_config` 字段

### 依赖
- 可选：`mem0` Python SDK（Mem0 引擎）
- 可选：`zep-python` SDK（Zep 引擎）
- `httpx`（Custom API 引擎 HTTP 请求）
