# Add Nats Trigger Web Chat Exposure

Status: ready

## Migration Context

- Legacy source: `openspec/changes/add-nats-trigger-web-chat-exposure/`
- Legacy state: `active`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

## Why

opspilot 工作台（Bot + BotWorkFlow）的 NATS 触发节点当前接收告警中心经 NATS 触发的执行，但**不会在 web 端形成可见的会话**。根因是 `nats_api.trigger_workflow_by_nats` 没生成 session_id、`engine.execute` 收到的 `user_id` 是空串，导致 `ExecutionRepository.record_conversation_history` 在 `if not user_id or ... return` 处短路（`execution_repository.py:217`），`WorkFlowConversationHistory` 一条 NATS 触发都不写。结果是告警触发的执行只在 `WorkFlowTaskResult(execute_type='nats')` 留痕，告警干系人没有 web 端渠道跟进。需求是给 NATS 触发节点加可选项 `expose_as_web_chat`，开启后 NATS 触发生成新会话、`user_ids` 列表作为干系人、干系人可在 web 查看历史与继续对话。

## What Changes

- 在 NATS 触发节点的 `node_config.data.config` 中新增可选项 `expose_as_web_chat: bool`（默认 `false`）。
- 新增 `BotWebChatSession` 数据模型（`session_id` PK + `bot_id` + `node_id` + `source` + `participants` JSONField + `title` + `is_active` + `created_by` + 时间戳），承载会话元数据与干系人授权信息。
- `ChatApplication` 的 `unique_together` 由 `[bot, node_id]` 调整为 `[bot, node_id, app_type]`，使同一 NATS 节点在 `expose=true` 时可同时存在 `app_type='nats'` 与 `app_type='web_chat'` 两条应用记录。
- NATS 触发链路（`nats_api.trigger_workflow_by_nats`）：仅在 `expose_as_web_chat=true` 时创建 `BotWebChatSession` 行、生成 UUID `session_id`、将 `session_id` 与 `user_id=user_ids[0]` 注入 `input_data`；`expose=false` 时行为完全不变。
- 应用发布同步（`ChatApplication.sync_applications_from_workflow`）：扫到 `type=='nats'` 且 `expose=true` 的节点时，额外 upsert 一条 `app_type='web_chat'` 的 `ChatApplication`（`app_name` 加 `[NATS] ` 前缀，复用同一 `node_id`），作为 web 端干系人发现入口。
- web 端会话查询（`web_chat_sessions`）：在现有 owner 会话结果之后**附加**查询 `BotWebChatSession` 中 `participants` 包含当前用户（或 `{username}@{domain}`）的会话，统一以 `{session_id, title, bot_id, source}` 结构返回。
- web 端会话详情（`session_messages`）：先按 `(bot_id, node_id, session_id)` 取 `BotWebChatSession`，校验当前用户在 `participants`，否则 `403`；通过则返回 `WorkFlowConversationHistory` 中 `session_id == X` 的全部消息（不再限定 `entry_type ∈ {web_chat, mobile}`）。
- web 端删除（`delete_session_history`）：同样做参与者授权；通过则删除全部消息并将 `BotWebChatSession.is_active` 置为 `False`（软删）。
- web 端发送入口（`execute_chat_flow`）：当传入的 `session_id` 对应 `source == 'nats'` 且当前用户 ∈ `participants` 时，继续走工作流（同一 NATS 入口节点），新写入的历史 `user_id` 为当前 web 用户、`entry_type='web_chat'`；否则 `403`。
- 前端在 `WebChatSession` 类型加 `source?: 'web_chat' | 'mobile' | 'nats'`，会话列表元素多展示一个 source 标签（Tag 颜色：web_chat=blue / mobile=green / nats=orange）。
- 覆盖率 ≥75% 的 TDD 测试用例：覆盖 NATS 暴露关闭/开启、会话列表可见性、会话详情参与者授权、干系人发言、应用发布同步两条 ChatApplication、删除授权、多干系人共享同一 session。

## Capabilities

### New Capabilities
- `ops-nats-web-chat-exposure`: NATS 触发节点在 `expose_as_web_chat=true` 时，NATS 触发的执行会在 web 端形成由 NATS `user_ids` 列表授权的会话，干系人可查看历史、可继续发消息；参与者授权与会话元数据由新增的 `BotWebChatSession` 模型承担。

### Modified Capabilities
（无现有 spec 的 REQUIREMENTS 受影响。`ops-safety` 与本需求无关；web 会话列表/详情当前没有对应的 OpenSpec capability，本需求首次引入。）

## Impact

