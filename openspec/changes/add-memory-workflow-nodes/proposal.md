## Why

OpsPilot 工作流目前缺乏记忆能力，无法在多次对话间持久化和复用关键信息。产品经理设计了记忆功能，需要在工作流中新增读取记忆和写入记忆两种节点，使工作流能够：
1. 读取历史记忆作为上下文，提升 Agent 分析质量
2. 将对话中的关键信息提炼并持久化，便于后续追问和经验复用

## What Changes

- **新增 MemorySpace 模型**：记忆空间，作为记忆的容器，支持 personal（个人）和 organization（组织）两种作用域
- **新增 Memory 模型**：记忆条目，存储实际的 Markdown 格式记忆内容
- **新增 MemoryRead 工作流节点**：读取指定记忆空间的记忆内容，输出 `output`（透传）和 `memory`（记忆内容）
- **新增 MemoryWrite 工作流节点**：将输入内容按记忆准则提炼后写入记忆空间，输出 `output`（透传输入）
- **新增记忆管理界面**：记忆空间的 CRUD 管理，包括列表页和详情页
- **新增记忆服务**：LLM 驱动的记忆提炼和合并逻辑
- **新增 Celery 异步任务**：记忆写入为异步操作，不阻塞工作流执行

### 权限规则
- **个人记忆 (personal scope)**：只有记忆空间创建者可以读取和写入，其他用户执行工作流时读取返回空、写入跳过
- **组织记忆 (organization scope)**：同 Team 所有成员可以读取和写入

## Capabilities

### New Capabilities
- `memory-space-management`: 记忆空间的创建、配置、删除等管理功能，包括后端 API 和前端管理界面
- `memory-workflow-nodes`: 工作流中的读取记忆和写入记忆节点，包括节点执行器、前端节点组件和配置面板
- `memory-service`: 记忆提炼和合并服务，使用 LLM 按记忆准则处理内容

### Modified Capabilities
<!-- 无需修改现有 spec -->

## Impact

### 后端 (server/apps/opspilot/)
- `models/`: 新增 `memory_mgmt.py`
- `serializers/`: 新增 `memory_serializer.py`
- `viewsets/`: 新增 `memory_viewset.py`
- `services/`: 新增 `memory_service.py`
- `tasks/`: 新增 `memory_tasks.py`
- `utils/chat_flow_utils/nodes/`: 新增 `memory/` 目录
- `utils/chat_flow_utils/engine/node_registry.py`: 注册新节点

### 前端 (web/src/app/opspilot/)
- `(pages)/memory/`: 新增记忆管理页面
- `api/`: 新增 `memory.ts`
- `components/chatflow/`: 新增记忆节点组件和配置面板
- `components/chatflow/types.ts`: 新增节点类型定义
- `components/chatflow/constants.ts`: 新增默认配置

### 数据库
- 新增 `opspilot_memory_space` 表
- 新增 `opspilot_memory` 表

### 依赖
- Celery：异步记忆写入任务
- LLM Provider：记忆提炼和合并
