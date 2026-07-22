# 2026 06 05 Add Memory Workflow Nodes

Status: done

## Migration Context

- Legacy source: `openspec/changes/archive/2026-06-05-add-memory-workflow-nodes/`
- Legacy state: `archived`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

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

## Implementation Decisions

## Context

OpsPilot 是一个基于工作流的智能运维助手平台。当前工作流节点包括：入口/出口、LLM、Agent、HTTP 请求、知识检索、技能调用等。工作流通过 `node_registry.py` 注册节点类型，每个节点继承 `BaseExecutor` 实现 `execute()` 方法。

现有架构：
- **后端节点执行**：`server/apps/opspilot/utils/chat_flow_utils/engine/` 下的执行引擎
- **前端节点编辑**：`web/src/app/opspilot/components/chatflow/` 下的 ReactFlow 编辑器
- **变量传递**：通过 `VariableManager` 和 Jinja2 模板 `{{node_id.output_key}}` 实现节点间数据流

本次需要新增记忆功能，使工作流能够持久化和复用对话中的关键信息。

## Goals / Non-Goals

**Goals:**
- 实现 MemorySpace 和 Memory 数据模型，支持 personal/organization 两种作用域
- 实现 MemoryRead 节点：读取记忆内容，输出 `output`（透传）和 `memory`（记忆内容）
- 实现 MemoryWrite 节点：异步写入记忆，输出 `output`（透传输入）
- 实现记忆管理界面：记忆空间的 CRUD
- 实现 LLM 驱动的记忆提炼和合并服务

**Non-Goals:**
- 记忆的向量化存储和语义搜索（后续迭代）
- 记忆版本历史和回滚（后续迭代）
- 跨 Team 的记忆共享
- 记忆的自动过期和清理

## Decisions

### D1: 数据模型设计

**决策**：采用 MemorySpace（记忆空间）+ Memory（记忆条目）两层模型

```
MemorySpace (记忆空间)
├── id, name, description
├── scope: personal | organization
├── guidelines: 记忆准则 (Markdown)
├── model: 用于提炼的 LLM 模型
├── team_id (FK)
└── created_by_id (FK)

Memory (记忆条目)
├── id
├── memory_space_id (FK)
├── owner_id (FK, nullable) - personal scope 时为用户 ID
├── title, content (Markdown)
├── source_workflow, source_node
└── created_at, updated_at
```

**理由**：
- 两层模型分离了"配置"和"数据"，便于管理
- `guidelines` 字段允许用户定义记忆提炼规则，提高记忆质量
- `owner_id` 字段支持 personal scope 下每个用户独立的记忆

**替代方案**：
- 单表设计（Memory 直接包含配置）：配置重复，难以统一管理
- 三层模型（增加 MemoryEntry 历史）：过于复杂，非当前需求

### D2: 权限模型

**决策**：基于 scope 和 created_by 的简单权限模型

| Scope | 读取权限 | 写入权限 |
|-------|---------|---------|
| personal | 仅 created_by | 仅 created_by |
| organization | 同 Team 所有成员 | 同 Team 所有成员 |

**理由**：
- 简单直观，符合 PM 设计
- personal scope 保护用户隐私
- organization scope 支持团队知识共享

**替代方案**：
- 细粒度 RBAC：过于复杂，当前需求不需要
- 基于 owner 的权限：personal scope 下 owner 是动态的，不适合

### D3: 节点输入输出设计

**决策**：

**MemoryRead 节点**：
- 输入：`input`（来自上游节点）
- 输出：`output`（透传 input）、`memory`（读取到的记忆内容）

**MemoryWrite 节点**：
- 输入：`input`（要写入的内容）
- 输出：`output`（透传 input）

**理由**：
- 透传设计使节点可以无缝插入工作流任意位置
- MemoryRead 额外输出 `memory` 变量，下游节点可通过 `{{memory_read_node.memory}}` 引用
- MemoryWrite 不阻塞流程，异步写入

