# Historical Superpowers change: 2026-06-18-opspilot-chatflow-reply-to-waiting-agent

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## specs: 2026-06-18-opspilot-chatflow-reply-to-waiting-agent-design.md

- **日期**: 2026-06-18
- **状态**: 已实现（worktree，未提交）；web/openai 入口已落地，第三方渠道顺延（见 §11）
- **模块**: opspilot（server 后端 + web 前端）
- **关联代码**: `server/apps/opspilot/`、`web/src/app/opspilot/components/custom-chat-sse/`

> **实现细化（as-built，2026-06-18）**——实现期相对原设计的两处必要细化：
> 1. **`trigger_type` 三态**：`_ask_user` 原把 `trigger_type` 硬编码为 `interactive`；若不修，定时任务在"无限等待"下会**永久挂死**。现读真实值并三分支：`interactive` 无限等待 / `unattended` 立即默认 / **`third_party`（企微/钉钉）保留有界等待**（webhook 不能悬挂）。详见 §5.3。
> 2. **前端 loading 机制**：`user_choice_request` 事件 handler 返回 `false`（`aguiMessageHandler.ts`），等待期 `loading` 仍为 `true`→`Sender` 显示"停止"键、主输入框无法提交。故用 `loading={loading && !pendingChoice}` 让等待期可发送、答完自动恢复"停止"键（**恰好保留 D7 中断**）。详见 §6.3。

---

## 1. 背景与问题

在 opspilot 的 ChatFlow（可视化工作流）里可以编排多个智能体节点（A → B → …）。当问题流转到智能体 B、B 调用工具且**需要用户介入选择/判断**时，前端会弹出"选择框"（`request_user_choice`）。

**现象**：如果用户**不点选择框**，而是直接在下方主对话框输入回复，这条回复会被当成一次全新的对话——工作流**从入口节点重新跑**，于是又回到智能体 A，而不是把答案交给正在等待的 B。

### 1.1 根因

系统里存在两条**互不相通**的通道：

**① 选择框通道（正确，能到 B）**
- B 的 LLM 调用 `request_user_choice` 工具（`server/apps/opspilot/metis/llm/chain/node.py:929`、`_ask_user` 在 `:942`）。
- 发出 `user_choice_request` 自定义事件（含 `execution_id` / `node_id=B` / `choice_id`）→ 前端渲染选择框（`node.py:1005`）。
- 调用 `await wait_for_choice(...)`（`node.py:1011`），**在原 SSE 流的协程里**轮询 Django cache `choice:{execution_id}:{node_id}:{choice_id}`（`server/apps/opspilot/utils/user_choice.py:62`）。
- 用户点选择框 → `submit_choice`（`server/apps/opspilot/views.py:854`）把答案写进同一 cache key → B 的轮询命中，在原流继续输出。

**② 对话框通道（错误，跑回 A）**
- 主对话框输入走 `execute_chat_flow`（`server/apps/opspilot/views.py:621`）。
- 每次都 `create_chat_flow_engine(...)` 生成一个**全新 `execution_id`**（`views.py:680`、`views.py:694`），从入口节点开始重跑整张图 → 先到 A。

**一句话**：对话框输入永远走"新建一次执行、从入口重跑"，后端**没有"该 session 当前有一个在等回答的 B"这个概念**去拦截它；而选择框通道靠 `(execution_id, node_id, choice_id)` 点对点喂给还活着的 B。

### 1.2 前端放大了问题

更糟的是，用户在 B 等待时于主对话框发送新消息，会触发 `stopSSEConnection()`（`web/src/app/opspilot/components/custom-chat-sse/hooks/useSSEStream.ts:64`），它做了两件**致命**的事：

1. `abortControllerRef.abort()` —— 掐断原始 SSE 流（B 续跑无处输出）；
2. POST `interrupt_chat_flow_execution` —— 把 execution#1 标记为 INTERRUPTED（B 在引擎层被主动中断）。

随后才 POST `execute_chat_flow` 开新流、新 execution、从入口跑到 A。所以不是"被动走错门"，而是前端**先把 B 杀了再新建执行**。⇒ **仅改后端不够，前端必须配合。**

### 1.3 已具备的能力