### 后端（必须改动）
- `server/apps/opspilot/models/bot_mgmt.py`：新增 `BotWebChatSession` 模型；`ChatApplication.Meta.unique_together` 改为 `[bot, node_id, app_type]`
- 新增 migration：包含 `BotWebChatSession` 新表 + `ChatApplication` unique_together 调整 + 必要索引
- `server/apps/opspilot/nats_api.py` `trigger_workflow_by_nats`：按 `expose_as_web_chat` 分支；`expose=true` 时创建 `BotWebChatSession`、注入 `session_id`/`user_id`；返回值扩展
- `server/apps/opspilot/models/bot_mgmt.py` `ChatApplication.sync_applications_from_workflow`：扫到 `type=='nats'` 且 `expose=true` 时同步两条 `ChatApplication`
- `server/apps/opspilot/viewsets/chat_application_view.py` `web_chat_sessions` action：附加 `BotWebChatSession` 查询
- `server/apps/opspilot/viewsets/chat_application_view.py` `session_messages` action：先做参与者授权再返回历史
- `server/apps/opspilot/viewsets/chat_application_view.py` `delete_session_history` action：参与者授权 + 软删
- `server/apps/opspilot/views.py` `execute_chat_flow`：对 NATS session 做参与者授权

### 前端（轻改动）
- `web/src/app/opspilot/types/studio.ts`：`WebChatSession` 增加 `source` 字段
- `web/src/app/opspilot/(pages)/studio/chat/page.tsx`：会话列表元素展示 source 标签

### 测试（新增）
- `server/apps/opspilot/tests/test_nats_web_chat_exposure.py`：8 项核心场景用例，沿用 `tests/workflow/cases/test_workflow_e2e.py:451` fixture 风格 + `tests/test_workflow_log_pagination.py:21` 纯函数断言风格

### 风险与回滚
- `expose=false` 路径完全不变（向后兼容）
- migration 仅为加法（新表 + unique_together 弱化）
- 回滚：migration down + 关闭 expose 配置即可恢复现状

## Implementation Decisions

## Context

opspilot 工作台（`Bot` + `BotWorkFlow`）的 NATS 触发节点是告警中心推送告警事件的标准入口（注册于 `utils/chat_flow_utils/engine/node_registry.py:42`，由告警中心经 NATS RPC 调用 `nats_api.trigger_workflow_by_nats` 触发）。但当前 NATS 路径下的执行不会在 web 端留下会话：

- `nats_api.trigger_workflow_by_nats`（`nats_api.py:200`）没有为执行生成 `session_id`，传给 `engine.execute` 的 `input_data["user_id"]` 是空串；
- `ChatFlowEngine._record_conversation_history`（`utils/chat_flow_utils/engine/execution_repository.py:217`）的早返条件 `if not user_id or not message or entry_type == "celery": return` 会直接吞掉 NATS 路径的所有 user 消息。

结果是告警触发的执行**只**在 `WorkFlowTaskResult(execute_type='nats')` 留痕，告警干系人没有 web 渠道跟进。约束：保持 `expose_as_web_chat=false` 路径行为完全不变（向后兼容）；复用现有 `user_ids` 字符串列表约定（在 memory 节点的 `flow_input.user_ids` 已有同义使用）；复用现有 `execute_chat_flow` 作为 web 端发送入口，不新建 web_chat endpoint。

涉及模块边界：
- 后端模型 / migration：`server/apps/opspilot/models/bot_mgmt.py`
- 后端 NATS 入口：`server/apps/opspilot/nats_api.py`
- 后端工作流引擎：`server/apps/opspilot/utils/chat_flow_utils/engine/{engine.py, execution_repository.py}`
- 后端应用发布同步：`server/apps/opspilot/models/bot_mgmt.py:474 ChatApplication.sync_applications_from_workflow`
- 后端视图：`server/apps/opspilot/viewsets/chat_application_view.py`、`server/apps/opspilot/views.py:633 execute_chat_flow`
- 前端类型与页面：`web/src/app/opspilot/types/studio.ts`、`web/src/app/opspilot/(pages)/studio/chat/page.tsx`

## Goals / Non-Goals

**Goals:**
- 让工作台 NATS 触发节点可在 `node_config.data.config.expose_as_web_chat=true` 时把触发的执行暴露为 web 端可见的会话。
- 会话以 NATS 入参 `user_ids` 列表为干系人授权依据；干系人登录后可在 web 端会话列表中看到、在会话详情中查看历史、可继续发消息（bot 通过同一 NATS 入口节点继续工作流回复）。
- 默认 `expose_as_web_chat=false` 时行为完全不变；引入的 migration 仅为加法。
- 测试覆盖率 ≥75%，关键路径 TDD 风格（先写测试再写实现）。

**Non-Goals:**
- 不改动 `user_ids` 字符串格式约定；不引入新用户系统。
- 不改动 web_chat 主动发起的会话路径（owner == `{username}@{domain}` 的会话继续走原逻辑）。
- 不引入跨 bot/跨租户共享会话；每个 NATS 触发的会话绑定到触发时的 `bot_id + node_id`。
- 不新增独立的 web_chat endpoint；干系人发言复用现有 `execute_chat_flow`。
- 不做会话语义分析、状态机、关闭/打开/超时等"会话生命周期"功能（仅"持续追加"语义）。

## Decisions

