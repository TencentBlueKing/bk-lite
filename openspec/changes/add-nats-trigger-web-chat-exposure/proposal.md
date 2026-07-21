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