"把对话框自由文本喂给 B"这条链路前后端**都已具备**，缺的只是"识别 + 改道 + 别杀原流"：

- 后端 `request_user_choice` 支持 `question_type="text"` 自由输入，把 `selected[0]` 当原始用户输入喂回 LLM（`node.py:1041`）。
- 前端 `UserChoiceCard` 本就有自由文本输入框，连 single/multi_select 模式都带"或者自行输入"提示（`web/src/app/opspilot/components/custom-chat-sse/UserChoiceCard.tsx:229`、`:309`），提交走 `submit_choice` 的 `selected:[文本]`（`UserChoiceCard.tsx:44`）。

---

## 2. 目标与非目标

### 2.1 目标
1. 当某 session 存在"正在等待用户输入的智能体 B"时，用户在主对话框的回复应**直接交给 B**（在原流续跑），**不经过 A 及其他节点、不新建执行**。
2. 跨入口一致：web、企业微信、钉钉、OpenAI API 任一入口的消息进来，后端都能正确判断"是否在回答 B"。
3. interactive（真人对话）场景下，B 对用户输入**无限长等待**（去掉 120s 超时），直到用户应答或主动中断。

### 2.2 非目标（明确划界）
1. **不**引入 LangGraph checkpointer / 跨进程持久化恢复（讨论中的 option 3，已排除）。⇒ 刷新页面、断线、进程重启**仍会丢失**正在等待的 B（与 Hermes 的真实姿态一致，见 §7）。
2. **不**做"是否在回答 B"的语义判别——存在待回答的 B 时，下一条对话框消息**无条件**当作 B 的答案（用户已选定）。
3. **不**让 approval（危险操作审批 approve/reject）接管对话框；本期拦截只覆盖 `request_user_choice`。approval 维持选择框专用。
4. **不**开放等待时长配置（暂不开放）。
5. **不**为 interactive 增加"另起话题"的逃生口（无条件给 B）。退出靠"中断"。

---

## 3. 关键决策与依据

| # | 决策 | 依据 |
|---|---|---|
| D1 | **服务端会话级拦截**（依赖 B 进程存活，不做跨重启持久化） | 用户选定；与 Hermes 生产实现的真实姿态一致（§7） |
| D2 | **无条件给 B**（不语义判别） | 用户选定；简单可预期 |
| D3 | **前后端一起做** | 前端会 abort+interrupt 原流，仅后端不够 |
| D4 | **前端命中 pending 时复用 `submit_choice`**；后端拦截作为跨渠道安全网 | 复用成熟路径、改动最小；后端保证非 web 渠道与异常客户端的正确性 |
| D5 | **interactive 无限长等待**，去掉 120s 超时与"超时回退默认"；**不开放配置** | 用户指定 |
| D6 | **保留 `unattended` 立即默认**（定时/无人值守不长等待） | 推荐保留：否则 headless 工作流永久挂死等一个不会来的人 |
| D7 | **interrupt 作为唯一的非应答退出口** | 去掉超时后，中断是唯一的"放弃"手段 |
| D8 | **pending 注册表用自续租约**（非固定 TTL） | 无超时下不能猜 TTL；租约在 B 停止轮询后 ~LEASE_TTL 内自动回收 |

---

## 4. 架构总览

```
现状（坏）— 用户在 B 等待时于主对话框回复：
  前端 onSubmit ──► stopSSEConnection(): abort 原流 + POST interrupt(exec#1) ──► B 被杀
            └─► POST execute_chat_flow ──► 新 exec#2 ──► 入口 ──► A ──► …（跑回 A）

方案 — 同样动作：
  前端 onSubmit ──► 检测到 last bot msg 有 pending 选择
            └─► 复用 submit_choice(exec#1, node_B, choice_id, selected=[文本])
                 · 不 abort、不 interrupt，原流保持打开
                 · B 的 wait_for_choice 轮询命中 ──► B 在原流续跑（不经过 A）
  ┌─ 后端安全网（跨渠道，单一拦截 choke point）──────────────────────┐
  │ 任意入口在创建引擎之前先查 pending_hitl:{bot}:{session}            │
  │   命中 ─► submit_user_choice(...) + clear_pending + 返回 ack（不建执行） │
  │   未命中 ─► 现有逻辑（新建执行）                                   │
  └────────────────────────────────────────────────────────────────┘
```

