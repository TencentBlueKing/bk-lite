# OpsPilot Workflow 对话历史注入设计（方案 A：单一会话历史线）

- 日期：2026-06-22
- 范围：`server/apps/opspilot` 的 Workflow（ChatFlow）执行路径
- 目标读者：后端开发
- 状态：设计已确认，待写实现计划

---

## 1. 背景与问题

OpsPilot 的 Workflow（ChatFlow）是基于有向图的节点编排（入口 / agent / 意图分类 / 条件 / 记忆 等节点）。在 workflow 执行路径里，**LLM 节点拿不到跨轮对话历史**，导致两类问题：

- **问题 A（多轮指代）**：用户先问"广州天气如何？"，bot 答"广州 20–28 度"，再问"深圳呢？"。没有历史时，LLM 不知道"深圳呢"在问天气。
- **问题 B（多 agent 历史）**：一个流程里串了多个 agent（`问题 → agent1 → 答案1 → agent2 → 答案2`）。新一轮问题来时，应该给 agent1 什么历史、给 agent2 什么历史？

### 1.1 根因（已核实）

1. **agent 节点把历史写死成"只有当前这句"**
   [`agent.py:199`](../../../server/apps/opspilot/utils/chat_flow_utils/nodes/agent/agent.py)：
   ```python
   "chat_history": [{"event": "user", "message": final_message}],
   ```
   无论第几轮，LLM 只看到当前这一句。

2. **意图分类节点是同样的 bug，且更严重**
   [`intent_classifier.py:89-91`](../../../server/apps/opspilot/utils/chat_flow_utils/nodes/intent/intent_classifier.py)：同样写死 `chat_history=[{"event":"user","message":message}]`，且 `conversation_window_size=1`。结果"深圳呢"在意图分支流程里是**双重失败**：路由分不对类、被路由到的 agent 也答不了。

3. **历史其实已经在存，只是没读回来**
   `WorkFlowConversationHistory`（[`models/bot_mgmt.py:366`](../../../server/apps/opspilot/models/bot_mgmt.py)）每轮记两条：用户原话（`conversation_role='user'`）+ 系统最终输出（`conversation_role='bot'`）。它在 [`engine.py:1264`](../../../server/apps/opspilot/utils/chat_flow_utils/engine/engine.py) 写入，但只被"会话列表 / 历史查看 / 删除"等 UI 接口读取（`viewsets/chat_application_view.py`、`viewsets/bot_view.py`），**从未读回去拼进 LLM 的 `chat_history`**。

4. **`memory_read` 节点 ≠ 对话历史，不在本设计范围**
   [`memory_read.py`](../../../server/apps/opspilot/utils/chat_flow_utils/nodes/memory/memory_read.py) 读的是"记忆空间"（mem0 / zep / local）的**语义检索**（按 query 相似度 top_k），不是逐轮对话历史，解决不了"深圳呢"这种指代，本设计不动它。

### 1.2 对照：普通（非 workflow）对话路径本来就有历史

普通对话由前端把 `chat_history` 传入，`services/history_service.py::process_chat_history` 按窗口（`conversation_window_size`，默认 10）截断注入。**能力是现成的，只是 workflow 路径没喂给它。**

---

## 2. 目标与非目标

### 目标
- G1：workflow 内的 agent / 意图节点在多轮会话中能拿到**本会话的历史**，使"深圳呢"这类指代可解析。
- G2：历史按节点**有选择地**注入——面向用户原话的节点拿历史，纯加工上游输出的节点不拿（避免污染、控制 token）。
- G3：最小改动，**不动表结构、不动记录逻辑、不动普通对话路径**。

### 非目标
- N1：不做 query 改写 / 指代消解（contextualize / condense）。与 hermes 一致，靠把历史喂给模型、由模型自行理解。
- N2：不做"每个 agent 各留一份独立历史"（即方案 B 的 `节点历史` 模式）。本期只有"单一会话历史线"。
- N3：不改 `memory_read` / 记忆空间。
- N4：不处理定时 / celery 触发的历史（这类本就不记录，见 `WorkFlowConversationHistory` docstring）。

---

## 3. 方案选型

三个方向（详见 brainstorm 过程）：