**替代方案**：
- MemoryRead 不透传，只输出 memory：破坏数据流，需要额外节点合并
- MemoryWrite 同步写入：阻塞工作流，影响用户体验

### D4: 记忆写入策略

**决策**：异步写入 + LLM 提炼 + 合并更新

```
工作流执行 → MemoryWrite 节点 → 触发 Celery 任务 → LLM 提炼 → 合并到 Memory
                    ↓
              立即返回（透传）
```

**理由**：
- 异步写入不阻塞工作流执行
- LLM 提炼确保记忆质量，过滤无效信息
- 合并更新避免记忆碎片化

**替代方案**：
- 同步写入：阻塞工作流，用户体验差
- 直接写入不提炼：记忆质量低，噪音多
- 追加而非合并：记忆碎片化，难以阅读

### D5: 前端节点实现

**决策**：复用现有节点架构

- 节点组件：继承 `BaseNode`，在 `nodes/index.tsx` 注册
- 配置面板：在 `nodeConfigs/` 下创建 `MemoryReadConfig.tsx` 和 `MemoryWriteConfig.tsx`
- 类型定义：在 `types.ts` 添加 `memory_read` 和 `memory_write` 类型
- 默认配置：在 `constants.ts` 添加默认节点配置

**理由**：
- 复用现有架构，保持一致性
- 降低开发成本和维护成本

## Risks / Trade-offs

### R1: LLM 提炼质量不稳定
**风险**：LLM 可能提炼出低质量或不相关的记忆内容
**缓解**：
- 提供 `guidelines` 字段让用户定义提炼规则
- 记忆管理界面支持手动编辑
- 后续可增加人工确认模式

### R2: 异步写入可能丢失
**风险**：Celery 任务失败导致记忆写入丢失
**缓解**：
- Celery 任务配置重试机制
- 记录任务执行日志
- 后续可增加写入状态追踪

### R3: 记忆内容无限增长
**风险**：长期使用后记忆内容过大，影响读取性能和 LLM 上下文
**缓解**：
- 合并策略控制记忆大小
- 后续可增加自动摘要和归档功能

### R4: personal scope 权限判断依赖 created_by
**风险**：如果 created_by 用户被删除，记忆空间可能无法访问
**缓解**：
- `created_by` 使用 `SET_NULL` 而非 `CASCADE`
- 管理员可以接管孤儿记忆空间（后续功能）

## Migration Plan

### 部署步骤
1. 执行数据库迁移创建新表
2. 部署后端代码（模型、API、节点执行器、Celery 任务）
3. 部署前端代码（管理界面、节点组件）
4. 验证功能正常

### 回滚策略
- 数据库：保留新表，不影响现有功能
- 后端：回滚代码，新节点类型在工作流中会报错但不影响其他节点
- 前端：回滚代码，新节点类型不可用