### Decision 1: 引入独立 `BotWebChatSession` 表承载会话元数据与参与者授权
**Rationale:**
- `WorkFlowConversationHistory` 是"每条一行"的消息表，承载 `(bot_id, user_id, session_id, entry_type, conversation_content, conversation_time)`，无法表达"会话级"的元数据（参与者授权列表、会话标题、来源、活跃状态）。
- 复用 `user_id` 单值字段会让"多个干系人共享一个 session"的语义表达困难；强行用 `user_id` 列表会污染现有查询过滤逻辑（`chat_application_view.py:104-128` 的 `web_chat_sessions` 写死 `user_id == f"{username}@{domain}"`）。
- 单独一张会话元数据表（`BotWebChatSession`）使参与者授权与会话生命周期独立演进，且不影响现有消息表的索引与查询路径。

**Alternatives considered:**
- **A. 在 `WorkFlowConversationHistory` 加 `participants JSONField`**：改动最小，但每条消息重复存参与者列表（数据冗余）；失去了"会话级"的元数据抽象。否决。
- **C. 不暴露到 `ChatApplication`，前端单独加一个 tab"我的 NATS 会话"**：避免改 unique_together，但前端多一个入口、与现有 web_chat 入口不统一；干系人要先选 bot 才能选会话，多一跳。否决。

### Decision 2: `ChatApplication` 的 `unique_together` 改为 `[bot, node_id, app_type]`
**Rationale:**
- `ChatApplication` 是 web_chat 应用发现的源头（前端 `chat/page.tsx` 走 `ChatApplicationViewSet.list` 列出应用）；干系人必须能通过现有 web_chat 应用发现路径看到入口。
- NATS 节点 `expose=true` 时需要让"同一 node_id 同时挂 nats 应用和 web_chat 应用"成为可能；现状 `[bot, node_id]` 唯一约束不允许。
- 改 `[bot, node_id, app_type]` 后，sync 逻辑只对 `type=='nats' && expose=true` 的节点多 upsert 一条 `app_type='web_chat'` 记录，`app_name` 加 `[NATS] ` 前缀；其他类型节点行为不变。

**Alternatives considered:**
- **A. 用合成 node_id（如 `nats_xxx`）**：不需要改 unique_together，但要在 sync / publish / chat 入口发现处多做一层映射；语义不清晰。否决。
- **B. 复用同一条 `ChatApplication`，把 `app_type` 改为多值字段（不在枚举范围内）**：打破现有 `app_type` choices 语义。否决。

### Decision 3: NATS 触发链路只在 `expose_as_web_chat=true` 时注入 `session_id` / `user_id`
**Rationale:**
- 默认路径（`expose=false`）行为完全不变；engine 收到的 `input_data["user_id"]` 仍然是空串，`record_conversation_history` 仍然走早返路径。这是"向后兼容"的硬要求。
- `expose=true` 路径注入 `user_id = user_ids[0] if user_ids else ""` 是为了确保首条 user 消息写入历史时不触发早返；后续消息由工作流正常产出，无需特别处理。

**Alternatives considered:**
- **A. 把 NATS 入参拆成"trigger 入参"和"会话初始消息"**：拆得太细，超出本次需求范围；保留 `last_message` 即可。

### Decision 4: web 端发送沿用 `execute_chat_flow`，通过 `session_id` 命中 `BotWebChatSession.source == 'nats'` 时复用同一 NATS 入口节点走工作流
**Rationale:**
- 现有 `execute_chat_flow` 已经支持任意 `session_id` 走工作流；新增一个 endpoint 会与现有路径重复。
- 干系人发消息时，`entry_type` 写 `'web_chat'`（不是 `'nats'`）以区分"系统触发"与"用户后续"在历史中的来源；`user_id` 用当前 web 用户 `{username}@{domain}` 标识发言人。
- 工作流入口仍是 NATS 节点（同一 `node_id`）；`EntryNode.execute` 只读 `data.config` 的 `inputParams/outputParams`，与 `entry_type` 无关，因此 bot 的语义不会因为 `entry_type` 变化而变。

**Alternatives considered:**
- **A. 干系人发言只追加到历史，不触发工作流**：语义最弱，与"且能对话"的明确需求冲突。否决。

### Decision 5: 参与者授权放在 web 端 4 个接口（list/detail/delete/send）
**Rationale:**
- 所有 web 端入口（`web_chat_sessions`、`session_messages`、`delete_session_history`、`execute_chat_flow`）必须做参与者授权；不在前端依赖任何"前端只展示自己会话"的隐式保护。
- 授权匹配支持两种格式：`request.user.username` 与 `f"{username}@{domain}"`，以兼容不同部署下 NATS 调用方传入的 user_id 格式。

## Risks / Trade-offs

