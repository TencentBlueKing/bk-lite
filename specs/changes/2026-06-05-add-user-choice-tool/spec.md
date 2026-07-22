# 2026 06 05 Add User Choice Tool

Status: done

## Migration Context

- Legacy source: `openspec/changes/archive/2026-06-05-add-user-choice-tool/`
- Legacy state: `archived`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

## Why

OpsPilot 的 ReAct Loop 目前只有审批功能（`request_human_approval`），用于高危操作的人工确认。但当 LLM 需要用户从多个选项中选择时（如用户请求查询多个表但一次只能查一个），只能通过普通对话让用户打字回复，体验不佳。

需要一个点击式的用户选择功能，让用户可以直接点击选项而不是打字，提升交互效率和用户体验。

## What Changes

- 新增 `request_user_choice` 工具，供 LLM 在需要用户选择时调用
- 新增 `user_choice_request` SSE 事件，前端渲染选择卡片
- 新增 `/submit_choice/` API 端点，接收用户选择
- 新增 `UserChoiceCard` 前端组件，支持按钮/下拉/复选框三种交互模式
- 支持单选和多选
- 支持超时后使用默认值

## Capabilities

### New Capabilities

- `user-choice-tool`: 后端用户选择工具实现，包括工具构建、缓存存储、等待轮询逻辑
- `user-choice-frontend`: 前端用户选择组件和 SSE 事件处理

### Modified Capabilities

<!-- 无需修改现有 spec -->

## Impact

- **后端代码**:
  - `server/apps/opspilot/utils/user_choice.py` (新增)
  - `server/apps/opspilot/metis/llm/chain/node.py` (添加 `_build_choice_tool`)
  - `server/apps/opspilot/views.py` (添加 `submit_choice` 端点)
  - `server/apps/opspilot/urls.py` (添加路由)

- **前端代码**:
  - `web/src/app/opspilot/components/custom-chat-sse/UserChoiceCard.tsx` (新增)
  - `web/src/app/opspilot/components/custom-chat-sse/aguiMessageHandler.ts` (处理新事件)
  - `web/src/app/opspilot/types/global.ts` (添加类型定义)
  - `web/src/app/opspilot/types/chat.ts` (添加事件类型)

- **API**: 新增 `POST /api/opspilot/bot_mgmt/submit_choice/`

- **依赖**: 无新增依赖，复用现有 Redis 缓存机制

## Implementation Decisions

## Context

OpsPilot 的 ReAct Loop 已有审批功能（`request_human_approval`），通过 SSE 事件 + Redis 轮询实现人机交互。本设计复用该架构，新增用户选择功能。

**现有架构**:
```
LLM 调用工具 → dispatch_custom_event → SSE 推送 → 前端渲染卡片
                                                      ↓
后端 wait_for_xxx() 轮询 ← Redis Cache ← POST /submit_xxx/ ← 用户操作
```

**约束**:
- 必须与现有 AG-UI 协议兼容
- 复用 Redis 缓存机制，不引入新依赖
- 前端组件风格与 ApprovalCard 保持一致

## Goals / Non-Goals

**Goals:**
- 提供 `request_user_choice` 工具，LLM 可主动调用让用户选择
- 支持单选（按钮/下拉）和多选（复选框）两种模式
- 超时后自动使用默认值，不阻塞流程
- 前端根据选项数量自动选择最佳交互形式

**Non-Goals:**
- 系统强制触发（prepareStep hook 检测）- 后续迭代
- 选项分组、搜索过滤 - 后续迭代
- 选项动态加载（异步获取选项列表）- 后续迭代

## Decisions

### 1. 工具设计：结构化输入

**决策**: 使用 Pydantic 定义工具输入 schema，与 `request_human_approval` 保持一致。

```python
class ChoiceToolInput(BaseModel):
    title: str           # 选择标题
    options: List[ChoiceOption]  # 选项列表
    description: str = ""        # 补充说明
    multiple: bool = False       # 是否多选
    default_keys: List[str] = [] # 超时默认值
```

**理由**: 结构化输入让 LLM 更容易正确调用，也便于前端解析渲染。

### 2. 交互模式：自动适配

**决策**: 前端根据 `display_hint` + 选项数量自动选择交互形式：

| 条件 | 交互形式 |
|------|----------|
| `multiple=true` | 复选框 + 确认按钮 |
| `options.length ≤ 5` | 按钮组（点击即提交） |
| `options.length > 5` | 下拉菜单 |

**理由**: 减少 LLM 决策负担，同时保证最佳用户体验。

### 3. 单选按钮：点击即提交

**决策**: 单选模式下，用户点击按钮后立即提交，无需额外确认。

**理由**: 减少交互步骤，提升效率。多选模式因需要选择多个，保留确认按钮。

### 4. 超时策略：使用默认值

