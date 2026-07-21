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