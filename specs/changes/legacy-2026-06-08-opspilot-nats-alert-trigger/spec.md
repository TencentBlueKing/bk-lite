# Historical Superpowers change: 2026-06-08-opspilot-nats-alert-trigger

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-06-08-opspilot-nats-alert-trigger.md

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

## specs: 2026-06-08-opspilot-nats-alert-trigger-design.md

> ## 方案修订（2026-06-12）
>
> 本文档初版假设「用户在系统管理手动新建 NATS 通道并填 bot_id/node_id」。实现阶段方案做了如下调整，**以下条目优先于正文中相冲突的描述**：
>
> 1. **`team` 由列表改为单个整数**。契约 `content.team` 现在是 `2` 而非 `[2]`；归一化兼容单元素列表，但多元素/空/非数字一律拒绝。下游组织记忆/权限直接用该标量，不再取 `team[0]`。
> 2. **通道由 OpsPilot 在「发布(上线)」时自动创建/对账，用户不再手填 `bot_id`/`node_id`**。
>    - 触发点：`bot_view.update`(is_publish) 与 `start_pilot`；删除 Bot 时清理其通道。
>    - 实现：OpsPilot 扫描 `flow_json` 里 `type=='nats'` 的节点，经 RPC 调 system_mgmt 的 `sync_opspilot_nats_channels`（增/改/删对账）；Bot 删除调 `delete_opspilot_nats_channels`。
>    - 通道命名：`{bot.name} - {节点 label}`（上限 100 字截断）；`team` 取 `bot.team`。
>    - config 写入 `namespace`（取部署的 `NATS_NAMESPACE`，默认 `bklite`，**非** `"opspilot"`）、`method_name="trigger_workflow_by_nats"`、`bot_id`、`node_id`、`timeout`，并以 **`source="opspilot"`** 作为托管标识。
> 3. **托管通道只读**：通道列表/详情前端隐藏「编辑/删除」并提示「OpsPilot 托管」；后端 `ChannelViewSet` 的 `update/destroy/update_settings` 对 `source=="opspilot"` 的 NATS 通道返回 403，防 API 绕过。
> 4. **nats 触发节点多次拖出自动改名**（`NATS触发`、`NATS触发 1`…），保证派生的通道名不冲突。
> 5. **前端不再有「是否 OpsPilot」开关**（曾短暂引入，已回退）；Studio 的 nats 节点也不承载任何路由配置。

## 一、背景

当前仓库里已经存在几块可复用能力：

- `server/apps/system_mgmt/nats_api.py::send_msg_with_channel` 已经是统一的通道发送入口。
- `server/apps/system_mgmt/utils/channel_utils.py::send_nats_message` 已经支持按 NATS channel 的 `namespace`、`method_name` 发起请求。
- OpsPilot workflow 已支持多个入口节点与 `entry_type` 记录机制。
- workflow 下游节点共享 `flow_input` 上下文。
- 现有记忆节点里，个人记忆主要依赖 `flow_input.user_id`，组织记忆仍更多依赖记忆空间本身配置。

这次需求不是让告警中心直接调 OpsPilot 的专用 NATS 接口，而是：

1. 告警中心底层仍调用 `send_msg_with_channel`
2. 当目标通道是 NATS 时，`content` 统一设计为：

```json
{
  "message": "",
  "team": [],
  "user_ids": []
}
```

3. NATS channel 的 `config` 中新增两个路由字段：
   - `bot_id`
   - `node_id`

目标是让告警中心通过这个统一通道，把告警内容、组织信息、通知人信息带入 OpsPilot workflow，并在后续节点里复用这些上下文，尤其是：

- 个人记忆
- 组织记忆
- 邮件/通知
- 组织权限相关工具调用

## 二、目标

- 保持告警中心只依赖 `send_msg_with_channel`，不新增第二套告警专用发送入口。
- 复用现有 NATS channel 能力，不绕开 system_mgmt 的通道抽象。
- 在 OpsPilot workflow 中新增 `nats` 触发节点。
- 把告警中心传入的 `message/team/user_ids` 原样落入 `flow_input`，只做必要归一化，不新增节点用不到的别名字段。
- 让 `user_ids` 成为本次 session 的“干系人”集合，供后续个人记忆、通知类节点复用，并按干系人分别存储个人记忆。
- 让 `team` 成为本次执行的组织上下文，供后续组织记忆、权限校验和资源访问复用。
- 保持对现有非 NATS 通道、非告警 workflow 的兼容。

