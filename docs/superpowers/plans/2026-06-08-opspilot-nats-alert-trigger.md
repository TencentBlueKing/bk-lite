# OpsPilot NATS 告警触发节点 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让告警中心通过 `send_msg_with_channel` 的 NATS 通道触发 OpsPilot workflow，并把 `message/team/user_ids` 直接落入 `flow_input`，供个人记忆、组织记忆和通知节点复用。

**Architecture:** 保持 system_mgmt 作为统一集成边界：Alert Center 只调用 `send_msg_with_channel`，NATS channel config 负责补齐 `bot_id/node_id`。OpsPilot 侧新增 `nats` 入口并把 `message/team/user_ids` 原样归一化写入 `flow_input`，下游 memory/notification 节点直接消费 `flow_input.user_ids` 和 `flow_input.team`，不再引入额外别名字段。

**Tech Stack:** Django 4.2, NATS (`nats_client`), OpsPilot ChatFlowEngine, pytest, Next.js 16 + TypeScript.

---

## File Structure

- Modify: `server/apps/system_mgmt/nats_api.py`
  - 为 NATS 分支增加 `content` 校验与归一化逻辑。
  - 修正邮件通道对用户名列表的收件人解析，支持 `flow_input.user_ids` 直接复用到邮件发送。
- Modify: `server/apps/system_mgmt/utils/channel_utils.py`
  - 在 NATS 请求发出前，把 channel config 中的 `bot_id`、`node_id` 合并到 payload。
- Modify: `server/apps/system_mgmt/tests/nats_api_test.py`
  - 增加 `send_msg_with_channel` 的 NATS payload 校验测试与 email 用户名收件人测试。
- Modify: `server/apps/opspilot/enum.py`
  - 新增 `WorkFlowExecuteType.NATS`。
- Modify: `server/apps/opspilot/utils/chat_flow_utils/engine/node_registry.py`
  - 注册 `nats -> EntryNode`。
- Modify: `server/apps/opspilot/nats_api.py`
  - 新增 `trigger_workflow_by_nats` 入口和 `flow_input` 构建逻辑。
- Modify: `server/apps/opspilot/utils/chat_flow_utils/nodes/memory/memory_read.py`
  - 个人记忆读取改为消费 `flow_input.user_ids`，按干系人逐个读取并聚合。
  - 组织记忆读取优先消费 `flow_input.team[0]`。
- Modify: `server/apps/opspilot/utils/chat_flow_utils/nodes/memory/memory_write.py`
  - 个人记忆写入改为消费 `flow_input.user_ids`，按干系人逐个写入。
  - 组织记忆写入优先消费 `flow_input.team[0]`。
- Modify: `server/apps/opspilot/utils/chat_flow_utils/nodes/action/action.py`
  - 通知节点在未显式配置 recipients 时，回退使用 `flow_input.user_ids`。
- Modify: `server/apps/opspilot/tests/workflow/cases/test_memory_workflow_nodes.py`
  - 追加多干系人个人记忆读写与 `team[0]` 组织记忆覆盖测试。
- Modify: `server/apps/opspilot/tests/workflow/cases/test_workflow_e2e.py`
  - 追加 NATS 入口 workflow 执行测试、`flow_input` 透传测试、通知节点干系人回退测试。
- Modify: `web/src/app/opspilot/constants/chatflow.ts`
  - 为 `nats` 节点补图标、默认配置、trigger 列表支持。
- Modify: `web/src/app/opspilot/components/chatflow/types.ts`
  - 为 `NodeType` 增加 `nats`。
- Modify: `web/src/app/opspilot/components/studio/chatflowSettings.tsx`
  - 在触发节点列表中加入 `nats`。
- Modify: `web/src/app/opspilot/components/chatflow/nodes/index.tsx`
  - 新增 `NatsTriggerNode`。
- Modify: `web/src/app/opspilot/components/chatflow/ChatflowEditor.tsx`
  - 注册 `nats` 节点组件，并把它加入无输入句柄节点列表。