- **[R1] `ChatApplication` unique_together 调整可能影响历史数据** → 当前现状是 `[bot, node_id]` 唯一；放宽到 `[bot, node_id, app_type]` 后，存量数据不会出现冲突（每条历史记录仍是单一 `app_type`）。Mitigation：migration 加数据校验步骤，确认无 `(bot, node_id, app_type)` 重复。
- **[R2] 参与者授权写多接口容易遗漏** → 在 `execute_chat_flow` 和 3 个 viewset action 都要做。Mitigation：所有授权函数收敛到 `BotWebChatSession.is_participant(user)` 助手函数；测试覆盖 4 个接口的 negative 路径。
- **[R3] `sync_applications_from_workflow` 行为变更可能影响非 NATS 节点** → 当前 sync 只对 `type=='nats'` 节点改逻辑；其他类型节点（web_chat/mobile）行为不变。Mitigation：sync 逻辑加显式分支，单测覆盖 NATS 节点 expose=true/false/无配置 三种情况。
- **[R4] 前端 Tag 颜色约定可能与现有设计系统冲突** → web_chat=blue / mobile=green / nats=orange 是 AntD 默认色，与现有其他列表 Tag 风格保持一致。Mitigation：实际渲染走 Storybook 验证；如冲突再调整为设计系统色 token。
- **[R5] 干系人 user_ids 格式与 web 用户不一致** → 若 NATS 调用方传 `username` 而 web 用户是 `username@domain`，授权匹配会失败。Mitigation：授权匹配同时支持两种格式（`username` 与 `f"{username}@{domain}"`）；测试覆盖两种格式都能命中。

## Migration Plan

1. **Pre-deploy**: 在 staging 环境跑现有 NATS 工作流若干次，确认 `execute_type='nats'` 的执行仍能在 `WorkFlowTaskResult` 留痕，且 web 会话列表不受影响（无新增可见会话）。
2. **Deploy**:
   - Step 1: 应用 Django migration（新增 `BotWebChatSession` 表 + `ChatApplication` unique_together 调整）；migration 是加法，回滚容易。
   - Step 2: 部署包含 `trigger_workflow_by_nats` / sync / 视图 / 前端逻辑变更的代码；新代码对 `expose=false` 路径完全等价于旧行为。
   - Step 3: 对需要开启新功能的 bot，由工作台编辑者在 NATS 节点配置面板勾选"作为 web 对话"，保存即触发 `sync_applications_from_workflow`，自动生成 `app_type='web_chat'` 应用。
3. **Rollback**:
   - 回滚代码到上一版本（数据库 schema 兼容旧代码）。
   - 若需要彻底回退：migration down（删 `BotWebChatSession` 表 + 恢复 unique_together），同时把所有 NATS 节点的 `expose_as_web_chat` 关闭。
   - `expose=false` 路径永远可作为 fallback，不需要紧急修复。

## Open Questions