## 三、不做的范围

- 首版不做告警中心侧的组织自动推断。
- 首版不做复杂的多干系人优先级算法，但要求所有干系人平级生效。
- 首版不扩展第二种 NATS payload 格式。
- 首版不支持一次执行同时对多个组织写入组织记忆。

## 四、方案对比

### 方案 A：在通道层补路由，在 OpsPilot 入口层做上下文标准化（推荐）

告警中心始终调用 `send_msg_with_channel`。当 channel type 为 NATS 时：

- `send_msg_with_channel` 负责校验 `content`
- `send_nats_message` 负责从 channel config 注入 `bot_id`、`node_id`
- OpsPilot 新增专用 NATS 消费方法，接收 enrichment 后的参数并统一转成 workflow `flow_input`

**优点**

- 告警中心只需要关心稳定的 `content` 契约
- 路由关系收敛在 system_mgmt channel config，不泄露到告警中心
- OpsPilot 只处理一种标准化后的上下文，后续节点复用成本最低

**缺点**

- 需要同时改 system_mgmt、opspilot、web studio 三处

### 方案 B：由告警中心直接拼完整 OpsPilot 请求

告警中心直接把 `bot_id`、`node_id` 和完整执行参数一起放进 NATS payload，system_mgmt 只负责转发。

**缺点**

- 告警中心需要知道 OpsPilot workflow 路由细节
- channel config 价值下降
- 后续换 bot 或换入口节点时，需要改告警中心而不是只改通道配置

### 方案 C：只做透传，不做上下文标准化

system_mgmt 仅把 `content + bot_id + node_id` 转发给 OpsPilot，下游每个节点自行解析 `team` 和 `user_ids`。

**缺点**

- 解析逻辑会散落到多个节点
- 个人记忆、组织记忆、通知节点会重复做同样的事情
- 后续 payload 一旦变化，影响面会很大

**结论**

采用 **方案 A**：system_mgmt 做路由补齐，OpsPilot 做上下文标准化。

## 五、上游接口契约

### 5.1 告警中心 -> system_mgmt

告警中心调用：

```python
send_msg_with_channel(channel_id, title, content, receivers, attachments=None)
```

其中 NATS 分支约束如下：

- `title` 在 NATS 分支不参与实际业务逻辑，仅保留接口兼容性
- `receivers` 在 NATS 分支不作为真实干系人来源，仅保留接口兼容性
- NATS 的真实输入以 `content` 为准

`content` 固定为：

```json
{
  "message": "告警内容摘要或提示词",
  "team": 2,
  "user_ids": ["alice", "bob"]
}
```

字段语义：

- `message`：传给 workflow 的核心输入消息
- `team`：组织 ID（**单个整数**，仅允许一个组织）
- `user_ids`：通知人用户名列表，也是本次 session 的干系人列表

### 5.2 system_mgmt NATS 分支校验规则

当 `send_msg_with_channel` 识别到 channel type 为 NATS 时，应新增如下校验：

- `content` 必须是 dict；如果是字符串，需要先反序列化再校验
- `message` 必须是非空字符串
- `team` 必须是**单个整数**（兼容单元素列表，多元素/空/非数字直接拒绝）
- `user_ids` 必须是 list，元素按 string 归一化，空值丢弃
- 校验失败时直接返回 `{"result": False, "message": "..."}`
- 不允许静默把 `receivers` 合并进 `user_ids`

这样可以确保告警中心传入的数据在 system_mgmt 就具备稳定结构。

## 六、NATS Channel Config 设计

当前 NATS channel config 已有：

- `namespace`
- `method_name`
- `timeout`

本次新增：

- `bot_id`
- `node_id`

因此 `send_nats_message` 实际发往目标方法的 kwargs 应变成：

