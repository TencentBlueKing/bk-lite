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