- Modify: `web/src/app/opspilot/components/chatflow/hooks/useNodeDrop.ts`
  - 为拖拽创建节点时的 label 解析增加 `nats`。
- Modify: `web/src/app/opspilot/components/chatflow/utils/formatConfigInfo.ts`
  - 为 `nats` 增加最小配置摘要展示。
- Modify: `web/src/app/opspilot/locales/zh.json`
  - 增加 `chatflow.nats` 中文文案。
- Modify: `web/src/app/opspilot/locales/en.json`
  - 增加 `chatflow.nats` 英文文案。

不要创建新的测试文件；把测试追加到现有 `server/apps/system_mgmt/tests/nats_api_test.py`、`server/apps/opspilot/tests/workflow/cases/test_memory_workflow_nodes.py`、`server/apps/opspilot/tests/workflow/cases/test_workflow_e2e.py` 中。

## Task 1: 收紧 system_mgmt 的 NATS 契约并补齐路由字段

**Files:**
- Modify: `server/apps/system_mgmt/nats_api.py:668-718`
- Modify: `server/apps/system_mgmt/utils/channel_utils.py:273-294`
- Modify: `server/apps/system_mgmt/tests/nats_api_test.py`

- [ ] **Step 1: 先写 NATS content 校验失败用例**

```python
def test_send_msg_with_channel_rejects_invalid_nats_content(monkeypatch):
    channel = types.SimpleNamespace(id=9, channel_type=nats_api.ChannelChoices.NATS, config={"namespace": "opspilot", "method_name": "trigger_workflow_by_nats"})

    class _QuerySet:
        @staticmethod
        def first():
            return channel

    monkeypatch.setattr(nats_api.Channel.objects, "filter", lambda **kwargs: _QuerySet())

    result = nats_api.send_msg_with_channel(
        channel_id=9,
        title="",
        content={"message": "", "team": "bad", "user_ids": ["alice"]},
        receivers=[],
    )

    assert result["result"] is False
    assert "message" in result["message"]
```

- [ ] **Step 2: 再写 config 注入与 email 用户名收件人用例**

```python
def test_send_nats_message_merges_bot_and_node_from_config(monkeypatch):
    channel = types.SimpleNamespace(
        config={"namespace": "opspilot", "method_name": "trigger_workflow_by_nats", "timeout": 30, "bot_id": 12, "node_id": "nats-entry"},
    )
    captured = {}

    def fake_request_sync(namespace, method_name, _timeout, _raw, **kwargs):
        captured["namespace"] = namespace
        captured["method_name"] = method_name
        captured["timeout"] = _timeout
        captured["kwargs"] = kwargs
        return {"result": True}

    monkeypatch.setattr("apps.system_mgmt.utils.channel_utils.nats_client.request_sync", fake_request_sync)
    result = send_nats_message(channel, {"message": "告警", "team": [2], "user_ids": ["alice"]})

    assert result == {"result": True}
    assert captured["kwargs"]["bot_id"] == 12
    assert captured["kwargs"]["node_id"] == "nats-entry"


@pytest.mark.django_db
def test_send_msg_with_channel_email_accepts_username_receivers(monkeypatch):
    channel = Channel.objects.create(name="mail", channel_type=ChannelChoices.EMAIL, config={"smtp_host": "smtp.example.com"})
    user = User.objects.create(username="alice", email="alice@example.com")
    captured = {}

    def fake_send_email(channel_obj, title, content, user_list, attachments=None):
        captured["usernames"] = list(user_list.values_list("username", flat=True))
        return {"result": True}

    monkeypatch.setattr(nats_api, "send_email", fake_send_email)

    result = nats_api.send_msg_with_channel(channel.id, "主题", "正文", ["alice"])

    assert result == {"result": True}
    assert captured["usernames"] == [user.username]
```

- [ ] **Step 3: 运行这组测试，确认先失败**