- **方案 A·单一会话历史线（本设计采用）**：只有一条"用户可见的会话线"（提问 ↔ 最终回答），按固定规则注入。最小改动、不改表。
- 方案 B·每节点可配 `historyMode {none / 会话历史 / 节点历史}`：更灵活，但要动前端节点配置 + 后端记录扩展。
- 方案 C·全量节点历史 + 视图过滤：最灵活但存储重、噪音与隐私难控。

**采用 A 的理由**：问题根因是"历史压根没注入"，而历史数据已存在，A 用最小改动即可覆盖三种真实场景（见 §4.3）。这也正是 hermes 的主线思想——"对话记忆挂在顶层会话层、工人节点默认无状态"——落到 OpsPilot 常驻节点模型上的等价形态。

### 3.1 hermes 参考（验证结论）
- 多轮指代：hermes 每轮把**整条会话的完整消息列表**喂回模型（`hermes_state.py::get_messages_as_conversation`，支持 `include_ancestors` 接回被压缩切出去的父 session），**不做** query 改写。
- 多 agent：`delegate_task` 派生的子 agent **完全无历史**（`skip_memory=True`、`ephemeral_system_prompt=goal+context`、不传 conversation_history），只把摘要结果回灌父级。
- 不可照搬点：hermes 的子 agent 是"一次性动态派生工人"，无历史合理；OpsPilot 的 agent 是"每轮常驻、反复调用"的节点，照搬"无历史"会导致常驻 agent 永远记不住上一轮。故 A 改为"**按是否面向用户原话**决定是否给历史"。

---

## 4. 设计详述

### 4.1 关键概念：同轮数据传递 ≠ 跨轮历史

- **同轮数据传递**：`问题 → agent1 → 答案1 → agent2` 中，答案1 传给 agent2 是**同一轮内**的事，靠现有 `variable_manager` / `inputParams` 完成，已经能用，**不在本设计范围**。
- **跨轮历史**：当**下一轮**问题来时，给某节点注入它**之前若干轮**的会话历史——这才是本设计要新建的东西。

> 重要陷阱：流水线里滚动变量 `last_message` 会被上游输出逐节点覆盖（[`engine.py:906`](../../../server/apps/opspilot/utils/chat_flow_utils/engine/engine.py)）。所以"当前轮用户原话"不能从节点当前输入拿，必须用初始化时保存的原始输入（见 §4.3）。

### 4.2 数据来源：复用 `WorkFlowConversationHistory`，零 schema 改动

这条"单一会话历史线"已经存在：每轮的用户原话 + 系统最终输出，键 `(bot_id, user_id, session_id, execution_id)`。

- 用户那条在节点链执行**之前**写入（[`engine.py:340`](../../../server/apps/opspilot/utils/chat_flow_utils/engine/engine.py) / [`1147`](../../../server/apps/opspilot/utils/chat_flow_utils/engine/engine.py)，均在 `_execute_node_chain` 之前）。
- bot 最终输出那条在流程结束时写入（[`engine.py:1168`](../../../server/apps/opspilot/utils/chat_flow_utils/engine/engine.py)）。

**含义**：节点在执行中读历史时，**当前轮的用户记录已经落库**，因此读取时必须排除当前轮，否则会把当前问题重复拼进去（见 §4.4）。

### 4.3 固定规则：节点"吃的是不是本轮用户原话"

> 一个 agent / 意图节点注入会话历史，**当且仅当它的输入就是本轮用户的原始问题**；若它吃的是上游节点加工过的输出，则不注入。

#### 判定机制
1. 引擎在 `_initialize_variables`（[`engine.py:99-108`](../../../server/apps/opspilot/utils/chat_flow_utils/engine/engine.py)）显式写入两个 `variable_manager` 变量，作为节点判定 + 读历史所需的稳定锚点（后续节点不得改写）：
   - `original_user_message = input_data.get("last_message", "")`——本轮用户原话；
   - `bot_id = self.instance.bot_id`——读历史的过滤键（`flow_input` 里不一定带 bot_id）。
   - （`execution_id` 已在 [`engine.py:106`](../../../server/apps/opspilot/utils/chat_flow_utils/engine/engine.py) 写入，复用。）