设计参照 Hermes 的 `clarify`：**会话级 pending 注册表 + 入站单一 choke point 在"新一轮开始前"拦截并 resolve**（详见 §7）。

---

## 5. 详细设计 — 后端（server）

### 5.1 新增模块：pending HITL 注册表（自续租约）

新文件 `server/apps/opspilot/utils/pending_hitl.py`，仿 `user_choice.py` / `execution_interrupt.py` 的 cache 风格。

- **Key**：`pending_hitl:{bot_id}:{session_id}`
- **Value**：`{kind:"choice", execution_id, node_id, choice_id, created_at}`
- **租约 TTL**：模块内常量 `LEASE_TTL = 30`（秒）——**非用户配置**。等待循环每轮续写（heartbeat），B 活着就一直新鲜；B 停止轮询后 ~30s 自动过期。
- **API**：
  - `register_pending(bot_id, session_id, *, kind, execution_id, node_id, choice_id)` —— 写/续租（`cache.set(key, payload, LEASE_TTL)`）。
  - `get_pending(bot_id, session_id) -> dict | None` —— 入口拦截查询。
  - `clear_pending(bot_id, session_id)` —— 显式清理。

> 选 cache 而非 DB：本方案恢复本就依赖 B 进程存活，cache 语义足够，与现有 HITL（`user_choice` / `execution_interrupt`）一致。

### 5.2 注册/清理生命周期（在 B 真正等待的边界）

在 `node.py` 的 `_ask_user`（`:942`）里：

1. 发出 `user_choice_request` 后、进入等待前 `register_pending(...)`。
2. 进入改造后的 `wait_for_choice`，**每轮轮询续租**（heartbeat）。
3. `finally` 中 `clear_pending(...)`（无论应答/中断/异常），不等租约过期。

**所需上下文**：`_ask_user` 从 `config["configurable"]` 取 `execution_id` / `node_id` / `trigger_type` / `session_id` / `bot_id`。

> **as-built**：核实发现 `session_id` / `bot_id` 原**不在** configurable。已贯通：[agent.py](../../../server/apps/opspilot/utils/chat_flow_utils/nodes/agent/agent.py) `_build_llm_params` 把 `flow_input` 的 `session_id` / `bot_id` 加入 llm_params → [chat_service.py](../../../server/apps/opspilot/services/chat_service.py) `_process_tools_and_extra_config` 与 `format_chat_server_kwargs` 两处把它们搬进 `extra_config` → 经 `**extra_config` 展开进 `configurable`（`graph.py:308`）。`_ask_user` 直接从已挂载的 `_configurable` 读。

### 5.3 `wait_for_choice` 改造（`server/apps/opspilot/utils/user_choice.py:62`）

**按 `trigger_type` 三分支**（as-built）：

- `unattended`（定时/无人值守，D6）：立即用 `default_keys` 返回，**绝不长等待**。
- `interactive`（真人对话，D5）：**无限等待**（`deadline=None`），删除"超时→默认"回退。
- `third_party`（企微/钉钉等 webhook）：**保留有界等待**（`deadline=now+timeout_seconds`），超时回退默认——webhook 同步请求不能被无限悬挂。

统一为单循环（`deadline=None` 即无限）：

```python
if trigger_type == "unattended":
    return {"selected": default_keys or [...], "source": "auto"}

deadline = None if trigger_type == "interactive" else time.monotonic() + timeout_seconds
while deadline is None or time.monotonic() < deadline:
    result = get_user_choice(execution_id, node_id, choice_id)
    if result:
        clear_user_choice(execution_id, node_id, choice_id)
        return {"selected": result["selected"], "source": "user"}
    if execution_id and await is_interrupt_requested_async(execution_id):   # D7：中断退出
        return {"selected": [], "source": "interrupted"}
    if bot_id and session_id:                                              # D8：续租
        register_pending(bot_id, session_id, execution_id=execution_id, node_id=node_id, choice_id=choice_id)
    await asyncio.sleep(poll_interval)                                     # 沿用 1s
# 仅有界(third_party)会走到这：超时 → 默认
return {"selected": default_keys or [...], "source": "timeout"}
```