```json
{
  "message": "xxx",
  "team": 2,
  "user_ids": ["alice", "bob"],
  "bot_id": 12,
  "node_id": "nats-entry-1"
}
```

这里的设计重点是：

- `message/team/user_ids` 来自告警中心 `content`
- `bot_id/node_id` 来自 channel config

> **修订**：`bot_id`/`node_id` 不再由用户手填，而是由 OpsPilot 发布时自动写入 channel config（见顶部「方案修订」第 2 条）。告警中心仍只需关心 `content`，路由仍收敛在 channel config。

## 七、OpsPilot NATS 入口设计

OpsPilot 侧新增专用 NATS 消费方法，建议放在 `server/apps/opspilot/nats_api.py` 中，并由 NATS channel 的 `namespace + method_name` 指向它。

该方法职责如下：

1. 校验 `bot_id`、`node_id`、`message`、`team`、`user_ids`
2. 查找目标 `Bot` 与 `BotWorkFlow`
3. 校验 `node_id` 是否存在，且对应节点类型必须为 `nats`
4. 创建 workflow engine，指定 `entry_type="nats"`
5. 构建标准化后的 `input_data`
6. 执行 workflow

同时需要补充：

- `WorkFlowExecuteType.NATS`
- workflow node registry 注册 `nats -> EntryNode`
- web studio 新增 `nats` 触发节点

`nats` 节点本身只承担入口职责，不承担业务逻辑，行为上与其他 trigger node 保持一致。

## 八、Workflow 上下文透传

NATS 入口收到参数后，应只在入口处做一次必要归一化，并把结果直接写入 `flow_input`。

这里不再额外引入 `session_stakeholders`、`current_organization_id`、`current_organization_ids`、`authorized_team_ids` 这类别名字段，避免设计出节点实际上不会消费的上下文。

推荐写入结果：

```json
{
  "last_message": "告警内容摘要",
  "message": "告警内容摘要",
  "entry_type": "nats",
  "trigger_type": "nats",
  "bot_id": 12,
  "node_id": "nats-entry-1",
  "team": 2,
  "user_ids": ["alice", "bob"],
  "is_third_party": true
}
```

归一化规则：

- `message`：保证为非空字符串
- `team`：保证为**单个整数**
- `user_ids`：保证为去空后的 string 列表
- `bot_id/node_id`：来自 channel config
- `entry_type`：固定为 `nats`

原则是：**哪些字段会被节点直接使用，就保留哪些字段；不会直接使用的别名不引入。**

## 九、下游节点语义调整

### 9.1 个人记忆

NATS 触发的 workflow 中，多干系人是平级关系，不再定义“主干系人”。

因此个人记忆语义调整为：

1. 当 `flow_input.user_ids` 非空时，个人记忆写入节点应按干系人逐个写入
2. 例如传入 3 个干系人，则同一条 workflow 产生的个人记忆需要分别写入这 3 个用户各自的个人记忆
3. 当 `flow_input.user_ids` 非空时，个人记忆读取节点也应按干系人逐个读取，并将结果聚合后再传给下游
4. 只有在 `flow_input.user_ids` 为空时，才回退到旧逻辑

这样可以保证告警中心传来的多个通知人都拥有各自独立的个人记忆，而不是只围绕某一个默认用户展开。

### 9.2 组织记忆

NATS 触发的 workflow 中，组织记忆节点直接消费 `flow_input.team`。

首版建议：

1. `flow_input.team` 非空时，直接用该整数作为本次执行的当前组织 `organization_id`
2. `flow_input.team` 为空时，回退旧逻辑（如记忆空间默认 `memory_space.team[0]`）

这样组织记忆就能优先使用告警中心传入的组织上下文，而不是只依赖记忆空间静态配置。

### 9.3 邮件/通知节点

需求里明确希望后续邮件发送等节点能复用干系人，因此通知类节点应支持从标准化上下文读取收件人，而不是要求每个告警 workflow 重新手填一份静态 recipients。

推荐首版能力：

- 保留现有静态 recipients 配置，兼容老 workflow
- 新增“从 session 干系人取收件人”的解析能力
- 解析来源统一读取 `flow_input.user_ids`