Run:

```bash
cd server && uv run pytest apps/system_mgmt/tests/nats_api_test.py -k "nats_content or merges_bot_and_node or username_receivers" -v
```

Expected: FAIL，当前实现还没有 NATS payload 校验、bot/node 注入，以及 email 用户名收件人支持。

- [ ] **Step 4: 写最小实现**

在 `server/apps/system_mgmt/nats_api.py` 中先抽出 NATS content 归一化逻辑，并在 email 分支补用户名查询：

```python
def _normalize_nats_content(content):
    if isinstance(content, str):
        content = json.loads(content)
    if not isinstance(content, dict):
        return None, {"result": False, "message": "NATS content must be a dict"}

    message = str(content.get("message", "")).strip()
    if not message:
        return None, {"result": False, "message": "NATS content.message is required"}

    team = [int(team_id) for team_id in content.get("team", []) if str(team_id).strip()]
    user_ids = [str(user_id).strip() for user_id in content.get("user_ids", []) if str(user_id).strip()]

    return {"message": message, "team": team, "user_ids": user_ids}, None


def _resolve_receivers(receivers):
    if not receivers:
        return None
    if all(isinstance(r, int) or (isinstance(r, str) and r.isdigit()) for r in receivers):
        return User.objects.filter(id__in=[int(r) for r in receivers])
    return User.objects.filter(username__in=[str(r).strip() for r in receivers if str(r).strip()])
```

在 `send_msg_with_channel` 的 NATS 分支改成：

```python
elif channel_obj.channel_type == ChannelChoices.NATS:
    normalized_content, error = _normalize_nats_content(content)
    if error:
        return error
    return send_nats_message(channel_obj, normalized_content)
```

在 `server/apps/system_mgmt/utils/channel_utils.py` 中改成：

```python
bot_id = config.get("bot_id")
node_id = config.get("node_id")

if not namespace or not method_name or not bot_id or not node_id:
    return {"result": False, "message": "NATS channel config missing namespace, method_name, bot_id or node_id"}

payload = {
    **content,
    "bot_id": int(bot_id),
    "node_id": str(node_id),
}
result = nats_client.request_sync(namespace, method_name, _timeout=timeout, _raw=True, **payload)
```

- [ ] **Step 5: 重新运行测试并提交**

Run:

```bash
cd server && uv run pytest apps/system_mgmt/tests/nats_api_test.py -k "nats_content or merges_bot_and_node or username_receivers" -v
```

Expected: PASS

Commit:

```bash
git add server/apps/system_mgmt/nats_api.py server/apps/system_mgmt/utils/channel_utils.py server/apps/system_mgmt/tests/nats_api_test.py
git commit -m "feat: validate nats alert payloads"
```

## Task 2: 接入 OpsPilot 的 NATS 触发入口

**Files:**
- Modify: `server/apps/opspilot/enum.py:57-71`
- Modify: `server/apps/opspilot/utils/chat_flow_utils/engine/node_registry.py:27-65`
- Modify: `server/apps/opspilot/nats_api.py`
- Modify: `server/apps/opspilot/tests/workflow/cases/test_workflow_e2e.py`

- [ ] **Step 1: 先写 NATS 入口 workflow 的失败测试**

在 `test_workflow_e2e.py` 追加一个最小 NATS workflow 测试：

```python
@pytest.mark.django_db(transaction=True)
def test_nats_trigger_executes_workflow(bot_workflow):
    bot_workflow.flow_json = {
        "nodes": [
            {"id": "nats_entry", "type": "nats", "data": {"label": "NATS", "config": {"outputParams": "last_message"}}},
            {"id": "agent_node", "type": "agents", "data": {"label": "Agent", "config": {"inputParams": "last_message", "outputParams": "last_message"}}},
        ],
        "edges": [{"source": "nats_entry", "target": "agent_node"}],
    }
    bot_workflow.save(update_fields=["flow_json"])

    result = trigger_workflow_by_nats(
        message="CPU 告警",
        team=[2],
        user_ids=["alice", "bob"],
        bot_id=bot_workflow.bot_id,
        node_id="nats_entry",
    )

    assert result["result"] is True
    assert result["entry_type"] == "nats"
```