- `wait_for_choice` 增加可选参数 `bot_id` / `session_id`（向后兼容；缺省则不续租）。
- **关键修复（as-built）**：`_ask_user` 原**硬编码** `trigger_type="interactive"` 调用 `wait_for_choice`。若保留硬编码 + interactive 无限，则 `entry_type ∈ (celery, test)` 的定时/测试执行会**永久挂死**。现 `_ask_user` 改为从 `configurable.get("trigger_type", "interactive")` 读真实值并透传。
- `node.py` 调用处去掉 `timeout_seconds=120`；`user_choice_request` 事件 payload 的 `timeout_seconds` 置 `0`（表"无限"，供前端拆倒计时）。

`trigger_type` 取值来自 [agent.py](../../../server/apps/opspilot/utils/chat_flow_utils/nodes/agent/agent.py) `_resolve_trigger_type`（`celery/test`→`unattended`；`enterprise_wechat/dingtalk/wechat_official`→`third_party`；其余→`interactive`）。`is_interrupt_requested_async` 见 `execution_interrupt.py:119`。

### 5.4 入口拦截（D4 安全网 + 跨渠道）

抽公共 helper（如 `try_deliver_to_pending(bot_id, session_id, message) -> dict | None`）：

```python
p = get_pending(bot_id, session_id)
if p:   # cache 命中即视为"新鲜"（租约过期则自动 None）
    submit_user_choice(p["execution_id"], p["node_id"], p["choice_id"], selected=[message])
    clear_pending(bot_id, session_id)
    return {"delivered_to_pending": True, **p}
return None
```

接入点（创建引擎之前）：
- **as-built 已接入** `execute_chat_flow`（`views.py:621`，`try` 块顶部、`not is_test and session_id and message` 时）——命中则返回 `JsonResponse({"result": True, "data": {delivered_to_pending, execution_id, node_id, choice_id}})`，**不建执行、不开新流**；未命中走现有逻辑。这覆盖 web_chat / agui / embedded / mobile / **openai**（均经此入口，`views.py:717` 的 `stream_node_types`）。
- **企微/钉钉顺延**（见 §11）：它们走 `base_chat_flow_utils.execute_chatflow_with_message`，**`input_data` 无 `session_id`** 且用同步 `engine.execute()`（webhook 模型）。需先为这些渠道引入稳定 session_id 才能登记/命中 pending，故本期未接 helper。

**鉴权**：`execute_chat_flow` 已校验 token 并按 team 作用域解析 bot；pending 按 `(bot_id, session_id)` 键、且只由该 bot 自身运行中的执行写入，作用域天然内聚。等价于 `submit_choice` 的安全级别（后者另按 `execution_id` 校验 team 归属）。

### 5.5 退出路径（超时已去，这是全部出口）

1. **应答**：选择框 or 对话框→`submit_choice` → cache 命中 → B 续跑。
2. **中断**：web "停止" → `interrupt_chat_flow_execution`（`views.py:736`）→ `wait_for_choice` 轮询查到中断 → break；引擎中断逻辑（`engine.sse_execute` 的 `_check_interrupt_requested_async`，`engine.py:119`）正常收尾。
3. **客户端断连**：SSE 生成器取消 → 等待协程随之取消 + 租约 ~LEASE_TTL 过期回收。
   - **实现期校验**：确认 ASGI 断连能取消处于 `wait_for_choice` 轮询中的协程（避免僵尸协程持续续租）。`asyncio.sleep` 可被取消，正常情况下断连会传播 `CancelledError`；需在测试中覆盖。

---

## 6. 详细设计 — 前端（web）

### 6.1 发送时检测 pending（`custom-chat-sse/index.tsx` 的 `handleSend` / `useSendMessage`）
取最后一条 bot 消息的 `userChoiceRequests`（类型见 `web/src/app/opspilot/types/global.ts:80`、`:128`），若存在 `status==='pending'` 项 → 进入"投递给 B"分支。