这样做的重点不是新增一条告警专用通知链路，而是让通知节点复用统一上下文。

### 9.4 组织权限与资源访问

后续需要组织上下文的工具或节点，应统一读取 `flow_input.team`。

首版约定：

- `team` 为单个整数，即当前组织（一次执行仅一个组织）
- 如果某个节点依赖组织上下文，但本次触发没有带有效 `team`，应显式失败，不做静默降级。

## 十、错误处理

### 10.1 system_mgmt 层

- NATS channel config 缺少 `namespace`、`method_name`、`bot_id`、`node_id` 时，直接拒绝发送
- `content` 结构非法时，直接拒绝发送
- 不允许自动把 `receivers` 补成 `user_ids`

### 10.2 OpsPilot NATS 入口

- `bot_id` 不存在：拒绝执行
- `node_id` 不存在：拒绝执行
- `node_id` 对应节点不是 `nats` 类型：拒绝执行
- `team` 为空：只有在后续真正访问组织记忆或组织权限节点时，才明确报错
- `user_ids` 为空：只有在后续真正访问个人记忆或干系人通知节点时，才明确报错

### 10.3 可观测性

执行记录和日志里建议保留以下摘要信息：

- `execution_id`
- `entry_type=nats`
- `bot_id`
- `node_id`
- stakeholder 数量
- 当前组织 ID

日志中不应直接打印完整敏感内容，只保留必要摘要。

## 十一、前端 Studio 影响

Studio 需要新增 `nats` 触发节点，和现有 `celery/restful/openai/...` 同级。

这个节点的配置应尽量轻量，因为真正的路由信息在 system_mgmt channel config 中：

- 不在 Studio 里配置 `namespace`
- 不在 Studio 里配置 `method_name`
- 不在 Studio 里配置 `bot_id/node_id`
- 仅保留与入口节点一致的基础展示与输入输出参数配置

这样可以让 workflow 画布只关注流程编排，不承载通道路由职责。

> **修订**：
> - nats 触发节点多次拖出时，前端自动对 label 去重（`NATS触发`、`NATS触发 1`…），保证「发布」时派生的通道名不冲突。
> - 对应的 system_mgmt NATS 通道在「发布(上线)」时由后端自动创建/对账，用户无需也无法在通道管理里手动维护这些通道（见顶部「方案修订」第 2、3 条）。

## 十二、兼容性

- 现有 email、企微机器人、自定义 webhook 等通道行为保持不变
- 现有非 OpsPilot 的 NATS channel 仍可复用原有 `namespace/method_name` 机制，只是其 payload 仍需满足目标方法自己的契约
- 现有没有 `nats` 节点的 OpsPilot workflow 不受影响
- 现有 memory workflow 在没有新 NATS 上下文时，继续走旧逻辑兜底

## 十三、建议落地顺序

1. 扩展 NATS channel config，新增 `bot_id`、`node_id`
2. 收紧 `send_msg_with_channel` 的 NATS payload 校验
3. 改造 `send_nats_message`，把 config 中的 `bot_id/node_id` 注入 kwargs
4. 新增 OpsPilot NATS 消费入口
5. 新增 `WorkFlowExecuteType.NATS` 与 workflow node registry 支持
6. 把 NATS payload 标准化写入 `flow_input`
7. 调整个人记忆、组织记忆、通知收件人解析逻辑，消费统一上下文
8. 新增 web studio 的 `nats` 触发节点及展示支持

## 十四、最终建议

最终采用：

- **system_mgmt 作为统一集成边界**
- **OpsPilot 作为上下文标准化边界**

对应含义是：

- 告警中心只知道 `send_msg_with_channel`
- NATS 路由留在 channel config，通过 `namespace/method_name/bot_id/node_id` 控制
- OpsPilot 只接收一份 enrichment 后的标准参数，并在入口处一次性标准化
- 后续记忆、通知、权限相关逻辑统一复用这些标准字段

这个方案的优点是：

- 对告警中心侵入最小
- 路由职责清晰
- 下游节点复用成本低
- 后续如果再扩展告警上下文能力，仍然可以沿用这套标准化入口