### 兼容性
- 现有工作流不受影响
- 新节点为可选功能，不强制使用

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-05-21
```

## Capability Deltas

### memory-service

## ADDED Requirements

### Requirement: Memory extraction
The system SHALL use LLM to extract valuable information from input content based on memory space guidelines.

#### Scenario: Extract with guidelines
- **WHEN** memory service receives content and guidelines
- **THEN** system calls LLM to extract information following the guidelines

#### Scenario: No valuable content
- **WHEN** LLM determines no content worth memorizing
- **THEN** system returns empty result and skips memory write

#### Scenario: Use configured model
- **WHEN** memory space has model configured
- **THEN** system uses the configured model for extraction

### Requirement: Memory merge
The system SHALL merge new memory content with existing memory content using LLM.

#### Scenario: Merge with existing memory
- **WHEN** memory entry already exists for the user/organization
- **THEN** system calls LLM to merge new content with existing content

#### Scenario: Create new memory
- **WHEN** no memory entry exists for the user/organization
- **THEN** system creates new memory entry with extracted content

#### Scenario: Deduplicate content
- **WHEN** merging memories
- **THEN** system removes duplicate information and consolidates related content

### Requirement: Async memory write task
The system SHALL process memory writes asynchronously using Celery.

#### Scenario: Task triggered
- **WHEN** memory write node triggers write
- **THEN** system enqueues Celery task and returns immediately

#### Scenario: Task execution
- **WHEN** Celery task executes
- **THEN** system extracts memory, merges with existing, and saves to database

#### Scenario: Task retry on failure
- **WHEN** Celery task fails
- **THEN** system retries the task according to retry policy

### Requirement: Memory source tracking
The system SHALL track the source of memory writes for auditing.

#### Scenario: Record source workflow
- **WHEN** memory is written
- **THEN** system records source_workflow and source_node fields

#### Scenario: Update timestamp
- **WHEN** memory is updated
- **THEN** system updates the updated_at timestamp

### memory-space-management

## ADDED Requirements

### Requirement: Create memory space
The system SHALL allow users to create a memory space with name, description, scope (personal/organization), guidelines, and model configuration.

#### Scenario: Create personal memory space
- **WHEN** user submits create form with scope="personal"
- **THEN** system creates a memory space with created_by set to current user and team set to current team

#### Scenario: Create organization memory space
- **WHEN** user submits create form with scope="organization"
- **THEN** system creates a memory space accessible to all team members

### Requirement: List memory spaces
The system SHALL display all memory spaces accessible to the current user within the current team.

#### Scenario: List memory spaces for team member
- **WHEN** user views memory space list
- **THEN** system displays all memory spaces belonging to the current team

#### Scenario: Filter by scope
- **WHEN** user filters by scope="personal"
- **THEN** system displays only personal memory spaces

### Requirement: View memory space details
The system SHALL allow users to view memory space configuration and its memory entries.

#### Scenario: View configuration
- **WHEN** user opens memory space detail page
- **THEN** system displays name, description, scope, guidelines, and model configuration

#### Scenario: View memory entries for personal scope
- **WHEN** user views memory entries of a personal memory space they created
- **THEN** system displays all memory entries owned by the user

#### Scenario: View memory entries for organization scope
- **WHEN** user views memory entries of an organization memory space
- **THEN** system displays all memory entries (owner is null)

### Requirement: Update memory space
The system SHALL allow users to update memory space configuration.

#### Scenario: Update guidelines
- **WHEN** user modifies guidelines and saves
- **THEN** system updates the guidelines field

#### Scenario: Scope cannot be changed
- **WHEN** user attempts to change scope after creation
- **THEN** system rejects the change (scope is immutable)

### Requirement: Delete memory space
The system SHALL allow users to delete a memory space and all its memory entries.

#### Scenario: Delete with confirmation
- **WHEN** user confirms deletion
- **THEN** system deletes the memory space and all associated memory entries

### Requirement: Edit memory entry
The system SHALL allow users to manually edit memory entry content.

#### Scenario: Edit memory content
- **WHEN** user edits memory content in the detail view
- **THEN** system updates the memory entry content

### Requirement: Delete memory entry
The system SHALL allow users to delete individual memory entries.

#### Scenario: Delete single entry
- **WHEN** user deletes a memory entry
- **THEN** system removes the entry from the memory space

### memory-workflow-nodes

## ADDED Requirements

### Requirement: Memory read node type
The system SHALL provide a "memory_read" workflow node type that reads memory content from a configured memory space.

#### Scenario: Node available in editor
- **WHEN** user opens workflow editor
- **THEN** "读取记忆" node type is available in the node palette

### Requirement: Memory read node configuration
The system SHALL allow users to configure the memory read node with a memory space selection.

#### Scenario: Configure memory space
- **WHEN** user opens memory read node configuration panel
- **THEN** system displays a dropdown of available memory spaces with scope labels

### Requirement: Memory read node execution
The system SHALL execute memory read node by reading memory content based on scope and user permissions.

#### Scenario: Read personal memory as creator
- **WHEN** memory read node executes with personal scope memory space AND current user is the creator
- **THEN** system outputs `output` (passthrough from input) and `memory` (user's memory content)

#### Scenario: Read personal memory as non-creator
- **WHEN** memory read node executes with personal scope memory space AND current user is NOT the creator
- **THEN** system outputs `output` (passthrough from input) and `memory` (empty string)

#### Scenario: Read organization memory
- **WHEN** memory read node executes with organization scope memory space
- **THEN** system outputs `output` (passthrough from input) and `memory` (organization memory content)

#### Scenario: No memory space configured
- **WHEN** memory read node executes without memory space configured
- **THEN** system outputs `output` (passthrough from input) and `memory` (empty string)

#### Scenario: Memory not found
- **WHEN** memory read node executes AND no memory entry exists
- **THEN** system outputs `output` (passthrough from input) and `memory` (empty string)

### Requirement: Memory write node type
The system SHALL provide a "memory_write" workflow node type that writes content to a configured memory space.

#### Scenario: Node available in editor
- **WHEN** user opens workflow editor
- **THEN** "写入记忆" node type is available in the node palette

### Requirement: Memory write node configuration
The system SHALL allow users to configure the memory write node with a memory space selection.

#### Scenario: Configure memory space
- **WHEN** user opens memory write node configuration panel
- **THEN** system displays a dropdown of available memory spaces with scope labels

### Requirement: Memory write node execution
The system SHALL execute memory write node by triggering async memory write and passing through input.

#### Scenario: Write to personal memory as creator
- **WHEN** memory write node executes with personal scope memory space AND current user is the creator
- **THEN** system triggers async memory write task AND outputs `output` (passthrough from input)

#### Scenario: Write to personal memory as non-creator
- **WHEN** memory write node executes with personal scope memory space AND current user is NOT the creator
- **THEN** system skips memory write AND outputs `output` (passthrough from input)

#### Scenario: Write to organization memory
- **WHEN** memory write node executes with organization scope memory space
- **THEN** system triggers async memory write task AND outputs `output` (passthrough from input)

#### Scenario: No memory space configured
- **WHEN** memory write node executes without memory space configured
- **THEN** system outputs `output` (passthrough from input) without triggering write

#### Scenario: Empty input
- **WHEN** memory write node executes with empty input
- **THEN** system outputs `output` (empty) without triggering write

### Requirement: Memory node variable reference
The system SHALL allow downstream nodes to reference memory read node outputs using template syntax.

#### Scenario: Reference memory content
- **WHEN** downstream node uses `{{memory_read_node_id.memory}}` in configuration
- **THEN** system resolves to the memory content from the memory read node

## Work Checklist

## 1. Backend Data Models

- [x] 1.1 Create `server/apps/opspilot/models/memory_mgmt.py` with MemorySpace model (id, name, introduction, scope, write_rule, default_model, team, timestamps)
- [x] 1.2 Add Memory model to `memory_mgmt.py` (id, memory_space FK, owner_username, owner_domain, title, content, timestamps)
- [x] 1.3 Update `server/apps/opspilot/models/__init__.py` to export new models
- [x] 1.4 Create and run database migrations

## 2. Backend API (Memory Space Management)

- [x] 2.1 Create `server/apps/opspilot/serializers/memory_serializer.py` with MemorySpaceSerializer and MemorySerializer
- [x] 2.2 Create `server/apps/opspilot/viewsets/memory_view.py` with MemorySpaceViewSet (CRUD, team filtering)
- [x] 2.3 Add MemoryViewSet to `memory_view.py` with scope-based permission filtering (personal: only creator by username+domain)
- [x] 2.4 Update `server/apps/opspilot/viewsets/__init__.py` to export new viewsets
- [x] 2.5 Register memory_space and memory routes in `server/apps/opspilot/urls.py`
- [x] 2.6 Add operation audit logs for MemorySpace and Memory CRUD operations

## 3. Backend Memory Service

- [x] 3.1 Implement memory write logic in `server/apps/opspilot/tasks.py` as `process_memory_write` Celery task
- [x] 3.2 Implement LLM-based content normalization using write_rule
- [x] 3.3 Implement LLM-based intelligent update/create decision (reads existing memories, decides to merge or create new)
- [x] 3.4 Enhanced merge prompt with detailed rules and examples to ensure proper content merging (not replacement)

## 4. Backend Workflow Nodes

- [x] 4.1 Create `server/apps/opspilot/utils/chat_flow_utils/nodes/memory/` directory
- [x] 4.2 Create `memory_read.py` with MemoryReadNode - implement execute() with scope-based permission check (personal: filter by username+domain)
- [x] 4.3 Create `memory_write.py` with MemoryWriteNode - implement execute() with async task trigger
- [x] 4.4 Create `__init__.py` in memory directory to export executors
- [x] 4.5 Register `memory_read` and `memory_write` in `server/apps/opspilot/utils/chat_flow_utils/engine/node_registry.py`

## 5. Frontend Types and Constants

- [x] 5.1 Add `memory_read` and `memory_write` to NodeType union in `web/src/app/opspilot/components/chatflow/types.ts`
- [x] 5.2 Add MemoryReadNodeConfig and MemoryWriteNodeConfig interfaces to types.ts
- [x] 5.3 Add default configs for memory_read and memory_write in `web/src/app/opspilot/components/chatflow/constants.ts`

## 6. Frontend API Hooks

- [x] 6.1 Create `web/src/app/opspilot/api/memory.ts` with useMemorySpaces, useMemorySpace, useCreateMemorySpace, useUpdateMemorySpace, useDeleteMemorySpace hooks
- [x] 6.2 Add useMemories, useMemory, useUpdateMemory, useDeleteMemory hooks to memory.ts

## 7. Frontend Workflow Node Components

- [x] 7.1 Create `web/src/app/opspilot/components/chatflow/nodes/MemoryReadNode.tsx` wrapping BaseNode
- [x] 7.2 Create `web/src/app/opspilot/components/chatflow/nodes/MemoryWriteNode.tsx` wrapping BaseNode
- [x] 7.3 Export new nodes in `web/src/app/opspilot/components/chatflow/nodes/index.tsx`
- [x] 7.4 Register nodes in nodeTypes in `web/src/app/opspilot/components/chatflow/ChatflowEditor.tsx`

## 8. Frontend Node Configuration Panels

- [x] 8.1 Create `web/src/app/opspilot/components/chatflow/components/nodeConfigs/MemoryReadConfig.tsx` with memory space selector
- [x] 8.2 Create `web/src/app/opspilot/components/chatflow/components/nodeConfigs/MemoryWriteConfig.tsx` with memory space selector
- [x] 8.3 Export new configs in `web/src/app/opspilot/components/chatflow/components/nodeConfigs/index.ts`
- [x] 8.4 Add cases for memory_read and memory_write in `web/src/app/opspilot/components/chatflow/NodeConfigForm.tsx`

## 9. Frontend Memory Management Pages

- [x] 9.1 Create `web/src/app/opspilot/(pages)/memory/page.tsx` - memory space list page with cards
- [x] 9.2 Create memory space create/edit modal component
- [x] 9.3 Create `web/src/app/opspilot/(pages)/memory/[id]/page.tsx` - memory space detail page with memory list
- [x] 9.4 Create memory entry preview/edit component with Markdown support
- [x] 9.5 Add test_write endpoint for testing memory write rules

## 10. Frontend Navigation and i18n

- [x] 10.1 Add "记忆" navigation item to opspilot main navigation menu
- [x] 10.2 Add memory icon to navigation
- [x] 10.3 Add i18n translations for memory module (en.json, zh.json)

## 11. Testing and Verification

- [x] 11.1 Test memory space CRUD via API
- [x] 11.2 Test memory read node execution with personal scope (creator vs non-creator)
- [x] 11.3 Test memory read node execution with team scope
- [x] 11.4 Test memory write node execution with async task
- [x] 11.5 Test memory extraction and merge with LLM
- [x] 11.6 Test frontend memory management pages
- [x] 11.7 Test workflow editor with new nodes
