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