- 无。当前 5 条澄清问题已全部对齐（开关位置 / 干系人定义 / 身份映射 / 会话粒度 / web 入口）。
- 后续若需扩展"会话语义状态机"（如 active/closed/archived），属于新的 spec，不在本 change 范围。

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-07-06
```

## Capability Deltas

### ops-nats-web-chat-exposure

## ADDED Requirements

### Requirement: NATS 触发节点支持「作为 web 对话」可选项
NATS 触发节点的 `node_config.data.config` MUST 支持布尔字段 `expose_as_web_chat`，默认 `false`；当且仅当该字段为 `true` 时，NATS 触发的执行才会被暴露为 web 端可见的会话。

#### Scenario: 配置缺省时维持现状
- **WHEN** NATS 触发节点的 `node_config.data.config` 中没有 `expose_as_web_chat` 字段
- **THEN** 节点触发行为与未启用该特性前完全一致：不会创建任何 `BotWebChatSession` 行，`WorkFlowConversationHistory` 中不会出现源自本次 NATS 触发的 user/bot 消息

#### Scenario: 配置显式为 false 时维持现状
- **WHEN** NATS 触发节点的 `node_config.data.config.expose_as_web_chat` 为 `false`
- **THEN** 行为与"配置缺省"完全一致

#### Scenario: 配置为 true 时进入暴露路径
- **WHEN** NATS 触发节点的 `node_config.data.config.expose_as_web_chat` 为 `true` 且 NATS 调用 `trigger_workflow_by_nats` 成功
- **THEN** 系统为本次触发分配一个新 `session_id`（UUID 字符串），并创建一条 `BotWebChatSession` 记录

### Requirement: 暴露模式下生成 BotWebChatSession 会话元数据
当 NATS 触发节点 `expose_as_web_chat=true` 时，系统 MUST 为本次触发创建一条 `BotWebChatSession` 记录，`participants` 字段 SHALL 等于 NATS 入参 `user_ids` 列表，`source` 字段 SHALL 为 `"nats"`。

#### Scenario: 创建会话记录
- **WHEN** NATS 调用 `trigger_workflow_by_nats(message, team, ["alice","bob"], bot_id, node_id)`，且 NATS 节点配置 `expose_as_web_chat=true`
- **THEN** 系统创建一条 `BotWebChatSession`：`session_id` 是新生成的 UUID；`bot_id`、`node_id` 与 NATS 入参一致；`source="nats"`；`participants=["alice","bob"]`；`title` 为 `message` 的前 50 个字符；`is_active=true`

#### Scenario: 注入 session_id 与 user_id 到引擎
- **WHEN** NATS 触发进入暴露路径
- **THEN** 系统将生成的 `session_id` 与 `user_id=user_ids[0]` 注入到 `engine.execute(input_data)` 的 input_data 中，使 `ExecutionRepository.record_conversation_history` 不再被早返条件拦截

#### Scenario: 返回值包含 session_id 与暴露标记
- **WHEN** NATS 触发进入暴露路径并完成执行
- **THEN** `trigger_workflow_by_nats` 的返回值中必须包含 `session_id` 字段与 `exposed_as_web_chat=True`

### Requirement: 干系人可在 web 端会话列表中看到 NATS 会话
`web_chat_sessions` API MUST 把 `BotWebChatSession` 中 `participants` 包含当前 web 用户（或 `{username}@{domain}`）的会话附加到返回列表中，元素结构 SHALL 包含 `session_id`、`title`、`bot_id`、`source`。

#### Scenario: 干系人 A 能看到自己被授权的 NATS 会话
- **WHEN** 干系人 A（`username="alice"`）调用 `GET /opspilot/bot_mgmt/chat_application/web_chat_sessions/?bot_id=X&node_id=Y`
- **AND** 数据库中存在 `BotWebChatSession(bot_id=X, node_id=Y, participants=["alice","bob"], source="nats")`
- **THEN** 返回列表中包含该 NATS 会话，元素 `{session_id, title, bot_id, source="nats"}` 字段齐全

#### Scenario: 非干系人 B 看不到 NATS 会话
- **WHEN** 用户 B（`username="charlie"`）调用同一接口
- **AND** NATS 会话的 `participants` 仅包含 `["alice","bob"]`
- **THEN** 返回列表中不包含该 NATS 会话

#### Scenario: 列表混合展示
- **WHEN** 用户 A（web_chat 会话的 owner 且是 NATS 会话的干系人）调用接口
- **AND** 数据库中既有用户 A 自己发起的 web_chat 会话，又有 A 作为干系人的 NATS 会话
- **THEN** 返回列表同时包含这两类会话，统一结构 `{session_id, title, bot_id, source}`，且 `source` 字段区分 `web_chat`/`mobile`/`nats`

### Requirement: 干系人可查看会话详情；非干系人被拒
`session_messages` API MUST 先按 `(bot_id, node_id, session_id)` 查 `BotWebChatSession`，校验当前 web 用户（或 `{username}@{domain}`）∈ `participants`，否则返回 `403`；通过则返回 `WorkFlowConversationHistory` 中 `session_id == X` 的全部消息，不限定 `entry_type`。

#### Scenario: 干系人 A 可查看会话详情
- **WHEN** 干系人 A 调用 `GET /opspilot/bot_mgmt/chat_application/session_messages/?session_id=X`
- **AND** `BotWebChatSession(session_id=X, participants=["alice","bob"])` 存在
- **THEN** 接口返回 `WorkFlowConversationHistory` 中所有 `session_id=X` 的消息，按 `conversation_time` 升序；既包含 entry_type="nats" 的消息，也包含后续 entry_type="web_chat" 的消息

#### Scenario: 非干系人 B 被拒
- **WHEN** 用户 B（不在 `participants` 中）调用同一接口
- **THEN** 接口返回 `403`

### Requirement: 干系人可继续发言；bot 通过同一 NATS 入口节点走工作流回复
干系人通过 `execute_chat_flow` 在 NATS 会话里发消息时，系统 MUST 校验当前用户 ∈ `BotWebChatSession.participants`，通过后用当前 web 用户作为 `user_id`、`entry_type="web_chat"` 写入历史，并复用同一 NATS 入口节点（`node_id`）触发工作流。

#### Scenario: 干系人 A 成功发言
- **WHEN** 干系人 A 调用 `POST /opspilot/bot_mgmt/execute_chat_flow/<bot_id>/<node_id>/`，body 含 `session_id=X` 与 `message="hello"`
- **AND** `BotWebChatSession(session_id=X, source="nats", participants=["alice","bob"])` 存在
- **THEN** 工作流从该 `node_id` 执行；`WorkFlowConversationHistory` 写入一条 `user_id="alice@<domain>"`、`entry_type="web_chat"`、`session_id=X` 的 user 消息，以及若干 bot 回复消息

#### Scenario: 非干系人 B 发言被拒
- **WHEN** 用户 B（不在 `participants` 中）调用同一接口并传入 `session_id=X`
- **THEN** 接口返回 `403`，不写入任何历史

### Requirement: NATS 节点 expose=true 时同步发布 web_chat 应用
`ChatApplication.sync_applications_from_workflow` 在扫到 `type=='nats'` 且 `node_config.data.config.expose_as_web_chat=true` 的节点时，MUST 在保留原有 `app_type='nats'` `ChatApplication` 的基础上，**额外** upsert 一条 `app_type='web_chat'` 的 `ChatApplication`，复用同一 `node_id`，`app_name` SHALL 加 `[NATS] ` 前缀。

#### Scenario: 发布产生两条 ChatApplication
- **WHEN** 工作流保存，且 flow_json 含一个 NATS 节点（`type='nats'`，`node_config.data.config.expose_as_web_chat=true`）
- **THEN** 数据库中产生两条 `ChatApplication`：`app_type='nats'` 一条，`app_type='web_chat'` 一条，`bot_id` 与 `node_id` 相同；`app_type='web_chat'` 那条的 `app_name` 带 `[NATS] ` 前缀

#### Scenario: expose=false 时只产生 nats 应用
- **WHEN** 工作流保存，且 flow_json 含 NATS 节点 `expose_as_web_chat=false`（或缺省）
- **THEN** 数据库中只产生一条 `app_type='nats'` 的 `ChatApplication`，不产生 `app_type='web_chat'` 条目

### Requirement: 干系人可软删 NATS 会话；非干系人被拒
`delete_session_history` API MUST 校验当前用户 ∈ `BotWebChatSession.participants`，通过则删除 `WorkFlowConversationHistory` 中 `session_id=X` 的全部消息并将 `BotWebChatSession.is_active` 置为 `False`；否则返回 `403`。

#### Scenario: 干系人 A 删除会话成功
- **WHEN** 干系人 A 调用 `POST /opspilot/bot_mgmt/chat_application/delete_session_history/`，body 含 `session_id=X`、`bot_id`、`node_id`
- **THEN** `WorkFlowConversationHistory` 中 `session_id=X` 的全部记录被删除；`BotWebChatSession(session_id=X).is_active` 被置为 `False`

#### Scenario: 非干系人 B 删除被拒
- **WHEN** 用户 B 调用同一接口
- **THEN** 接口返回 `403`，数据未被修改

### Requirement: 多干系人共享同一 session_id
当 NATS 触发入参 `user_ids` 包含多个用户时，所有这些用户 MUST 能在 web 端独立看到同一个 session_id，且任一干系人发言 SHALL 进入同一会话历史。

#### Scenario: 三干系人都能看到同一会话
- **WHEN** NATS 调用 `trigger_workflow_by_nats(..., user_ids=["alice","bob","carol"], ...)`，节点 `expose_as_web_chat=true`
- **THEN** 数据库中存在一条 `BotWebChatSession`，`participants=["alice","bob","carol"]`
- **AND** 三人分别调用 `web_chat_sessions` 接口，都能从返回列表中看到同一个 `session_id`

#### Scenario: 任一干系人发言进入同一会话
- **WHEN** alice 调用 `execute_chat_flow(session_id=X, message="from alice")`
- **THEN** 历史写入 `user_id="alice@<domain>"`、`entry_type="web_chat"`、`session_id=X` 的消息
- **WHEN** bob 调用 `execute_chat_flow(session_id=X, message="from bob")`
- **THEN** 历史写入 `user_id="bob@<domain>"`、`entry_type="web_chat"`、`session_id=X` 的消息
- **THEN** carol 调用 `session_messages(session_id=X)` 能看到 alice 与 bob 的消息，顺序按 `conversation_time` 升序

### Requirement: 暴露模式不影响非 NATS 入口类型
NATS 暴露模式的实现 MUST NOT 改变 `web_chat`、`mobile`、`openai`、`restful` 等其他入口类型的行为；`WorkFlowConversationHistory` 对这些入口的写入路径 SHALL 保持不变。

#### Scenario: web_chat 主动发起的会话仍按 owner=user_id 匹配
- **WHEN** 用户 A 主动通过 `execute_chat_flow` 在 web_chat 入口发起对话
- **THEN** `WorkFlowConversationHistory` 中该会话的 `user_id="alice@<domain>"`、`entry_type="web_chat"`
- **AND** `BotWebChatSession` 中**不**创建新行（仅 NATS 暴露路径才创建）
- **AND** `web_chat_sessions` 接口对该会话的可见性仍按现有 `user_id == "{username}@{domain}"` 过滤逻辑处理

## Work Checklist

## 1. 数据模型与 Migration

- [ ] 1.1 在 `server/apps/opspilot/models/bot_mgmt.py` 新增 `BotWebChatSession` 模型类，包含字段 `session_id` (PK, max_length=100)、`bot_id` (IntegerField, db_index)、`node_id` (CharField, max_length=100, db_index)、`source` (CharField, choices, default='web_chat')、`participants` (JSONField, default=list)、`title` (CharField, max_length=255, blank, default='')、`is_active` (BooleanField, default=True)、`created_by` (CharField, max_length=100, blank, default='')、`created_at` (DateTimeField, auto_now_add)、`updated_at` (DateTimeField, auto_now)；索引 `[bot_id, -created_at]` 与 `[bot_id, node_id, -created_at]`
- [ ] 1.2 调整 `ChatApplication.Meta.unique_together` 由 `[bot, node_id]` 改为 `[bot, node_id, app_type]`，确保同一 NATS 节点在 `expose=true` 时可同时存在 nats 与 web_chat 两条应用
- [ ] 1.3 在 `server/apps/opspilot/models/bot_mgmt.py` 新增 `BotWebChatSession.is_participant(user_id)` 实例方法，接受字符串 user_id 或类字典 user 对象，返回该用户是否在 `participants` 列表中（兼容 `username` 与 `f"{username}@{domain}"` 两种格式）
- [ ] 1.4 生成 Django migration：`cd server && python manage.py makemigrations opspilot`，命名 `add_bot_web_chat_session_and_chatapplication_unique_change`；检查 migration 内容（确保无破坏性 schema 变更），手动添加索引与 unique_together 调整
- [ ] 1.5 在 staging/local 环境应用 migration：`cd server && python manage.py migrate opspilot`；验证 `bot_mgmt_botwebchatsession` 表创建成功，`bot_mgmt_chatapplication` 索引调整为新唯一约束

## 2. NATS 触发链路改造

- [ ] 2.1 在 `server/apps/opspilot/nats_api.py` 新增内部函数 `_read_nats_node_expose_flag(bot_id, node_id)`，从 `BotWorkFlow.flow_json` 解析指定 node 的 `data.config.expose_as_web_chat`，缺省返回 False
- [ ] 2.2 在 `server/apps/opspilot/nats_api.py` `trigger_workflow_by_nats` 函数中：根据 `expose_flag` 走两条分支；`False` 路径维持现状，`True` 路径生成 `session_id = uuid.uuid4().hex`、创建 `BotWebChatSession` 行（participants=user_ids, source='nats', title=message[:50]），将 `session_id` 与 `user_id=user_ids[0]` 注入 input_data 后调 `engine.execute`
- [ ] 2.3 扩展 `trigger_workflow_by_nats` 返回值：`expose=True` 时返回 `{"result": True, "session_id": ..., "exposed_as_web_chat": True, "data": ..., "execution_id": ...}`；`expose=False` 时维持现有返回结构
- [ ] 2.4 确认 `engine.execute` 与 `ExecutionRepository.record_conversation_history` 在 NATS 暴露路径下能正确写入 `WorkFlowConversationHistory`：`session_id` 非空、`user_id` 非空（取 `user_ids[0]`）、`entry_type='nats'`；早返条件不再触发

## 3. 应用发布同步改造

- [ ] 3.1 在 `server/apps/opspilot/models/bot_mgmt.py` `ChatApplication.sync_applications_from_workflow` 中：当扫到 `type=='nats'` 节点时，读取 `node_config.data.config.expose_as_web_chat`；若为 `true`，除原 `app_type='nats'` upsert 外，**额外** upsert 一条 `app_type='web_chat'` 的 `ChatApplication`（复用同一 `node_id`，`app_name` 加 `[NATS] ` 前缀）
- [ ] 3.2 处理 nats 节点的 `node_config.data.config` 在保存工作流时未被持久化的边界场景：若 sync 找不到 expose 字段，按 False 处理（不写 web_chat 应用），不报错
- [ ] 3.3 验证 sync 函数在 NATS 节点 `expose=false/缺省/true` 三种情况下的行为：False/缺省只产生 nats 应用；true 产生 nats + web_chat 两条；同一 node_id 两条记录 `app_name` 不重复

## 4. web 端 API 改造

- [ ] 4.1 在 `server/apps/opspilot/viewsets/chat_application_view.py` `web_chat_sessions` action 中：现有按 `user_id == f"{username}@{domain}"` + `entry_type='web_chat'` 过滤的逻辑保持；**附加**查询 `BotWebChatSession.objects.filter(participants__contains=<me_username or "{username}@{domain}">, bot_id=bot_id, node_id=node_id, is_active=True)`，按 `-created_at` 排序；把结果拼到现有结果之后，统一元素结构 `{session_id, title, bot_id, source}`
- [ ] 4.2 在 `session_messages` action 中：先按 `(bot_id, node_id, session_id)` 查 `BotWebChatSession` 单行；若不存在或当前用户不在 `participants` 中返回 `403`；通过则返回 `WorkFlowConversationHistory` 中 `session_id == X` 的全部消息（**不再限定 `entry_type ∈ {web_chat, mobile}`**），按 `conversation_time` 升序
- [ ] 4.3 在 `delete_session_history` action 中：先查 `BotWebChatSession` 并做参与者授权；通过则删除 `WorkFlowConversationHistory` 中 `session_id=X` 的全部记录并将 `BotWebChatSession.is_active` 置为 `False`（软删）；否则返回 `403`
- [ ] 4.4 在 `server/apps/opspilot/views.py:633` `execute_chat_flow` 函数中：当传入 `session_id` 且 `BotWebChatSession(source='nats').filter(session_id=...)` 命中时，校验当前用户 ∈ `participants`；通过则用 `user_id=f"{user.username}@{user.domain}"`、`entry_type='web_chat'`、`session_id=X` 走工作流（同一 node_id）；否则返回 `403`
- [ ] 4.5 保留 `execute_chat_flow` 在 `session_id` 为空或命中普通 web_chat 会话时的现有行为不变；非 NATS 会话路径完全不受影响

## 5. 前端轻改动

- [ ] 5.1 在 `web/src/app/opspilot/types/studio.ts` 中，给 `WebChatSession` interface 增加可选字段 `source?: 'web_chat' | 'mobile' | 'nats'`
- [ ] 5.2 在 `web/src/app/opspilot/(pages)/studio/chat/page.tsx` 会话列表元素中，按 `session.source` 渲染 AntD `Tag`：web_chat=blue、mobile=green、nats=orange；缺省按 web_chat 蓝处理
- [ ] 5.3 确认现有 chat 流式发送链路（`handleSendMessage` → `execute_chat_flow` SSE）不变；进入会话与发消息交互无新增弹窗
- [ ] 5.4 在 Storybook 里走一遍 `[NATS] xxx` 应用入口与会话列表渲染，验证 Tag 颜色与现有设计 token 一致

## 6. 测试（TDD 风格，覆盖率 ≥75%）

- [ ] 6.1 新建测试文件 `server/apps/opspilot/tests/test_nats_web_chat_exposure.py`，沿用 `tests/workflow/cases/test_workflow_e2e.py:451` fixture 风格（`bot` + `bot_workflow` + patch `create_chat_flow_engine`）
- [ ] 6.2 测试 6.2.1：`test_nats_trigger_without_expose_flag_unchanged` —— NATS 节点 `expose_as_web_chat` 缺省/为 false 时，`trigger_workflow_by_nats` 行为等价于改动前（不创建 `BotWebChatSession`，`WorkFlowConversationHistory` 不出现源自本次 NATS 的消息）
- [ ] 6.3 测试 6.3.1：`test_nats_trigger_with_expose_creates_session_and_history` —— NATS 节点 `expose=true` 时，触发后 `BotWebChatSession` 行存在（participants=user_ids、source='nats'、title 取 message 前 50 字符），`WorkFlowConversationHistory` 中出现 entry_type='nats' 的 user 消息与 bot 回复，返回值含 `session_id` 与 `exposed_as_web_chat=True`
- [ ] 6.4 测试 6.4.1：`test_web_chat_sessions_lists_participant_nats_session` —— 干系人 alice 调 `web_chat_sessions` 能看到 NATS 会话；测试 6.4.2：`test_web_chat_sessions_hides_non_participant_nats_session` —— 非干系人 charlie 调同一接口看不到
- [ ] 6.5 测试 6.5.1：`test_session_messages_returns_full_history_for_participant` —— 干系人 alice 调 `session_messages` 能取到 `session_id=X` 的全部消息（含 nats 与 web_chat 两条 entry_type）；测试 6.5.2：`test_session_messages_forbidden_for_non_participant` —— 非干系人调返回 403
- [ ] 6.6 测试 6.6.1：`test_execute_chat_flow_with_nats_session_participant_succeeds` —— 干系人 alice 调 `execute_chat_flow(session_id=X, ...)` 成功，工作流从同一 node_id 执行；测试 6.6.2：`test_execute_chat_flow_with_nats_session_non_participant_forbidden` —— 非干系人调返回 403
- [ ] 6.7 测试 6.7.1：`test_sync_creates_two_chat_applications_when_nats_node_exposed` —— NATS 节点 `expose=true` 时 sync 产生 nats + web_chat 两条 `ChatApplication`，app_name 不冲突；测试 6.7.2：`test_sync_creates_only_nats_application_when_not_exposed` —— `expose=false/缺省` 时只产生 nats 一条
- [ ] 6.8 测试 6.8.1：`test_delete_session_soft_deletes_for_participant` —— 干系人 alice 调 `delete_session_history` 成功，历史清空、`is_active=False`；测试 6.8.2：`test_delete_session_forbidden_for_non_participant` —— 非干系人调返回 403
- [ ] 6.9 测试 6.9.1：`test_multiple_participants_share_session` —— NATS 入参 3 个 user_ids 时，3 个干系人都能独立从会话列表看到同一 `session_id`、独立发消息独立看到彼此消息（按 conversation_time 升序）
- [ ] 6.10 测试 6.10.1：`test_backward_compat_web_chat_active_session_unchanged` —— web 主动发起的会话仍走 `user_id="{username}@{domain}"` 匹配，不创建 `BotWebChatSession` 行

## 7. 质量门禁与验证

- [ ] 7.1 后端：`cd server && make test` 全量通过；新增测试覆盖 opspilot 模块 ≥75% 增量行
- [ ] 7.2 后端：`cd server && make lint` 通过（black/isort/flake8 全绿）
- [ ] 7.3 前端：`cd web && pnpm lint && pnpm type-check` 通过
- [ ] 7.4 手动验证（dev 环境）：通过 NATS 模拟触发 `expose=true` 的 NATS 节点，确认 (a) `bot_mgmt_botwebchatsession` 表新增一行；(b) `bot_mgmt_workflowconversationhistory` 出现 entry_type='nats' 的 user/bot 消息；(c) `bot_mgmt_chatapplication` 出现第二条 `app_type='web_chat'` 记录；(d) web 端用其中一个 user_id 登录，能在 `[NATS] xxx` 应用下看到该 session，能查看历史，能继续发消息
- [ ] 7.5 手动验证（dev 环境）：用不在 `participants` 中的 web 用户尝试访问同一 `session_id`，确认 403
- [ ] 7.6 回滚演练（仅文档）：记录"关闭 NATS 节点的 expose_as_web_chat + 回滚 migration"两步回滚路径
- [ ] 7.7 OpenSpec 归档：执行 `openspec archive add-nats-trigger-web-chat-exposure --yes`（在所有任务完成并经过 verify 后）