- [ ] **Step 2: 运行测试，确认当前缺少 `nats` 类型和入口方法**

Run:

```bash
cd server && uv run pytest apps/opspilot/tests/workflow/cases/test_workflow_e2e.py -k "nats_trigger_executes_workflow" -v
```

Expected: FAIL，原因应包括缺少 `trigger_workflow_by_nats` 或 `nats` 节点未注册。

- [ ] **Step 3: 写最小后端接线实现**

在 `enum.py` 增加：

```python
class WorkFlowExecuteType(models.TextChoices):
    OPENAI = "openai", _("OpenAI")
    RESTFUL = "restful", _("RESTful")
    CELERY = "celery", _("Celery")
    NATS = "nats", _("NATS")
```

在 `node_registry.py` 增加：

```python
self.register_node_class("nats", EntryNode)
```

在 `server/apps/opspilot/nats_api.py` 增加：

```python
@nats_client.register
def trigger_workflow_by_nats(message, team, user_ids, bot_id, node_id):
    workflow = BotWorkFlow.objects.filter(bot_id=bot_id).first()
    if not workflow:
        return {"result": False, "message": "Bot workflow not found"}

    engine = create_chat_flow_engine(workflow, node_id, entry_type="nats")
    input_data = {
        "last_message": message,
        "message": message,
        "team": [int(team_id) for team_id in team if str(team_id).strip()],
        "user_ids": [str(user_id).strip() for user_id in user_ids if str(user_id).strip()],
        "bot_id": int(bot_id),
        "node_id": node_id,
        "entry_type": "nats",
        "trigger_type": "nats",
        "is_third_party": True,
    }
    result = engine.execute(input_data)
    return {"result": True, "data": result, "entry_type": "nats", "execution_id": engine.execution_id}
```

- [ ] **Step 4: 再补一个 `flow_input` 透传断言**

把 `test_nats_trigger_executes_workflow` 扩成：

```python
task_result = WorkFlowTaskResult.objects.get(execution_id=result["execution_id"])
assert task_result.execute_type == "nats"

engine = create_chat_flow_engine(bot_workflow, "nats_entry", entry_type="nats")
engine.custom_node_executors["agents"] = FakeAgentExecutor(engine.variable_manager)
engine.execute({"last_message": "CPU 告警", "team": [2], "user_ids": ["alice", "bob"], "entry_type": "nats"})
assert engine.variable_manager.get_variable("flow_input")["team"] == [2]
assert engine.variable_manager.get_variable("flow_input")["user_ids"] == ["alice", "bob"]
```

- [ ] **Step 5: 跑通测试并提交**

Run:

```bash
cd server && uv run pytest apps/opspilot/tests/workflow/cases/test_workflow_e2e.py -k "nats_trigger_executes_workflow" -v
```

Expected: PASS

Commit:

```bash
git add server/apps/opspilot/enum.py server/apps/opspilot/utils/chat_flow_utils/engine/node_registry.py server/apps/opspilot/nats_api.py server/apps/opspilot/tests/workflow/cases/test_workflow_e2e.py
git commit -m "feat: add opspilot nats workflow trigger"
```

## Task 3: 让 memory 节点直接消费 `flow_input.user_ids` 和 `flow_input.team`

**Files:**
- Modify: `server/apps/opspilot/utils/chat_flow_utils/nodes/memory/memory_read.py`
- Modify: `server/apps/opspilot/utils/chat_flow_utils/nodes/memory/memory_write.py`
- Modify: `server/apps/opspilot/tests/workflow/cases/test_memory_workflow_nodes.py`

- [ ] **Step 1: 先写多干系人个人记忆测试**