### 6.2 复用 `submit_choice`（D4 主路径）
该分支**不**调用普通发送。**as-built**：抽出共享函数 `submitUserChoice.ts` 的 `postUserChoice(token, {...})`，由 `UserChoiceCard` 与 `index.tsx` 主输入框**共用**（去重）。`handleSend` 命中 `pendingChoice` 时 POST `submit_choice` `{execution_id, node_id, choice_id, selected:[文本]}`，并把该 choice 标记 `submitted`。
**不另插 user 气泡**——与"点选择框提交"一致，答案随 B 续跑在 `request_user_choice` 工具结果面板内呈现（卡片 `isCompleted` 后 `return null`），避免在仍在增长的 bot 气泡下方插入用户气泡造成时序错乱。

### 6.3 绝不破坏原流（关键）+ loading 机制（as-built）
该分支**绝不**触发 `stopSSEConnection()`（`useSSEStream.ts:64`）——不 abort、不发 interrupt。B 续跑沿用现有"原流继续渲染到当前 bot 消息"的逻辑。

**as-built（关键机制）**：`user_choice_request` 在 `aguiMessageHandler.handle` 的 CUSTOM 分支返回 `false`（`aguiMessageHandler.ts:841`）→ 等待期 `loading` 仍为 `true` → `Sender`（`@ant-design/x`）在 `loading` 下把发送键变为"停止"（`onCancel=stopSSEConnection`），Enter 不提交。所以仅靠 `handleSend` 分支不够，必须让等待期的 `Sender` 可交互：

- `Sender` 的 `loading` 改为 `loading={loading && !pendingChoice}`：等待期（`pendingChoice` 非空）显示**发送键**，用户可在主输入框提交 → `handleSend` 命中 pending 分支。
- 答完后 choice 标记 `submitted` → `pendingChoice` 变空 → `Sender` 恢复 `loading`（流仍开、B 续跑中）→ 重新显示"停止"键，**D7 中断在 B 生成期可用**。
- 即：你要回答时给"发送"，agent 工作时给"停止"；等待期不提供"放弃"按钮，与 D2"无条件给 B"一致。

### 6.4 拆倒计时（配合 D5 无限等待）
`UserChoiceCard` 现有可见倒计时（`UserChoiceCard.tsx:20` 的 `remainingSeconds`、`:35` 的 `setInterval`、`:334` 的 `{remainingSeconds}s`、`:101` 的 `isTimedOut`）。引入 `noTimeout = !request.timeout_seconds || request.timeout_seconds <= 0`：不渲染倒计时、跳过 `setInterval`、`isTimedOut` 恒 `false`。

> **as-built 修复的坑**：原 `remainingSeconds` 初值 = `max(0, timeout_seconds - elapsed)`，当 `timeout_seconds=0` 时为 `0` → `isTimedOut = 0<=0 && pending = true` → `isCompleted=true` → 卡片 `return null` **直接消失**。`noTimeout` 守卫修复此问题。

### 6.5 UX 提示（配合 D2 无条件给 B）
pending 时主输入框 placeholder 改为"回复上面的问题…"之类，避免用户误以为在另起话题。

---

## 7. 与 Hermes-Agent 的对照（设计验证）

Hermes（Nous Research）的 `clarify`（问用户）机制与本方案高度同构，验证了取舍合理性。

| 维度 | Hermes | opspilot 现状 | 本方案 |
|---|---|---|---|
| 问用户的工具 | `clarify`（≤4 选项/开放式 + Other） | `request_user_choice`（同款 + 或自行输入） | 不动 |
| 阻塞方式 | agent 线程 `Event.wait` 1s 切片 | agent 协程 `wait_for_choice` 1s 轮询 cache | 不动 |
| pending 注册表 | `_session_index[session_key]`（`tools/clarify_gateway.py:165`） | 无 session 关联 | 新增 `pending_hitl:{bot}:{session}` |
| 回复路由 | 入站单一 choke point 拦截→`resolve_gateway_clarify`→不另起轮（`gateway/run.py:6954`） | 主输入必新建执行→A | 入口拦截 + 前端复用 submit_choice |
| 会话边界清理 | `clear_session`（`tools/clarify_gateway.py:203`） | 无 | `clear_pending`（应答/中断/结束） |
| 等待超时 | 600s 可配（`get_clarify_timeout`） | 固定 120s | interactive **无限** / unattended 立即默认 / third_party 有界回退 |
| 跨重启持久恢复 | ❌（等待本身为进程内 `threading.Event`） | ❌ | ❌（D1） |

