# OpsPilot NATS 触发调用指南

> 说明：调用方如何通过 `send_msg_with_channel` 的 **NATS 通道**，最终触达 OpsPilot 的
> `trigger_workflow_by_nats`，启动一条 workflow。重点是**参数如何一层层传递**以及**每个参数的含义**。
> 本文基于 master 现行代码（`apps/system_mgmt/nats_api.py`、`apps/system_mgmt/utils/channel_utils.py`、
> `apps/opspilot/nats_api.py`）。

## 一、整体调用链

```
调用方 (告警中心 / 业务代码)
  │  send_msg_with_channel(channel_id, title, content, receivers)
  ▼
system_mgmt.nats_api.send_msg_with_channel        # 按 channel_type 分发
  │  channel_type == NATS
  │  ├─ method_name ∈ {receive_alert_events}? → 原样透传（不走本指南）
  │  └─ 否则 _normalize_nats_content(content)   # 校验 + 归一化 {message, team, user_ids}
  ▼
channel_utils.send_nats_message(channel_obj, content)
  │  从 channel.config 读取 namespace / method_name / bot_id / node_id / timeout
  │  当 method_name == "trigger_workflow_by_nats" 时，把 bot_id/node_id 注入 payload
  ▼
nats_client.request_sync(namespace, method_name, **payload)   # 经 NATS 路由
  ▼
opspilot.nats_api.trigger_workflow_by_nats(message, team, user_ids, bot_id, node_id)
  │  _normalize_nats_trigger_input(...) 二次校验
  │  按 bot_id 找最新 BotWorkFlow，从 node_id 节点以 entry_type="nats" 启动引擎
  ▼
workflow 执行（message/team/user_ids 落入 flow_input 供下游节点复用）
```

**关键认知：调用方只需要关心 `content`（`message/team/user_ids`）。** 路由用的 `bot_id`/`node_id`
不是调用方传的，而是 OpsPilot 发布 workflow 时自动写进通道 `config`、由 `send_nats_message` 注入的。

---

## 二、前置条件：NATS 触发通道

要触达 `trigger_workflow_by_nats`，必须存在一个 **NATS 类型的 Channel**，其 `config` 形如：

| config 字段 | 含义 | 示例 |
|---|---|---|
| `namespace` | NATS 路由命名空间，需与部署的 `NATS_NAMESPACE` 一致 | `"bklite"` |
| `method_name` | 目标方法名，固定为触发入口 | `"trigger_workflow_by_nats"` |
| `bot_id` | 目标 Bot ID（路由用，**非调用方传**） | `12` |
| `node_id` | workflow 中 `type=="nats"` 入口节点的 id（路由用） | `"nats-1718..."` |
| `timeout` | NATS 请求超时（秒），默认 60 | `60` |
| `source` | OpsPilot 托管标识（只读保护用） | `"opspilot"` |

> 这类通道由 **OpsPilot 在「发布(上线)」workflow 时自动创建/对账**，名称为 `{Bot名} - {nats节点名}`，
> 用户无需也无法在「通知渠道」里手动编辑/删除。调用方只需拿到它的 `channel_id`。

---

## 三、第一层：调用 `send_msg_with_channel`

```python
send_msg_with_channel(channel_id, title, content, receivers, attachments=None)
```

| 参数 | 类型 | 在 NATS 触发场景下的含义 | 是否参与触发逻辑 |
|---|---|---|---|
| `channel_id` | int | 上面那个 NATS 触发通道的 ID | ✅ 必填，决定路由到哪个 bot/node |
| `title` | str | 邮件主题等——**NATS 触发分支不使用** | ❌ 仅接口兼容，传 `""` 即可 |
| `content` | dict / JSON str | **真正的业务入参**，见第四节 | ✅ 核心 |
| `receivers` | list | 收件人 ID/用户名——**NATS 触发分支不使用** | ❌ 仅接口兼容，传 `[]` 即可 |
| `attachments` | list | 附件——仅 email 通道用 | ❌ |