在 `test_memory_workflow_nodes.py` 追加：

```python
@pytest.mark.django_db
def test_personal_memory_write_fans_out_to_all_flow_input_user_ids(memory_space_personal):
    vm = MagicMock()
    vm.get_variable.side_effect = lambda key, default=None: {
        "flow_input": {"user_ids": ["alice@test.com", "bob@test.com", "carol@test.com"]},
        "flow_id": "1001",
    }.get(key, default)

    node = MemoryWriteNode(vm)
    node_config = build_node_config(memory_space_id=memory_space_personal.id, title="Alert Memory")

    with patch("apps.opspilot.utils.chat_flow_utils.nodes.memory.memory_write.MemoryEngineRegistry.get_engine") as mock_get_engine:
        engine = MagicMock()
        engine.write.return_value.success = True
        mock_get_engine.return_value = engine

        node.execute("mem_write_1", node_config, {"last_message": "CPU 告警"})

        assert engine.write.call_count == 3
        user_ids = [call.kwargs["entity"].user_id for call in engine.write.call_args_list]
        assert user_ids == ["alice@test.com", "bob@test.com", "carol@test.com"]
```

再追加组织记忆读取覆盖测试：

```python
@pytest.mark.django_db
def test_team_memory_prefers_flow_input_team_first_item(memory_space_team):
    vm = MagicMock()
    vm.get_variable.side_effect = lambda key, default=None: {
        "flow_input": {"team": [9, 10], "user_ids": ["alice@test.com"]},
    }.get(key, default)

    node = MemoryReadNode(vm)
    node_config = build_node_config(memory_space_id=memory_space_team.id)

    with patch("apps.opspilot.utils.chat_flow_utils.nodes.memory.memory_read.MemoryEngineRegistry.get_engine") as mock_get_engine:
        engine = MagicMock()
        engine.read.return_value.context = "org-9"
        engine.read.return_value.raw_memories = []
        mock_get_engine.return_value = engine

        node.execute("mem_read_1", node_config, {"last_message": "query"})

        assert engine.read.call_args.kwargs["entity"].organization_id == 9
```

- [ ] **Step 2: 运行测试，确认当前还是单用户/静态 team 逻辑**

Run:

```bash
cd server && uv run pytest apps/opspilot/tests/workflow/cases/test_memory_workflow_nodes.py -k "fans_out_to_all_flow_input_user_ids or prefers_flow_input_team_first_item" -v
```

Expected: FAIL，当前实现只读 `flow_input.user_id`，团队记忆也只看 `memory_space.team`。

- [ ] **Step 3: 写最小实现**

在 `memory_write.py` 增加目标解析：

```python
def resolve_personal_user_ids(flow_input, fallback_user_id):
    flow_user_ids = [str(user_id).strip() for user_id in flow_input.get("user_ids", []) if str(user_id).strip()]
    if flow_user_ids:
        return flow_user_ids
    return [fallback_user_id or "system"]


def resolve_team_id(flow_input, memory_space):
    flow_team = [int(team_id) for team_id in flow_input.get("team", []) if str(team_id).strip()]
    if flow_team:
        return flow_team[0]
    team_ids = memory_space.team or []
    return team_ids[0] if team_ids else None
```

个人记忆写入改成循环：

```python
if memory_space.scope == MemorySpace.SCOPE_PERSONAL:
    target_user_ids = resolve_personal_user_ids(flow_input, user_id)
    for target_user_id in target_user_ids:
        entity = MemoryEntity(user_id=target_user_id)
        engine.write(entity=entity, content=message, title=title or f"自动记忆-{node_id}", metadata=metadata, model_id=model_id)
```

`memory_read.py` 同样改成：

