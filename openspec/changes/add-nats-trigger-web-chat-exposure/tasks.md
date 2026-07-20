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