**深层结论**：Hermes 压根没有"跑回 A"问题，因为它**没有"每条消息从入口重建 DAG"** 的模型——它是一条可恢复对话循环 over 持久历史，`clarify` 只是循环里一次进程内阻塞工具调用，网关在唯一入口把回复拦下直接 resolve。opspilot 的 bug 正是 LangGraph"从入口重跑整张图"模型生出来的。本方案在现有引擎上 bolt-on，拿到同样的用户可见行为；真正"Hermes 同款"的彻底解法即 option 3（checkpointer + 单条可恢复循环），已排除。

从 Hermes 折入本设计的 4 点强化：单一拦截 choke point（§5.4）、会话边界显式清理（§5.2/§5.5）、等待时长策略（§5.3，本期取无限）、`resolve`/拦截幂等与陈旧回退（§5.4，租约过期即视为无 pending → 正常新建执行）。

---

## 8. 异常与边界

- **pending 但 B 已中断/原流已死**：B 停止续租 → 租约 ~30s 过期 → 入口拦截 `get_pending` 返回 None → 正常新建执行，不吞消息。前端：若原流已关闭（loading=false / choice 非 pending）走正常发送。
- **同 session 并发两个 pending**（并行 agent / 并行节点）：v1 假设单 session 至多一个 pending（同 key 后写覆盖前写）。并行多智能体属边界场景，文档标注，不在 v1 兜全。
- **用户同时点选择框又打字**：两次写同一 choice key，`wait_for_choice` 读到即 `clear`，第二次 no-op。安全。
- **approval（危险操作）**：自由文本不是干净的 approve/reject，本期拦截只覆盖 `request_user_choice`；approval 维持选择框专用。
- **session_id 缺失**：无法按 session 建关联 → 回退现有行为（不拦截）。文档列为前置条件。
- **跨渠道（企微/钉钉）**：**本期未接入**（见 §5.4 / §11）——这些入口 `input_data` 无 `session_id` 且用同步 `engine.execute()`（webhook 模型），且受"原 webhook 请求存活"更强约束。`third_party` 在 `wait_for_choice` 已是有界等待，不会悬挂。
- **"无限"受部署层制约**：SSE 路径无 300s 硬超时（`execution_timeout=300` 仅用于非流式 `execute()`，`engine.py:1113`）；实际上限取决于 Uvicorn/Nginx/Ingress 的 idle/read timeout。要让长等待名副其实，**可能需调部署层代理超时（不在本设计代码内，部署文档标注）**。长等待期间 `WorkFlowTaskResult` 持续 RUNNING 并占一个 ASGI 连接，废弃会话靠"中断/断连/租约"回收。

---

## 9. 测试计划

遵循 `server/docs/testing-guide.md`（分层 `_pure` / `_service` / `_views`）。

**后端**
- `_pure`：`pending_hitl` 注册表 register/get/clear、租约过期（TTL 到期后 `get_pending` 返回 None）。
- `_service`：`wait_for_choice` interactive —— (a) 写入答案后命中返回 `source="user"`；(b) 置中断标志后返回 `source="interrupted"`；(c) 轮询期间持续续租；(d) **不再**因时间流逝回退 default。`unattended` 立即返回 default 不变。
- `_views`：`execute_chat_flow` 拦截 —— pending 命中 → 写 choice cache + 返回 `delivered_to_pending` ack + **不新增 `WorkFlowTaskResult`**；未命中 → 正常执行；租约过期 → 回退正常执行。
- 复用既有 `server/apps/opspilot/tests/react_agent/cases/test_user_choice.py` 风格覆盖 `_ask_user` 的 register/clear 生命周期。
- 断连取消：覆盖"等待中协程被取消 → 停止续租 → 租约过期"。

**前端**（按团队约定走 **Storybook**，不启 dev server）
- `UserChoiceCard`：`timeout_seconds=0` 时不渲染倒计时、不进 `isTimedOut`。
- "pending 时主输入框发送"场景：断言调用 `submit_choice(selected=[文本])`、**未**触发 abort/interrupt、原流保持。