2. 节点在构造 LLM 参数前，取其**原始输入**（prompt 拼接之前的 `message = input_data.get(input_key)`），与锚点比较：
   ```
   is_user_turn = bool(anchor) and (raw_input_message == anchor)   # anchor = variable_manager.get_variable("original_user_message")
   ```
   - `True` → 该节点面向用户原话 → 加载并注入会话历史。
   - `False` → 该节点吃的是上游产物（或锚点缺失）→ 维持现状（仅当前这条，不注入历史）。

#### 为什么这条规则正好覆盖三种真实场景
"连线方式"本身就编码了意图：

| 场景 | 连线 | agent1 | agent2 | 结果 |
|---|---|---|---|---|
| 意图分支 | 用户问题 → intent → 分支 agent | 拿历史 | 分支 agent 输入是 `intent_previous_output`＝用户原话（[`engine.py:842-845`](../../../server/apps/opspilot/utils/chat_flow_utils/engine/engine.py)）→ 拿历史 | ✓ 都能答"深圳呢" |
| 流水线·美化 | 用户问题 → agent1 → agent2 | 拿历史 | 输入是答案1（[`engine.py:905-910`](../../../server/apps/opspilot/utils/chat_flow_utils/engine/engine.py)）→ 不拿 | ✓ 美化不被历史污染 |
| 协同·并联 | 用户问题 →（agent1 / agent2）→ 合并 | 拿历史 | 输入是用户原话 → 拿历史 | ✓ 两者共享上下文 |

意图节点本身输入即用户原话 → 始终拿历史（解决路由侧的"深圳呢"）。

#### 已知边界
- **串联式协同**（agent2 接 agent1 输出、但又希望 agent2 带历史）：A 覆盖不了，需把它改成"并联"连法，或留待未来引入节点级开关（即方案 B）。本期文档明确不支持。
- **echo 边界**：若某 agent 的输出恰好与用户原话逐字相同，其下游会被误判为"面向用户原话"而多拿历史。属极少见、低影响（只是多给些历史，非正确性错误），本期接受并记录。

### 4.4 注入与窗口

**读取（新增 helper）**：新增 `server/apps/opspilot/utils/chat_flow_utils/conversation_history.py`，提供两个函数：
```
load_session_history(bot_id, user_id, session_id, exclude_execution_id, cap=50) -> list[dict]   # 读 DB + 格式化
build_node_chat_history(variable_manager, raw_input_message, final_message) -> list[dict]        # 判定是否注入 + 拼当前消息
```
`load_session_history`：
- 查询 `WorkFlowConversationHistory.objects.filter(bot_id=, user_id=, session_id=).exclude(execution_id=current_execution_id).order_by("conversation_time")`。
  - `.exclude(execution_id=...)` **排除当前轮**（每轮 = 一个新 `ChatFlowEngine` = 新 `execution_id`），干净剔除当前问题/未完成回答。
  - `session_id` 为空时直接返回空列表（不做跨会话兜底，避免串话）。
- 把行映射为事件列表：`conversation_role='user' → {"event":"user","message":content}`，`'bot' → {"event":"bot","message":content}`。
- `cap` 只是**DB 层粗截断**（如取最近 `2*window+2` 条，避免会话过长时全表拉取），**不做精确加窗**——精确窗口交给下游统一处理（见下）。

**注入（改两处）**：把写死的 `chat_history` 改为 `历史事件列表 + [{"event":"user","message": 当前 final_message}]`，顺序为时间正序（历史在前、当前在最后）：
- agent 节点：[`agent.py:_build_llm_params`](../../../server/apps/opspilot/utils/chat_flow_utils/nodes/agent/agent.py)，`is_user_turn=True` 时注入；保持 `conversation_window_size = skill.conversation_window_size`（默认 10）。
- 意图节点：[`intent_classifier.py:_build_llm_params`](../../../server/apps/opspilot/utils/chat_flow_utils/nodes/intent/intent_classifier.py)，`is_user_turn=True` 时注入；把写死的 `conversation_window_size=1` 改为模块常量 `INTENT_HISTORY_WINDOW = 5`（后续可配）。

> **精确加窗只发生一次、在下游**：两类节点最终都走 `ChatService.invoke_chat → format_chat_server_kwargs → history_service.process_chat_history(chat_history, conversation_window_size, …)`。该函数取 `chat_history` 的最后 N 条**消息**（N = 上面设置的 `conversation_window_size`），当前用户消息在列表末尾必然保留，其前补最近的历史。因此 helper 不要再加精确窗口，避免重复加窗。