```python
if memory_space.scope == MemorySpace.SCOPE_PERSONAL:
    target_user_ids = resolve_personal_user_ids(flow_input, user_id)
    contexts = []
    for target_user_id in target_user_ids:
        result = engine.read(entity=MemoryEntity(user_id=target_user_id), query=message, top_k=top_k)
        if result.context:
            contexts.append(result.context)
    memory_context = "\n\n".join(contexts)
else:
    organization_id = resolve_team_id(flow_input, memory_space)
    result = engine.read(entity=MemoryEntity(organization_id=organization_id), query=message, top_k=top_k)
```

- [ ] **Step 4: 再补一个聚合读取断言**

把个人记忆读取测试补成：

```python
engine.read.side_effect = [
    MemoryReadResult(context="alice-memory", raw_memories=[], source="local"),
    MemoryReadResult(context="bob-memory", raw_memories=[], source="local"),
]

result = node.execute("mem_read_1", node_config, {"last_message": "query"})
assert "alice-memory" in result["memory_context"]
assert "bob-memory" in result["memory_context"]
```

- [ ] **Step 5: 跑通测试并提交**

Run:

```bash
cd server && uv run pytest apps/opspilot/tests/workflow/cases/test_memory_workflow_nodes.py -k "flow_input_user_ids or flow_input_team_first_item or aggregate" -v
```

Expected: PASS

Commit:

```bash
git add server/apps/opspilot/utils/chat_flow_utils/nodes/memory/memory_read.py server/apps/opspilot/utils/chat_flow_utils/nodes/memory/memory_write.py server/apps/opspilot/tests/workflow/cases/test_memory_workflow_nodes.py
git commit -m "feat: support nats memory context fanout"
```

## Task 4: 通知节点回退使用 `flow_input.user_ids`

**Files:**
- Modify: `server/apps/opspilot/utils/chat_flow_utils/nodes/action/action.py:197-242`
- Modify: `server/apps/opspilot/tests/workflow/cases/test_workflow_e2e.py`

- [ ] **Step 1: 先写通知节点回退测试**

在 `test_workflow_e2e.py` 追加：

```python
@pytest.mark.django_db(transaction=True)
def test_notification_node_falls_back_to_flow_input_user_ids(mocker):
    variable_manager = VariableManager()
    variable_manager.set_variable("execution_id", "exec-notify")
    variable_manager.set_variable("flow_input", {"user_ids": ["alice", "bob"]})

    send_mock = mocker.patch(
        "apps.opspilot.utils.chat_flow_utils.nodes.action.action.SystemMgmt.send_msg_with_channel",
        return_value={"result": True, "message": "ok"},
    )

    node = NotifyNode(variable_manager)
    node.execute(
        "notify_node",
        {
            "data": {
                "config": {
                    "notificationType": "email",
                    "notificationMethod": 1,
                    "notificationTitle": "Daily Report",
                    "notificationContent": "See attachment",
                    "notificationRecipients": [],
                    "outputParams": "last_message",
                }
            }
        },
        {"last_message": "ignored"},
    )

    assert send_mock.call_args.kwargs["receivers"] == ["alice", "bob"]
```

- [ ] **Step 2: 运行测试，确认当前空 recipients 只会 warning**

Run:

```bash
cd server && uv run pytest apps/opspilot/tests/workflow/cases/test_workflow_e2e.py -k "falls_back_to_flow_input_user_ids" -v
```

Expected: FAIL，当前实现不会从 `flow_input.user_ids` 回退。

- [ ] **Step 3: 写最小实现**

在 `NotifyNode` 中增加一个收件人解析函数：

```python
def _resolve_receivers(self, config):
    receivers = config.get("notificationRecipients") or config.get("notificationReceivers", [])
    if receivers:
        return receivers

    flow_input = self.variable_manager.get_variable("flow_input", {}) if self.variable_manager else {}
    fallback_receivers = flow_input.get("user_ids", []) if isinstance(flow_input, dict) else []
    return [str(receiver).strip() for receiver in fallback_receivers if str(receiver).strip()]
```

然后在 `execute` 中改成：