> 注意：`send_msg_with_channel` 的 NATS 分支会先看 `config.method_name`。只有当它**不在**透传白名单
> `RAW_PASSTHROUGH_NATS_METHODS = {"receive_alert_events"}`（告警中心内部直推通道）里时，才会走
> `_normalize_nats_content` 的规范化——`trigger_workflow_by_nats` 正属于这种「走规范化」的情况。

---

## 四、核心：`content` 的三个字段（调用方真正要填的）

`content` 是一个 dict（也可传 JSON 字符串，会先 `json.loads`），经 `_normalize_nats_content` 校验归一化：

```json
{
  "message": "告警/提示词正文",
  "team": 2,
  "user_ids": ["alice", "bob"]
}
```

| 字段 | 类型 | 含义 | 校验/归一化规则 | 下游用途 |
|---|---|---|---|---|
| `message` | str | 传给 workflow 的核心输入消息（告警摘要、RCA 报告、提示词等） | 必须是**非空字符串**，会 `strip()` | 落为 `flow_input.last_message` / `message`，作为入口节点输入 |
| `team` | int | 本次执行的**组织 ID（单个）** | 必须是**单个整数**；兼容单元素列表 `[2]`；多元素/空/非数字 → 拒绝 | 落为 `flow_input.team`，供**组织记忆 / 组织权限**作 `organization_id` |
| `user_ids` | list[str] | 本次的**干系人/通知人用户名列表** | 必须是 list；逐个 `str().strip()`，去空 | 落为 `flow_input.user_ids`：**个人记忆按人各写一条**、通知节点收件人回退 |

校验失败直接返回 `{"result": False, "message": "..."}`，不会发起 NATS 请求。例如：
- `message` 为空 → `NATS content.message must be a non-empty string`
- `team` 传了多个 → `NATS content.team must be a single team id`
- `team` 非数字 → `NATS content.team must be a single integer team id`
- `user_ids` 不是 list → `NATS content.user_ids must be a list`

---

## 五、第二层：`send_nats_message` 注入路由参数

归一化后的 `content`（`{message, team, user_ids}`）进入 `send_nats_message`，它从 **通道 config** 取路由信息并补齐：

- 校验 `namespace`、`method_name` 必填；
- 当 `method_name == "trigger_workflow_by_nats"` 时，要求 `config.bot_id` 和 `config.node_id` 存在，并把它们**合并进 payload**；
- 最终发出：`nats_client.request_sync(namespace, "trigger_workflow_by_nats", _timeout=timeout, _raw=True, **payload)`。

因此**实际投递给 `trigger_workflow_by_nats` 的 kwargs** 是：

```json
{
  "message": "告警/提示词正文",
  "team": 2,
  "user_ids": ["alice", "bob"],
  "bot_id": 12,            // 来自 channel.config，非调用方
  "node_id": "nats-1718…"  // 来自 channel.config，非调用方
}
```

---

## 六、终点：`trigger_workflow_by_nats` 的参数

```python
trigger_workflow_by_nats(message, team, user_ids, bot_id, node_id)
```

| 参数 | 类型 | 含义 | 二次校验（`_normalize_nats_trigger_input`） |
|---|---|---|---|
| `message` | str | workflow 入口消息 | 非空字符串，`strip()` |
| `team` | int | 单个组织 ID | 单个整数（兼容 `[2]`）；非法 → `team must be a single integer team id` |
| `user_ids` | list[str] | 干系人用户名列表 | 必须是 list，逐个去空 |
| `bot_id` | int | 目标 Bot | 可转 int，否则 `bot_id must be an integer` |
| `node_id` | str | workflow 入口节点 id（`type=="nats"`） | 非空字符串，否则 `node_id is required` |

执行逻辑：
1. 按 `bot_id` 取**最新一条** `BotWorkFlow`（`order_by("-id")`）；找不到 → `Bot workflow not found`。
2. `create_chat_flow_engine(workflow, node_id, entry_type="nats")` 从该节点启动。
3. 构造 `flow_input`（即 `input_data`）并执行。