**决策**: 超时后使用 `default_keys` 指定的选项，若未指定则使用第一个选项。

**备选方案**:
- 超时后取消操作 - 会中断流程，体验差
- 无限等待 - 可能导致资源泄漏

**理由**: 保证流程可继续，同时通过返回文本告知 LLM 是超时自动选择。

### 5. 缓存 Key 设计

**决策**: `choice:{execution_id}:{node_id}:{choice_id}`

与审批功能保持一致的命名模式，便于维护和调试。

### 6. 事件名称

**决策**: SSE 事件名 `user_choice_request`，与 `approval_request` 并列。

**理由**: 语义清晰，前端可独立处理不同事件类型。

## Risks / Trade-offs

| 风险 | 缓解措施 |
|------|----------|
| LLM 滥用选择工具（本可直接执行却要求选择） | 工具描述明确使用场景，prompt 中约束 |
| 选项过多导致界面拥挤 | 超过 5 个自动切换下拉菜单 |
| 用户长时间不选择占用资源 | 300s 超时 + 自动使用默认值 |
| 前端组件与现有样式不一致 | 复用 ApprovalCard 的样式基础 |

## 数据流

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              完整数据流                                  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────┐    ┌──────────────────┐    ┌─────────────────────────────┐ │
│  │   LLM   │───▶│ request_user_    │───▶│ dispatch_custom_event(     │ │
│  │         │    │ choice()         │    │   "user_choice_request",   │ │
│  └─────────┘    └──────────────────┘    │   {...}                    │ │
│       ▲                                 │ )                          │ │
│       │                                 └──────────────┬──────────────┘ │
│       │                                                │                │
│       │                                                ▼                │
│       │         ┌──────────────────┐    ┌─────────────────────────────┐ │
│       │         │ wait_for_choice()│    │      SSE Stream             │ │
│       │         │ 轮询 Redis       │    │      ↓                      │ │
│       │         └────────┬─────────┘    │ AGUIMessageHandler          │ │
│       │                  │              │      ↓                      │ │
│       │                  │              │ UserChoiceCard 渲染         │ │
│       │                  │              └──────────────┬──────────────┘ │
│       │                  │                             │                │
│       │                  │                             ▼                │
│       │                  │              ┌─────────────────────────────┐ │
│       │                  │              │ 用户点击选项                 │ │
│       │                  │              │      ↓                      │ │
│       │                  │              │ POST /submit_choice/        │ │
│       │                  │              └──────────────┬──────────────┘ │
│       │                  │                             │                │
│       │                  │                             ▼                │
│       │                  │              ┌─────────────────────────────┐ │
│       │                  └──────────────│ Redis Cache                 │ │
│       │                                 │ choice:{eid}:{nid}:{cid}    │ │
│       │                                 └─────────────────────────────┘ │
│       │                                                                 │
│       └─────────────────────────────────────────────────────────────────┘
│         返回: "用户选择了: xxx (keys: [...])"                            │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-05-14
```

## Capability Deltas

### user-choice-frontend

## ADDED Requirements

### Requirement: 前端处理 user_choice_request 事件

前端 SHALL 监听并处理 `user_choice_request` SSE 事件，渲染用户选择卡片。

#### Scenario: 接收并渲染选择卡片

- **WHEN** 前端收到 `user_choice_request` 事件
- **THEN** AGUIMessageHandler 解析事件数据
- **AND** 在当前消息中渲染 UserChoiceCard 组件

#### Scenario: 保留已提交状态

- **WHEN** 用户已提交选择后，SSE 流继续推送更新
- **THEN** 前端 MUST 保留用户已提交的状态，不被后续更新覆盖

### Requirement: 交互模式自动适配

前端 SHALL 根据选项数量和多选配置自动选择最佳交互形式。

#### Scenario: 少量选项使用按钮

- **WHEN** `multiple=false` 且 `options.length <= 5`
- **THEN** 渲染按钮组形式，每个选项一个按钮

#### Scenario: 大量选项使用下拉菜单

- **WHEN** `multiple=false` 且 `options.length > 5`
- **THEN** 渲染下拉菜单形式

#### Scenario: 多选使用复选框

- **WHEN** `multiple=true`
- **THEN** 渲染复选框列表 + 确认按钮

### Requirement: 单选按钮点击即提交

前端 SHALL 在单选模式下，用户点击按钮后立即提交选择。

#### Scenario: 点击按钮直接提交

- **WHEN** 用户在单选按钮模式下点击某个选项
- **THEN** 前端立即调用 `/submit_choice/` API 提交选择
- **AND** 无需额外确认步骤

### Requirement: 多选需要确认提交

前端 SHALL 在多选模式下，用户需点击确认按钮才提交选择。

#### Scenario: 多选需要确认

- **WHEN** 用户在多选模式下勾选了多个选项
- **THEN** 用户 MUST 点击"确认"按钮才提交选择
- **AND** 确认按钮显示已选数量（如 "确认 (2/3)"）

#### Scenario: 最少选择数量校验

- **WHEN** 用户选择数量少于 `min_select`
- **THEN** 确认按钮 MUST 禁用
- **AND** 显示提示信息

### Requirement: 倒计时显示

前端 SHALL 显示剩余选择时间的倒计时。

#### Scenario: 显示剩余时间

- **WHEN** 选择卡片渲染时
- **THEN** 显示剩余秒数，每秒更新

#### Scenario: 倒计时归零

- **WHEN** 剩余时间归零
- **THEN** 选择卡片切换为"已超时"状态
- **AND** 显示使用的默认选项

### Requirement: 提交选择 API 调用

前端 SHALL 调用 `/api/proxy/opspilot/bot_mgmt/submit_choice/` 提交用户选择。

#### Scenario: 成功提交

- **WHEN** 用户完成选择并提交
- **THEN** 前端 POST 请求包含 `execution_id`, `node_id`, `choice_id`, `selected`
- **AND** 成功后更新卡片状态为"已提交"

#### Scenario: 提交失败

- **WHEN** API 调用失败
- **THEN** 显示错误提示
- **AND** 允许用户重试

### Requirement: 推荐选项高亮

前端 SHALL 对标记为推荐的选项进行视觉高亮。

#### Scenario: 显示推荐标签

- **WHEN** 选项的 `recommended=true`
- **THEN** 该选项显示"推荐"标签
- **AND** 使用高亮样式区分

### Requirement: 类型定义

前端 SHALL 定义完整的 TypeScript 类型。

#### Scenario: UserChoiceRequest 类型

- **WHEN** 定义 UserChoiceRequest 接口
- **THEN** MUST 包含以下字段：
  - `execution_id: string`
  - `node_id: string`
  - `choice_id: string`
  - `title: string`
  - `description?: string`
  - `options: UserChoiceOption[]`
  - `multiple: boolean`
  - `min_select: number`
  - `max_select: number`
  - `timeout_seconds: number`
  - `default_keys: string[]`
  - `display_hint: 'auto' | 'buttons' | 'dropdown' | 'checkbox'`
  - `received_at: number` (前端添加)
  - `status: 'pending' | 'submitted' | 'timeout'` (前端状态)
  - `selected?: string[]` (用户选择结果)

#### Scenario: UserChoiceOption 类型

- **WHEN** 定义 UserChoiceOption 接口
- **THEN** MUST 包含以下字段：
  - `key: string`
  - `label: string`
  - `description?: string`
  - `icon?: string`
  - `disabled?: boolean`
  - `recommended?: boolean`

### user-choice-tool

## ADDED Requirements

### Requirement: LLM 可调用用户选择工具

系统 SHALL 提供 `request_user_choice` 工具，LLM 在需要用户从多个选项中选择时可调用此工具。

#### Scenario: LLM 调用选择工具请求单选

- **WHEN** LLM 调用 `request_user_choice` 工具，参数包含 `title="请选择要查询的表"`, `options=[{key:"orders", label:"orders 表"}, {key:"customers", label:"customers 表"}]`, `multiple=false`
- **THEN** 系统发射 `user_choice_request` SSE 事件，包含完整的选择请求数据
- **AND** 工具进入等待状态，轮询 Redis 获取用户选择结果

#### Scenario: LLM 调用选择工具请求多选

- **WHEN** LLM 调用 `request_user_choice` 工具，参数包含 `multiple=true`, `max_select=3`
- **THEN** 系统发射 `user_choice_request` SSE 事件，`multiple` 字段为 `true`
- **AND** 前端渲染复选框形式的选择界面

### Requirement: 用户选择结果返回给 LLM

系统 SHALL 将用户的选择结果以文本形式返回给 LLM，包含选中的选项标签和 key。

#### Scenario: 用户完成选择

- **WHEN** 用户在前端选择了 `orders` 选项并提交
- **THEN** 工具返回文本 `"用户选择了: orders 表 (keys: ['orders'])"`
- **AND** LLM 可根据返回的 key 继续执行后续操作

#### Scenario: 用户选择多个选项

- **WHEN** 用户在多选模式下选择了 `orders` 和 `customers` 两个选项
- **THEN** 工具返回文本 `"用户选择了: orders 表, customers 表 (keys: ['orders', 'customers'])"`

### Requirement: 超时自动使用默认值

系统 SHALL 在用户未在规定时间内选择时，自动使用默认选项继续流程。

#### Scenario: 超时使用指定默认值

- **WHEN** 用户 300 秒内未做出选择
- **AND** 工具调用时指定了 `default_keys=["orders"]`
- **THEN** 工具返回文本 `"用户未在规定时间内选择，已使用默认选项: orders 表 (keys: ['orders'])"`

#### Scenario: 超时使用第一个选项

- **WHEN** 用户 300 秒内未做出选择
- **AND** 工具调用时未指定 `default_keys`
- **THEN** 系统使用选项列表中的第一个选项作为默认值

### Requirement: 无人值守场景自动选择

系统 SHALL 在无人值守场景（定时任务）下不等待用户选择，直接使用默认值。

#### Scenario: 定时任务触发时自动选择

- **WHEN** `trigger_type="unattended"` 时调用选择工具
- **THEN** 工具立即返回默认选项，不发射 SSE 事件
- **AND** 返回文本包含 `"自动选择"` 标识

### Requirement: 选择请求数据结构

系统 SHALL 使用标准化的数据结构传递选择请求。

#### Scenario: SSE 事件包含完整数据

- **WHEN** 系统发射 `user_choice_request` 事件
- **THEN** 事件数据 MUST 包含以下字段：
  - `execution_id`: 执行标识
  - `node_id`: 节点标识
  - `choice_id`: 选择请求唯一标识
  - `title`: 选择标题
  - `options`: 选项列表，每个选项包含 `key`, `label`
  - `multiple`: 是否多选
  - `timeout_seconds`: 超时时间
  - `default_keys`: 默认选项 key 列表

### Requirement: 选择结果缓存

系统 SHALL 使用 Redis 缓存存储用户选择结果。

#### Scenario: 缓存 Key 格式

- **WHEN** 用户提交选择
- **THEN** 系统将结果存储到 Redis，Key 格式为 `choice:{execution_id}:{node_id}:{choice_id}`

#### Scenario: 缓存自动过期

- **WHEN** 选择结果存入 Redis
- **THEN** 缓存 TTL 设置为 600 秒（可通过环境变量 `CHOICE_CACHE_TTL` 配置）

## Work Checklist

## 1. 后端核心模块

- [x] 1.1 创建 `server/apps/opspilot/utils/user_choice.py`，实现缓存存储和轮询逻辑
- [x] 1.2 在 `server/apps/opspilot/metis/llm/chain/node.py` 中添加 `_build_choice_tool()` 方法
- [x] 1.3 在 `build_react_nodes()` 中注入 choice_tool（与 approval_tool 并列）

## 2. 后端 API 端点

- [x] 2.1 在 `server/apps/opspilot/views.py` 中添加 `submit_choice` 视图函数
- [x] 2.2 在 `server/apps/opspilot/urls.py` 中添加 `/submit_choice/` 路由

## 3. 前端类型定义

- [x] 3.1 在 `web/src/app/opspilot/types/global.ts` 中添加 `UserChoiceOption` 和 `UserChoiceRequest` 接口
- [x] 3.2 在 `web/src/app/opspilot/types/chat.ts` 中添加 `UserChoiceRequestValue` 类型
- [x] 3.3 更新 `AGUIMessage.value` 联合类型，包含 `UserChoiceRequestValue`
- [x] 3.4 在 `CustomChatMessage` 接口中添加 `userChoiceRequests?: UserChoiceRequest[]` 字段

## 4. 前端 SSE 事件处理

- [x] 4.1 在 `aguiMessageHandler.ts` 中添加 `userChoiceRequests` 数组和处理逻辑
- [x] 4.2 添加 `handleUserChoiceRequest()` 方法处理 `user_choice_request` 事件
- [x] 4.3 在 `updateMessageContent()` 中同步 `userChoiceRequests` 状态

## 5. 前端选择卡片组件

- [x] 5.1 创建 `web/src/app/opspilot/components/custom-chat-sse/UserChoiceCard.tsx` 组件
- [x] 5.2 实现按钮模式（单选，≤5 选项）
- [x] 5.3 实现下拉菜单模式（单选，>5 选项）
- [x] 5.4 实现复选框模式（多选）
- [x] 5.5 实现倒计时显示
- [x] 5.6 实现推荐选项高亮
- [x] 5.7 添加组件样式（复用 ApprovalCard 样式基础）

## 6. 前端组件集成

- [x] 6.1 在 `custom-chat-sse/index.tsx` 中导入并渲染 UserChoiceCard
- [x] 6.2 实现 `onSubmit` 回调，更新消息状态

## 7. 国际化

- [x] 7.1 添加中文翻译 key（chat.choiceMinSelect, chat.choiceSubmitFailed, chat.choicePlaceholder, chat.choiceConfirm, chat.choiceTimeout, chat.choiceSelected）
- [x] 7.2 添加英文翻译

## 8. 测试

- [x] 8.1 创建 `server/apps/opspilot/tests/react_agent/cases/test_user_choice.py` 单元测试
- [x] 8.2 测试工具注入、选择提交、超时处理、无人值守场景