```python
receivers = self._resolve_receivers(config)
if not receivers:
    logger.warning(f"通知节点 {node_id} 缺少接收人列表,通知可能无法发送")
```

- [ ] **Step 4: 追加一个静态 recipients 不被覆盖的测试**

```python
assert send_mock.call_args.kwargs["receivers"] == [1, 2]
```

把这个断言写在现有 `test_notification_node_sends_all_execution_attachments` 旁边的新用例中，确认已配置 recipients 时仍走原逻辑。

- [ ] **Step 5: 跑通测试并提交**

Run:

```bash
cd server && uv run pytest apps/opspilot/tests/workflow/cases/test_workflow_e2e.py -k "notification_node" -v
```

Expected: PASS

Commit:

```bash
git add server/apps/opspilot/utils/chat_flow_utils/nodes/action/action.py server/apps/opspilot/tests/workflow/cases/test_workflow_e2e.py
git commit -m "feat: let notification nodes reuse nats stakeholders"
```

## Task 5: 在 Studio 中暴露 `nats` 触发节点

**Files:**
- Modify: `web/src/app/opspilot/constants/chatflow.ts:1-145`
- Modify: `web/src/app/opspilot/components/chatflow/types.ts:1-140`
- Modify: `web/src/app/opspilot/components/studio/chatflowSettings.tsx:15-69`
- Modify: `web/src/app/opspilot/components/chatflow/nodes/index.tsx:1-76`
- Modify: `web/src/app/opspilot/components/chatflow/ChatflowEditor.tsx:276-295,334-336`
- Modify: `web/src/app/opspilot/components/chatflow/hooks/useNodeDrop.ts`
- Modify: `web/src/app/opspilot/components/chatflow/utils/formatConfigInfo.ts`
- Modify: `web/src/app/opspilot/locales/zh.json`
- Modify: `web/src/app/opspilot/locales/en.json`

- [ ] **Step 1: 先写最小前端类型和常量变更**

在 `types.ts` 增加：

```ts
export type NodeType =
  | 'celery'
  | 'restful'
  | 'openai'
  | 'nats'
  | 'agents'
  | 'agui'
  | 'embedded_chat'
  | 'web_chat'
  | 'mobile'
  | 'condition'
  | 'http'
  | 'notification'
  | 'enterprise_wechat'
  | 'dingtalk'
  | 'wechat_official'
  | 'intent_classification'
  | 'memory_read'
  | 'memory_write';
```

在 `chatflow.ts` 增加：

```ts
nats: { icon: 'API', color: 'purple' as const },
export const TRIGGER_NODE_TYPES = ['celery', 'restful', 'openai', 'nats', 'agui', 'embedded_chat', 'web_chat', 'mobile', 'enterprise_wechat', 'dingtalk', 'wechat_official'] as const;
```

并把默认配置显式补齐：

```ts
case 'nats':
  return baseConfig;
```

- [ ] **Step 2: 把节点放进画布组件和文案**

在 `chatflowSettings.tsx` 触发节点列表中加入：

```tsx
{ type: 'nats', icon: 'API', labelKey: 'chatflow.nats' },
```

在 `nodes/index.tsx` 增加：

```tsx
export const NatsTriggerNode = (props: any) => (
  <BaseNode {...props} icon={nodeConfig.nats.icon} color={nodeConfig.nats.color} hasOutput={true} />
);
```

在 `ChatflowEditor.tsx` 注册：

```tsx
nats: createNodeComponent(NatsTriggerNode),
```

并把 `nats` 加入无输入句柄列表：

```tsx
const noInputTypes = ['celery', 'restful', 'openai', 'nats', 'agui', 'embedded_chat', 'web_chat', 'mobile', 'enterprise_wechat', 'dingtalk', 'wechat_official'];
```

在语言文件中增加：

```json
"nats": "NATS触发"
```

和：

```json
"nats": "NATS Trigger"
```

- [ ] **Step 3: 运行前端类型检查，确认首轮报错点**