> **as-built 测试状态**：已落地 `test_pending_hitl.py`(6) 与 `test_user_choice_wait.py`(4)，并回归 `test_user_choice.py`(8) + `test_approval.py`(6)，**共 24 通过、零回归**；flake8/isort/black 后端全清，eslint + scoped tsc 前端我方代码零错。**尚未补**：`execute_chat_flow` 拦截的 `_views` 测试、断连取消测试、前端 Storybook 用例——列为后续。worktree 跑后端测试需临时 `.env`（gitignored）。

---

## 10. 影响面与回滚

- 改动文件（as-built）：
  - 后端：`utils/pending_hitl.py`(新)、`utils/user_choice.py`、`metis/llm/chain/node.py`、`services/chat_service.py`、`utils/chat_flow_utils/nodes/agent/agent.py`、`views.py`；测试 `tests/test_pending_hitl.py`(新)、`tests/test_user_choice_wait.py`(新)。
  - 前端：`custom-chat-sse/index.tsx`、`UserChoiceCard.tsx`、`submitUserChoice.ts`(新)。（注：loading 机制改在 `index.tsx` 的 `Sender` prop，**未**改 `useSSEStream.ts`。）
- 向后兼容：`wait_for_choice` 新增参数均可选；`timeout_seconds=0` 对旧前端为"倒计时立即 0→卡片消失"——故**前端需与后端同发布**（见 §6.4）。
- 回滚：恢复 `wait_for_choice` 的 120s 分支 + 移除入口拦截调用即可；`pending_hitl` 模块孤立、可整体下线。

---

## 11. 未来增量（非本期）
- **企微/钉钉接入**：前置——为这些渠道在 `base_chat_flow_utils.execute_chatflow_with_message` 的 `input_data` 引入稳定 `session_id`（如基于 `sender_id`），并贯通到 configurable；之后即可在该入口复用 `try_deliver_to_pending`。注意其同步 webhook 模型 + 平台秒级超时使实时续跑天然受限（`third_party` 已是有界等待）。
- **逃生口**：若将来要支持"不回答 B 而另起话题"，仿 Hermes 的保留前缀模式（`/` 命令不拦，`gateway/run.py:6971`）。
- **持久化精确续跑**：option 3（LangGraph `interrupt()` + checkpointer），可跨刷新/断线/重启从 B 续跑。改动最大，本期不做。
- **approval 文本接管**：把对话框"是/否"映射到 approve/reject。
- **i18n**：`chat.replyToPendingChoice` 暂用 fallback 文案，可补入社区版 locales。

---

## 附：关键代码锚点

opspilot 后端：`utils/pending_hitl.py`(注册表+try_deliver，新) ；`views.py:621`(execute_chat_flow 拦截) / `:854`(submit_choice) / `:736`(interrupt) ；`utils/user_choice.py:62`(wait_for_choice 三态) ；`utils/execution_interrupt.py:119` ；`metis/llm/chain/node.py:942`(_ask_user：读 trigger_type/session/bot + register/clear) ；`services/chat_service.py`(extra_config 贯通 session/bot 两处) ；`utils/chat_flow_utils/nodes/agent/agent.py`(_build_llm_params 加 session/bot) ；`metis/llm/chain/graph.py:308`(extra_config 展开进 configurable)。

opspilot 前端：`custom-chat-sse/submitUserChoice.ts`(共享 postUserChoice，新) ；`index.tsx`(pendingChoice memo / handleSend 投递分支 / Sender `loading && !pendingChoice` + placeholder) ；`UserChoiceCard.tsx`(noTimeout 拆倒计时 + 复用 postUserChoice) ；`aguiMessageHandler.ts:841`(user_choice_request 返回 false→loading 仍 true) ；`hooks/useSSEStream.ts:64`(stopSSEConnection，未改) ；`types/global.ts:80/128`。

Hermes（参照，仓库 `D:\app\github\hermes-agent`）：`tools/clarify_tool.py` ；`tools/clarify_gateway.py:78/103/150/165/203/231` ；`gateway/run.py:6954`(拦截)/`:14962`(callback)。