`flow_input` 字段映射：

| flow_input 字段 | 来源 | 说明 |
|---|---|---|
| `last_message` / `message` | `content.message` | 入口节点输入消息 |
| `team` | `content.team` | 单个组织 ID（标量），下游 `organization_id` |
| `user_ids` | `content.user_ids` | 干系人列表 |
| `bot_id` / `node_id` | channel.config | 路由信息 |
| `entry_type` | 固定 `"nats"` | 标识 NATS 触发 |
| `is_third_party` | 固定 `True` | 标识第三方触发 |

返回值：

```json
{
  "result": true,
  "data": { /* workflow 执行结果 */ },
  "entry_type": "nats",
  "execution_id": "……"
}
```

---

## 七、完整调用示例

### 7.1 通过 RPC 封装调用（推荐，告警中心/业务侧）

```python
from apps.rpc.system_mgmt import SystemMgmt

NATS_CHANNEL_ID = 9  # 已建好的 NATS 触发通道（config.method_name == "trigger_workflow_by_nats"）

result = SystemMgmt().send_msg_with_channel(
    channel_id=NATS_CHANNEL_ID,
    title="",                      # NATS 触发分支不使用
    content={
        "message": "【K8S严重告警】payment-gateway OOMKilled，可用副本 2/3",
        "team": 2,                 # 单个组织 ID
        "user_ids": ["alice", "bob"],
    },
    receivers=[],                  # NATS 触发分支不使用
)
# result 即 OpsPilot 返回：
# {"result": True, "data": <workflow结果>, "entry_type": "nats", "execution_id": "..."}
```

### 7.2 本地验证（Django shell，mock 掉真实 NATS）

```python
from unittest.mock import patch
from apps.system_mgmt.models import Channel, ChannelChoices
from apps.system_mgmt.nats_api import send_msg_with_channel

ch = Channel.objects.create(
    name="opspilot-trigger-test", channel_type=ChannelChoices.NATS, team=[2],
    config={
        "namespace": "bklite", "method_name": "trigger_workflow_by_nats",
        "bot_id": 12, "node_id": "nats_entry", "timeout": 60, "source": "opspilot",
    },
)
content = {"message": "测试触发", "team": 2, "user_ids": ["alice", "bob"]}

with patch("apps.system_mgmt.utils.channel_utils.nats_client.request_sync",
           lambda ns, m, _timeout=None, _raw=False, **kw: {"_routed_to": (ns, m), "_payload": kw}):
    print(send_msg_with_channel(ch.id, "", content, []))
# 可看到 payload 里 team=2（标量），并被注入 bot_id=12, node_id="nats_entry"，
# 路由到 ("bklite", "trigger_workflow_by_nats")
```

---

## 八、常见错误对照

| 现象 | 原因 | 排查点 |
|---|---|---|
| `Channel not found` | `channel_id` 不存在 | 通道是否已创建 |
| `NATS content.message must be a non-empty string` | `message` 空 | content.message |
| `NATS content.team must be a single team id` | `team` 传了多个 | team 改为单个整数 |
| `NATS channel config missing bot_id or node_id` | 通道 config 缺路由字段 | workflow 是否已发布（自动建通道） |
| `Bot workflow not found` | `bot_id` 无对应 workflow | config.bot_id 是否正确 |
| 记忆「管理组织」为空 | `team` 未传/无效，落为个人记忆 | content.team 是否为有效整数 |

---

## 九、要点速记

1. 调用方只填 **`content = {message, team, user_ids}`**；`title`/`receivers` 在 NATS 触发分支无效。
2. `team` 是**单个整数**（组织 ID），不是列表。
3. `bot_id`/`node_id` **不是调用方传的**，来自通道 `config`，由 `send_nats_message` 注入。
4. `message→workflow 输入`、`team→组织上下文`、`user_ids→干系人(个人记忆逐人写 + 通知)`。
5. 通道由 OpsPilot 发布时自动创建并只读，调用方只需 `channel_id`。