Run:

```bash
cd web && pnpm type-check
```

Expected: 如果还有遗漏，会报出 `nats` 未覆盖的联合类型或组件引用错误。

- [ ] **Step 4: 修齐遗漏的前端引用**

在 `useNodeDrop.ts` 补齐 label 分支：

```ts
if (nodeType === 'nats') {
  return t('chatflow.nats');
}
```

在 `formatConfigInfo.ts` 补齐摘要分支：

```ts
case 'nats':
  return t('chatflow.nats');
```

不要给 `nats` 节点增加多余配置项；保持和 `restful/openai` 同级的最小触发节点形态。

- [ ] **Step 5: 重新跑类型检查并提交**

Run:

```bash
cd web && pnpm type-check
```

Expected: PASS

Commit:

```bash
git add web/src/app/opspilot/constants/chatflow.ts web/src/app/opspilot/components/chatflow/types.ts web/src/app/opspilot/components/studio/chatflowSettings.tsx web/src/app/opspilot/components/chatflow/nodes/index.tsx web/src/app/opspilot/components/chatflow/ChatflowEditor.tsx web/src/app/opspilot/components/chatflow/hooks/useNodeDrop.ts web/src/app/opspilot/components/chatflow/utils/formatConfigInfo.ts web/src/app/opspilot/locales/zh.json web/src/app/opspilot/locales/en.json
git commit -m "feat: add nats trigger node to studio"
```

## Task 6: 做一次整体验证

**Files:**
- Modify: none
- Test: `server/apps/system_mgmt/tests/nats_api_test.py`
- Test: `server/apps/opspilot/tests/workflow/cases/test_memory_workflow_nodes.py`
- Test: `server/apps/opspilot/tests/workflow/cases/test_workflow_e2e.py`

- [ ] **Step 1: 跑 system_mgmt 相关测试**

Run:

```bash
cd server && uv run pytest apps/system_mgmt/tests/nats_api_test.py -v
```

Expected: PASS

- [ ] **Step 2: 跑 OpsPilot memory 与 workflow 测试**

Run:

```bash
cd server && uv run pytest apps/opspilot/tests/workflow/cases/test_memory_workflow_nodes.py apps/opspilot/tests/workflow/cases/test_workflow_e2e.py -v
```

Expected: PASS

- [ ] **Step 3: 跑前端类型检查**

Run:

```bash
cd web && pnpm type-check
```

Expected: PASS

- [ ] **Step 4: 看一眼 git diff，确认只包含本功能**

Run:

```bash
git --no-pager diff --stat
```

Expected: 只出现 system_mgmt、opspilot、web Studio 相关文件和既定测试文件。

- [ ] **Step 5: 最终提交**

```bash
git add server/apps/system_mgmt/nats_api.py server/apps/system_mgmt/utils/channel_utils.py server/apps/system_mgmt/tests/nats_api_test.py server/apps/opspilot/enum.py server/apps/opspilot/nats_api.py server/apps/opspilot/utils/chat_flow_utils/engine/node_registry.py server/apps/opspilot/utils/chat_flow_utils/nodes/memory/memory_read.py server/apps/opspilot/utils/chat_flow_utils/nodes/memory/memory_write.py server/apps/opspilot/utils/chat_flow_utils/nodes/action/action.py server/apps/opspilot/tests/workflow/cases/test_memory_workflow_nodes.py server/apps/opspilot/tests/workflow/cases/test_workflow_e2e.py web/src/app/opspilot/constants/chatflow.ts web/src/app/opspilot/components/chatflow/types.ts web/src/app/opspilot/components/studio/chatflowSettings.tsx web/src/app/opspilot/components/chatflow/nodes/index.tsx web/src/app/opspilot/components/chatflow/ChatflowEditor.tsx web/src/app/opspilot/locales/zh.json web/src/app/opspilot/locales/en.json
git commit -m "feat: add nats alert trigger workflow"
```