> 当前轮要追加的"用户消息"用节点已构造的 `final_message`（含节点 prompt + 用户原话），保持现有行为，只在其前面加历史。

### 4.5 改动范围（文件级）

| 文件 | 改动 |
|---|---|
| `engine/engine.py::_initialize_variables`（~99-108） | 写入 `original_user_message` 与 `bot_id` 两个 `variable_manager` 变量 |
| `utils/chat_flow_utils/conversation_history.py`（**新增**） | `load_session_history(...)` 读取+格式化；`build_node_chat_history(...)` 判定+注入 |
| `nodes/agent/agent.py::_build_llm_params` / `set_llm_params` | 透传原始 `message`，`chat_history` 改由 `build_node_chat_history` 生成 |
| `nodes/intent/intent_classifier.py::_build_llm_params` | `chat_history` 改由 `build_node_chat_history` 生成；窗口由写死的 1 改为 `INTENT_HISTORY_WINDOW = 5` |

**明确不改**：`WorkFlowConversationHistory` 表结构 / 迁移；对话历史记录逻辑（user + final 已在记）；普通对话路径；`memory_read` / 记忆空间；前端节点配置面板。

### 4.6 错误处理与边界

- **首轮 / 无历史**：查询为空 → 历史列表为空 → 行为同今天。
- **读历史失败（DB 异常等）**：`try/except` 记日志后按"无历史"降级，**绝不阻断对话**。
- **`session_id` 为空**：返回空历史（不兜底，避免串话）。
- **定时 / celery 触发**：本就不记录历史，自然取不到，符合预期。
- **token 控制**：复用 `process_chat_history` 的窗口截断；不新增 token 级裁剪。

---

## 5. 测试方案

遵循 `server/docs/testing-guide.md` 分层约定，测试置于 `server/apps/opspilot/tests/workflow/`。

- **`_pure` / 单元**：`build_workflow_chat_history`
  - 行 → 事件列表映射正确（user/bot → event），按时间正序。
  - `.exclude(execution_id=current)` 确实剔除当前轮。
  - `session_id` 为空 → 返回 `[]`。
  - `cap` 仅粗截断、不做精确加窗（精确窗口由下游 `process_chat_history` 负责）。
- **`is_user_turn` 规则**：输入 == 锚点 → True；输入 == 上游输出 → False；intent 分支输入（`intent_previous_output`）→ True。
- **`_service`**：`agent._build_llm_params` / `intent._build_llm_params` 在 `is_user_turn` 为真时把历史拼进 `chat_history`（历史在前、当前消息在末尾），为假时不拼；当前用户消息始终保留。
- **E2E / BDD**（中文 Gherkin）：
  - 多轮指代：同一 `session_id` 下先"广州天气"后"深圳呢"，断言第二轮 agent 的 `chat_history` 含第一轮、且不含当前轮重复。
  - 流水线：`用户 → agent1 → agent2(美化)`，断言 agent2 不注入历史。
  - 意图分支：断言意图节点与分支 agent 均注入历史。

> 注意（来自既往经验）：opspilot 整目录串行跑有既有失败，按单文件 / 小批跑；疑似回归就在 master 跑同命令对比。

---

## 6. 风险与权衡

- **R1 串联式协同不支持带历史**（§4.3 边界）：需并联连线规避，或未来上方案 B。已与需求方确认本期接受。
- **R2 echo 误判**：极少见、低影响，已接受并记录。
- **R3 行为变化 / token 增加**：现有 workflow 升级后会自动开始带历史（面向用户原话的节点），多轮会话 token 上升。属预期、可被窗口控制；纯加工节点不受影响。
- **R4 跨渠道同 session**：以 `session_id` 为会话主键，依赖渠道侧 `session_id` 稳定。定时/无 session 的情况已降级处理。

---

## 7. 验证步骤（前后端联调）

后端行为变更，建议在对话应用 UI 实测：
1. 建一个含意图分支（或流水线）的 workflow 并发布。
2. 同一会话内先问"广州天气如何？"，确认正常回答。
3. 紧接着问"深圳呢？"，确认回答的是**深圳的天气**（指代解析成功）。
4. 流水线场景：确认下游"美化"节点的输出未被历史污染。
5. 查 `WorkFlowConversationHistory` 确认仍是每轮两条（user + final），无新增重复。
