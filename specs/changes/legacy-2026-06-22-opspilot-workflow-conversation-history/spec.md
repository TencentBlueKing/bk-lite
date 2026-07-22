# Historical Superpowers change: 2026-06-22-opspilot-workflow-conversation-history

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-06-22-opspilot-workflow-conversation-history.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 OpsPilot Workflow 内"面向用户原话"的 agent / 意图节点能拿到本会话的跨轮历史，使"广州天气如何 → 深圳呢"这类指代可解析；纯加工上游输出的下游节点不注入历史。

**Architecture:** 复用已存在的 `WorkFlowConversationHistory`（每轮记 user + 最终 bot 两条），不改表。引擎初始化时写两个锚点变量（`original_user_message`、`bot_id`）；新增一个 helper 模块按 `session_id` 读历史并判定是否注入（节点原始输入 == 本轮用户原话才注入）；agent / 意图节点把写死的 `chat_history` 改为调用 helper。精确加窗仍由下游既有的 `process_chat_history` 完成。

**Tech Stack:** Python 3.12 / Django 4.2 / pytest + pytest-django / pytest-mock（mocker）。

**设计文档：** [docs/superpowers/specs/2026-06-22-opspilot-workflow-conversation-history-design.md](../specs/2026-06-22-opspilot-workflow-conversation-history-design.md)

---

## 执行须知（环境与提交）

- **全程在 worktree 改 + 测**（已把主仓库的 `server/.env` 与 `server/local_settings.py` 拷进 worktree，二者 gitignore、不会污染 git）。实测已能在 worktree 跑通既有 workflow 测试。
- **运行测试的确切命令**（在 worktree `server` 目录，用项目专用 venv，跳过 cov/html 提速、保留 `--reuse-db`）：
  ```bash
  cd /d/app/github/bk-lite/.claude/worktrees/charming-chaum-da9a90/server && \
  /d/app/venv/bkliteserver/Scripts/python.exe -m pytest "<test-path>" -o addopts="--reuse-db" -p no:cacheprovider 2>&1 | tail -40
  ```
  - 不要用 `uv run pytest`（worktree 内不一定配好）；用上面的 venv python 直跑。
  - 控制台中文日志可能乱码，只看 PASSED/FAILED 判定。
  - opspilot 整目录串行跑有既有失败/收集污染——**只按本计划给出的单文件跑**。
- **提交**：开发期不自动同步 master、不自动 push。每个 Task 末尾 `git commit` 仅在本地 worktree 分支（`claude/charming-chaum-da9a90`）；`git add` 只加任务列出的源/测试文件，**不要** add `.env`/`local_settings.py`。
- **完成后质量检查**：对改动的 `.py` 跑 `isort` + `black` + `flake8`（见 Task 6）。
- 备注：主仓库 `agent.py` 比 worktree 多 3 行（`session_id`/`bot_id` 透传，位于本任务改点之后），与本实现无关，留作将来合并处理。

---

## File Structure

| 文件 | 职责 | 改/建 |
|---|---|---|
| `server/apps/opspilot/utils/chat_flow_utils/conversation_history.py` | 跨轮历史的**读取**(`load_session_history`)与**注入判定+拼装**(`build_node_chat_history`) | 新建 |
| `server/apps/opspilot/utils/chat_flow_utils/engine/engine.py` | `_initialize_variables` 写锚点变量 `original_user_message` / `bot_id` | 改 |
| `server/apps/opspilot/utils/chat_flow_utils/nodes/agent/agent.py` | `set_llm_params`/`_build_llm_params` 透传原始 message，`chat_history` 改走 helper | 改 |
| `server/apps/opspilot/utils/chat_flow_utils/nodes/intent/intent_classifier.py` | `_build_llm_params` 的 `chat_history` 改走 helper；窗口 1→`INTENT_HISTORY_WINDOW` | 改 |
| `server/apps/opspilot/tests/workflow/cases/test_conversation_history.py` | helper 两函数的单元测试 | 新建 |
| `server/apps/opspilot/tests/workflow/cases/test_agent_history_injection.py` | agent 节点 `_build_llm_params` 注入测试 | 新建 |
| `server/apps/opspilot/tests/workflow/cases/test_intent_history_injection.py` | 意图节点多轮注入端到端测试 | 新建 |
| `server/apps/opspilot/tests/workflow/cases/test_engine_history_anchors.py` | 引擎锚点变量测试 | 新建 |

测试沿用 `server/apps/opspilot/tests/workflow/conftest.py` 已有 fixtures：`bot`、`bot_workflow`、`intent_workflow`。

---

## Task 1: 引擎写入锚点变量（`original_user_message` / `bot_id`）

**Files:**
- Modify: `server/apps/opspilot/utils/chat_flow_utils/engine/engine.py:99-108`（`_initialize_variables`）
- Test: `server/apps/opspilot/tests/workflow/cases/test_engine_history_anchors.py`

- [ ] **Step 1: 写失败测试**

新建 `server/apps/opspilot/tests/workflow/cases/test_engine_history_anchors.py`：

```python
"""引擎初始化应写入跨轮历史所需的锚点变量。"""
import pytest

from apps.opspilot.utils.chat_flow_utils.engine.factory import create_chat_flow_engine


@pytest.mark.django_db(transaction=True)
def test_initialize_variables_sets_history_anchors(bot_workflow):
    engine = create_chat_flow_engine(bot_workflow, "entry_node")

    engine._initialize_variables(
        {"last_message": "广州天气如何", "user_id": "u@test.com", "session_id": "s1"}
    )

    assert engine.variable_manager.get_variable("original_user_message") == "广州天气如何"
    assert engine.variable_manager.get_variable("bot_id") == bot_workflow.bot_id
```

- [ ] **Step 2: 跑测试确认失败**

Run（主仓库 server 目录）：`uv run pytest apps/opspilot/tests/workflow/cases/test_engine_history_anchors.py -v`
Expected: FAIL — `original_user_message` 为 `None`（断言不等）。

- [ ] **Step 3: 最小实现**

在 `engine.py` 的 `_initialize_variables` 末尾（现有 `set_variable("flow_input", input_data)` 之后）追加两行：

```python
    def _initialize_variables(self, input_data: Dict[str, Any]):
        """初始化变量管理器

        Args:
            input_data: 输入数据
        """
        self.variable_manager.set_variable("flow_id", str(self.instance.id))
        self.variable_manager.set_variable("execution_id", self.execution_id)
        self.variable_manager.set_variable("last_message", input_data.get("last_message", ""))
        self.variable_manager.set_variable("flow_input", input_data)
        # 跨轮历史注入所需的稳定锚点：本轮用户原话 + bot_id（flow_input 不一定带 bot_id）
        self.variable_manager.set_variable("original_user_message", input_data.get("last_message", ""))
        self.variable_manager.set_variable("bot_id", self.instance.bot_id)
```

- [ ] **Step 4: 跑测试确认通过**

Run：`uv run pytest apps/opspilot/tests/workflow/cases/test_engine_history_anchors.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add server/apps/opspilot/utils/chat_flow_utils/engine/engine.py server/apps/opspilot/tests/workflow/cases/test_engine_history_anchors.py
git commit -m "feat(opspilot): 引擎写入跨轮历史锚点变量(original_user_message/bot_id)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: helper —— `load_session_history`（读历史）

**Files:**
- Create: `server/apps/opspilot/utils/chat_flow_utils/conversation_history.py`
- Test: `server/apps/opspilot/tests/workflow/cases/test_conversation_history.py`

- [ ] **Step 1: 写失败测试**

新建 `server/apps/opspilot/tests/workflow/cases/test_conversation_history.py`：

```python
"""conversation_history helper 单元测试。"""
import pytest
from django.utils import timezone

from apps.opspilot.models.bot_mgmt import WorkFlowConversationHistory
from apps.opspilot.utils.chat_flow_utils.conversation_history import load_session_history


def _add_history(bot_id, role, content, execution_id, session_id="s1", user_id="u@test.com"):
    return WorkFlowConversationHistory.objects.create(
        bot_id=bot_id,
        node_id="entry",
        user_id=user_id,
        conversation_role=role,
        conversation_content=content,
        conversation_time=timezone.now(),
        entry_type="web_chat",
        session_id=session_id,
        execution_id=execution_id,
    )


@pytest.mark.django_db(transaction=True)
class TestLoadSessionHistory:
    def test_returns_prior_turns_in_chronological_order(self, bot):
        _add_history(bot.id, "user", "广州天气如何", "exec-1")
        _add_history(bot.id, "bot", "广州20-28度", "exec-1")

        history = load_session_history(bot.id, "u@test.com", "s1", exclude_execution_id="exec-2")

        assert history == [
            {"event": "user", "message": "广州天气如何"},
            {"event": "bot", "message": "广州20-28度"},
        ]

    def test_excludes_current_execution(self, bot):
        _add_history(bot.id, "user", "广州天气如何", "exec-1")
        _add_history(bot.id, "user", "深圳呢", "exec-2")  # 当前轮已落库，必须被排除

        history = load_session_history(bot.id, "u@test.com", "s1", exclude_execution_id="exec-2")

        assert [h["message"] for h in history] == ["广州天气如何"]

    def test_empty_session_id_returns_empty(self, bot):
        _add_history(bot.id, "user", "x", "exec-1", session_id="")
        assert load_session_history(bot.id, "u@test.com", "", exclude_execution_id="exec-2") == []

    def test_missing_bot_id_returns_empty(self):
        assert load_session_history(None, "u@test.com", "s1", exclude_execution_id="exec-2") == []
```

- [ ] **Step 2: 跑测试确认失败**

Run：`uv run pytest apps/opspilot/tests/workflow/cases/test_conversation_history.py -v`
Expected: FAIL — `ModuleNotFoundError: conversation_history` / `ImportError: load_session_history`。

- [ ] **Step 3: 最小实现**

新建 `server/apps/opspilot/utils/chat_flow_utils/conversation_history.py`：

```python
"""Workflow 跨轮会话历史读取与注入工具（方案 A：单一会话历史线）。

把 WorkFlowConversationHistory 里已存的 (用户原话, 系统最终输出) 读回来，
注入到"面向用户原话"的 agent / 意图节点。不改表、不改记录逻辑。
"""
from typing import Any, Dict, List

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.models.bot_mgmt import WorkFlowConversationHistory


def load_session_history(bot_id, user_id, session_id, exclude_execution_id, cap: int = 50) -> List[Dict[str, Any]]:
    """读取本会话历史轮次（不含当前轮），转成 chat_history 事件列表。

    - 按 (bot_id, user_id, session_id) 过滤，排除当前 execution_id（当前轮已落库的 user 记录）。
    - 取最近 cap 条做粗截断；精确加窗交给下游 process_chat_history。
    - session_id 为空或 bot_id 缺失时返回 []，避免串话。
    - 任何异常都降级为 []，绝不阻断对话。
    """
    if not session_id or bot_id is None:
        return []
    try:
        rows = list(
            WorkFlowConversationHistory.objects.filter(
                bot_id=bot_id, user_id=user_id, session_id=session_id
            )
            .exclude(execution_id=exclude_execution_id)
            .order_by("-conversation_time", "-id")[:cap]
        )
    except Exception as e:  # pragma: no cover - 防御性降级
        logger.warning(f"[history] 读取会话历史失败: bot_id={bot_id}, session_id={session_id}, error={e}")
        return []
    rows.reverse()  # 倒序取最近 cap 条后翻回时间正序
    history: List[Dict[str, Any]] = []
    for row in rows:
        event = "user" if row.conversation_role == "user" else "bot"
        history.append({"event": event, "message": row.conversation_content})
    return history
```

- [ ] **Step 4: 跑测试确认通过**

Run：`uv run pytest apps/opspilot/tests/workflow/cases/test_conversation_history.py -v`
Expected: PASS（4 个用例）

- [ ] **Step 5: 提交**

```bash
git add server/apps/opspilot/utils/chat_flow_utils/conversation_history.py server/apps/opspilot/tests/workflow/cases/test_conversation_history.py
git commit -m "feat(opspilot): 新增 load_session_history 读取 workflow 跨轮会话历史

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: helper —— `build_node_chat_history`（判定 + 拼装）

**Files:**
- Modify: `server/apps/opspilot/utils/chat_flow_utils/conversation_history.py`
- Test: `server/apps/opspilot/tests/workflow/cases/test_conversation_history.py`（追加）

- [ ] **Step 1: 写失败测试**

在 `test_conversation_history.py` 顶部补充 import，并追加一个测试类：

```python
from apps.opspilot.utils.chat_flow_utils.conversation_history import build_node_chat_history
from apps.opspilot.utils.chat_flow_utils.engine.core.variable_manager import VariableManager


def _vm_with_anchor(bot_id, anchor="深圳呢", session_id="s1", execution_id="exec-2", user_id="u@test.com"):
    vm = VariableManager()
    vm.set_variable("original_user_message", anchor)
    vm.set_variable("bot_id", bot_id)
    vm.set_variable("execution_id", execution_id)
    vm.set_variable("flow_input", {"user_id": user_id, "session_id": session_id})
    return vm


@pytest.mark.django_db(transaction=True)
class TestBuildNodeChatHistory:
    def test_injects_history_when_input_is_user_turn(self, bot):
        _add_history(bot.id, "user", "广州天气如何", "exec-1")
        _add_history(bot.id, "bot", "广州20-28度", "exec-1")
        vm = _vm_with_anchor(bot.id)

        result = build_node_chat_history(vm, raw_input_message="深圳呢", final_message="深圳呢")

        assert result[0] == {"event": "user", "message": "广州天气如何"}
        assert result[1] == {"event": "bot", "message": "广州20-28度"}
        assert result[-1] == {"event": "user", "message": "深圳呢"}

    def test_no_history_when_input_is_upstream_output(self, bot):
        # 下游加工节点：输入是上游 agent 的输出，不等于用户原话 → 不注入
        _add_history(bot.id, "user", "广州天气如何", "exec-1")
        vm = _vm_with_anchor(bot.id)

        result = build_node_chat_history(
            vm, raw_input_message="agent_processed: 广州天气如何", final_message="agent_processed: 广州天气如何"
        )

        assert result == [{"event": "user", "message": "agent_processed: 广州天气如何"}]

    def test_no_history_when_anchor_missing(self, bot):
        vm = VariableManager()  # 没有 original_user_message
        result = build_node_chat_history(vm, raw_input_message="深圳呢", final_message="深圳呢")
        assert result == [{"event": "user", "message": "深圳呢"}]
```

- [ ] **Step 2: 跑测试确认失败**

Run：`uv run pytest apps/opspilot/tests/workflow/cases/test_conversation_history.py::TestBuildNodeChatHistory -v`
Expected: FAIL — `ImportError: build_node_chat_history`。

- [ ] **Step 3: 最小实现**

在 `conversation_history.py` 末尾追加：

```python
def build_node_chat_history(variable_manager, raw_input_message: Any, final_message: Any) -> List[Dict[str, Any]]:
    """为 LLM 节点构建 chat_history。

    规则：仅当本节点的"原始输入" == 本轮用户原话（锚点）时注入会话历史；
    否则只返回当前这条（维持原行为）。返回列表末尾恒为当前用户消息。
    """
    current = {"event": "user", "message": final_message}
    anchor = variable_manager.get_variable("original_user_message", "")
    # 锚点缺失，或本节点吃的是上游产物 → 不注入
    if not anchor or raw_input_message != anchor:
        return [current]
    flow_input = variable_manager.get_variable("flow_input") or {}
    history = load_session_history(
        bot_id=variable_manager.get_variable("bot_id"),
        user_id=flow_input.get("user_id", "anonymous"),
        session_id=flow_input.get("session_id", ""),
        exclude_execution_id=variable_manager.get_variable("execution_id", ""),
    )
    return history + [current]
```

- [ ] **Step 4: 跑测试确认通过**

Run：`uv run pytest apps/opspilot/tests/workflow/cases/test_conversation_history.py -v`
Expected: PASS（含新增 3 个用例，全文件 7 个）

- [ ] **Step 5: 提交**

```bash
git add server/apps/opspilot/utils/chat_flow_utils/conversation_history.py server/apps/opspilot/tests/workflow/cases/test_conversation_history.py
git commit -m "feat(opspilot): 新增 build_node_chat_history 按是否面向用户原话决定注入历史

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: agent 节点接入 helper

**Files:**
- Modify: `server/apps/opspilot/utils/chat_flow_utils/nodes/agent/agent.py`
  - import helper
  - `_build_llm_params`：加参数 `raw_message`，`chat_history` 改走 helper（原第 199 行）
  - `set_llm_params`：调用处透传 `raw_message=message`（原第 345 行）
- Test: `server/apps/opspilot/tests/workflow/cases/test_agent_history_injection.py`

- [ ] **Step 1: 写失败测试**

新建 `server/apps/opspilot/tests/workflow/cases/test_agent_history_injection.py`：

```python
"""agent 节点 _build_llm_params 应在"面向用户原话"时注入会话历史。"""
import types

import pytest
from django.utils import timezone

from apps.opspilot.models.bot_mgmt import WorkFlowConversationHistory
from apps.opspilot.utils.chat_flow_utils.engine.core.variable_manager import VariableManager
from apps.opspilot.utils.chat_flow_utils.nodes.agent.agent import AgentNode


def _fake_skill():
    """构造 _build_llm_params 需要的最小 skill 替身。"""
    return types.SimpleNamespace(
        llm_model_id=1,
        skill_prompt="你是助手",
        skill_params=[],
        temperature=0.7,
        conversation_window_size=10,
        enable_rag=False,
        rag_score_threshold_map={},
        enable_rag_knowledge_source=False,
        show_think=False,
        tools=[],
        skill_type="basic_tool",
        team=[1],
        enable_km_route=False,
        km_llm_model=None,
        enable_suggest=False,
        enable_query_rewrite=False,
    )


def _vm(bot_id):
    vm = VariableManager()
    vm.set_variable("original_user_message", "深圳呢")
    vm.set_variable("bot_id", bot_id)
    vm.set_variable("execution_id", "exec-2")
    vm.set_variable("flow_input", {"user_id": "u@test.com", "session_id": "s1"})
    vm.set_variable("flow_id", "1")
    return vm


@pytest.mark.django_db(transaction=True)
def test_agent_injects_history_when_user_facing(bot):
    WorkFlowConversationHistory.objects.create(
        bot_id=bot.id, node_id="entry", user_id="u@test.com", conversation_role="user",
        conversation_content="广州天气如何", conversation_time=timezone.now(),
        entry_type="web_chat", session_id="s1", execution_id="exec-1",
    )
    node = AgentNode(_vm(bot.id))

    params = node._build_llm_params(
        _fake_skill(), final_message="深圳呢", flow_input={"user_id": "u@test.com"},
        node_id="agent_node", raw_message="深圳呢",
    )

    messages = [h["message"] for h in params["chat_history"]]
    assert "广州天气如何" in messages
    assert params["chat_history"][-1] == {"event": "user", "message": "深圳呢"}


@pytest.mark.django_db(transaction=True)
def test_agent_no_history_when_consuming_upstream_output(bot):
    WorkFlowConversationHistory.objects.create(
        bot_id=bot.id, node_id="entry", user_id="u@test.com", conversation_role="user",
        conversation_content="广州天气如何", conversation_time=timezone.now(),
        entry_type="web_chat", session_id="s1", execution_id="exec-1",
    )
    node = AgentNode(_vm(bot.id))

    params = node._build_llm_params(
        _fake_skill(), final_message="agent_processed: x", flow_input={"user_id": "u@test.com"},
        node_id="agent2", raw_message="agent_processed: x",  # 上游输出，非用户原话
    )

    assert params["chat_history"] == [{"event": "user", "message": "agent_processed: x"}]
```

- [ ] **Step 2: 跑测试确认失败**

Run：`uv run pytest apps/opspilot/tests/workflow/cases/test_agent_history_injection.py -v`
Expected: FAIL — `_build_llm_params() got an unexpected keyword argument 'raw_message'`。

- [ ] **Step 3: 实现（改三处）**

3a. `agent.py` 顶部 import 区加（现有 import 之后）：

```python
from apps.opspilot.utils.chat_flow_utils.conversation_history import build_node_chat_history
```

3b. `_build_llm_params` 改签名 + 改 `chat_history` 一行：

```python
    def _build_llm_params(self, skill: LLMSkill, final_message: str, flow_input: Dict[str, Any], node_id: str = "", raw_message: Any = "") -> Dict[str, Any]:
```

把原来这行（约 199 行）：

```python
            "chat_history": [{"event": "user", "message": final_message}],
```

改成：

```python
            "chat_history": build_node_chat_history(self.variable_manager, raw_message, final_message),
```

3c. `set_llm_params` 调用处（约 345 行）透传 `raw_message=message`：

```python
        # 构建LLM参数
        llm_params = self._build_llm_params(skill, final_message, flow_input, node_id=node_id, raw_message=message)
```

> 说明：`message = input_data.get(input_key)`（约 336 行）就是节点的"原始输入"，prompt 拼接发生在 `_build_final_message` 之后、不影响此处比较。

- [ ] **Step 4: 跑测试确认通过**

Run：`uv run pytest apps/opspilot/tests/workflow/cases/test_agent_history_injection.py -v`
Expected: PASS（2 个用例）

- [ ] **Step 5: 跑既有 e2e 防回归**

Run：`uv run pytest apps/opspilot/tests/workflow/cases/test_workflow_e2e.py -v`
Expected: PASS（agent 注入对纯单轮无影响）

- [ ] **Step 6: 提交**

```bash
git add server/apps/opspilot/utils/chat_flow_utils/nodes/agent/agent.py server/apps/opspilot/tests/workflow/cases/test_agent_history_injection.py
git commit -m "feat(opspilot): agent 节点按是否面向用户原话注入会话历史

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: 意图节点接入 helper + 调整窗口

**Files:**
- Modify: `server/apps/opspilot/utils/chat_flow_utils/nodes/intent/intent_classifier.py`
  - import helper + 新增模块常量 `INTENT_HISTORY_WINDOW = 5`
  - `_build_llm_params`：`chat_history` 改走 helper（原第 89 行）；`conversation_window_size` 由 `1` 改为常量（原第 91 行）
- Test: `server/apps/opspilot/tests/workflow/cases/test_intent_history_injection.py`

- [ ] **Step 1: 写失败测试**

新建 `server/apps/opspilot/tests/workflow/cases/test_intent_history_injection.py`：

```python
"""意图节点多轮：第二轮应能拿到第一轮的会话历史（端到端）。"""
import pytest

from apps.opspilot.utils.chat_flow_utils.engine.core.base_executor import BaseNodeExecutor
from apps.opspilot.utils.chat_flow_utils.engine.factory import create_chat_flow_engine

ENTRY_NODE_ID = "openai-1777450801989"  # 来自 intent_workflow(id=4) 的 openai 入口


class RecordingAgentExecutor(BaseNodeExecutor):
    def execute(self, node_id, node_config, input_data):
        ik = node_config.get("data", {}).get("config", {}).get("inputParams", "last_message")
        ok = node_config.get("data", {}).get("config", {}).get("outputParams", "last_message")
        return {ok: f"handled:{input_data.get(ik, '')}"}


@pytest.mark.django_db(transaction=True)
def test_intent_node_injects_prior_turn_history(intent_workflow, mocker):
    invoke = mocker.patch(
        "apps.opspilot.utils.chat_flow_utils.nodes.intent.intent_classifier.ChatService.invoke_chat",
        return_value=({"message": "generate_script"}, {}, {}),
    )

    # 第一轮：落一条 user + 一条 bot 历史（session=s1）
    e1 = create_chat_flow_engine(intent_workflow, ENTRY_NODE_ID)
    e1.custom_node_executors["agents"] = RecordingAgentExecutor(e1.variable_manager)
    e1.execute({"last_message": "广州天气如何", "user_id": "u@test.com", "node_id": ENTRY_NODE_ID, "session_id": "s1"})

    # 第二轮：同一 session，意图节点应注入第一轮历史
    e2 = create_chat_flow_engine(intent_workflow, ENTRY_NODE_ID)
    e2.custom_node_executors["agents"] = RecordingAgentExecutor(e2.variable_manager)
    e2.execute({"last_message": "深圳呢", "user_id": "u@test.com", "node_id": ENTRY_NODE_ID, "session_id": "s1"})

    # 最后一次 invoke_chat 即第二轮意图分类
    chat_history = invoke.call_args_list[-1][0][0]["chat_history"]
    messages = [h["message"] for h in chat_history]
    assert "广州天气如何" in messages, f"第二轮意图节点缺少上一轮历史: {messages}"
    assert chat_history[-1]["message"] == "深圳呢"
```

- [ ] **Step 2: 跑测试确认失败**

Run：`uv run pytest apps/opspilot/tests/workflow/cases/test_intent_history_injection.py -v`
Expected: FAIL — 第二轮 `chat_history` 仅 `[{"event":"user","message":"深圳呢"}]`，断言 `"广州天气如何" in messages` 失败。

- [ ] **Step 3: 实现（改三处）**

3a. `intent_classifier.py` 顶部 import 区加：

```python
from apps.opspilot.utils.chat_flow_utils.conversation_history import build_node_chat_history
```

3b. 在 import 之后、`class IntentClassifierNode` 之前加模块常量：

```python
# 意图分类读取最近 N 条会话消息用于解析省略/指代（如"深圳呢"），由下游 process_chat_history 精确加窗
INTENT_HISTORY_WINDOW = 5
```

3c. `_build_llm_params` 里把这两行（约 89、91 行）：

```python
            "chat_history": [{"event": "user", "message": message}],
            "user_message": message,
            "conversation_window_size": 1,
```

改成：

```python
            "chat_history": build_node_chat_history(self.variable_manager, message, message),
            "user_message": message,
            "conversation_window_size": INTENT_HISTORY_WINDOW,
```

> 说明：意图节点的 `message`（= `previous_node_output`）就是它的原始输入；对首个意图节点而言即用户原话，与锚点相等 → 注入。

- [ ] **Step 4: 跑测试确认通过**

Run：`uv run pytest apps/opspilot/tests/workflow/cases/test_intent_history_injection.py -v`
Expected: PASS

- [ ] **Step 5: 跑既有意图路由测试防回归**

Run：`uv run pytest apps/opspilot/tests/workflow/cases/test_workflow_intent_routing.py -v`
Expected: PASS（注入历史不改变路由结果；`test_intent_node_receives_user_message` 仍断言 `user_message` 为原话，不受影响）

- [ ] **Step 6: 提交**

```bash
git add server/apps/opspilot/utils/chat_flow_utils/nodes/intent/intent_classifier.py server/apps/opspilot/tests/workflow/cases/test_intent_history_injection.py
git commit -m "feat(opspilot): 意图节点注入会话历史并放宽窗口(1->5)以解析省略跟进

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: 质量检查与回归

**Files:** 无新增，仅校验与跑批。

- [ ] **Step 1: 格式化与 lint（对改动文件）**

在主仓库 `server` 目录执行：

```bash
uv run isort apps/opspilot/utils/chat_flow_utils/conversation_history.py apps/opspilot/utils/chat_flow_utils/engine/engine.py apps/opspilot/utils/chat_flow_utils/nodes/agent/agent.py apps/opspilot/utils/chat_flow_utils/nodes/intent/intent_classifier.py apps/opspilot/tests/workflow/cases/test_conversation_history.py apps/opspilot/tests/workflow/cases/test_agent_history_injection.py apps/opspilot/tests/workflow/cases/test_intent_history_injection.py apps/opspilot/tests/workflow/cases/test_engine_history_anchors.py
uv run black apps/opspilot/utils/chat_flow_utils/conversation_history.py apps/opspilot/utils/chat_flow_utils/engine/engine.py apps/opspilot/utils/chat_flow_utils/nodes/agent/agent.py apps/opspilot/utils/chat_flow_utils/nodes/intent/intent_classifier.py apps/opspilot/tests/workflow/cases/test_conversation_history.py apps/opspilot/tests/workflow/cases/test_agent_history_injection.py apps/opspilot/tests/workflow/cases/test_intent_history_injection.py apps/opspilot/tests/workflow/cases/test_engine_history_anchors.py
uv run flake8 apps/opspilot/utils/chat_flow_utils/conversation_history.py apps/opspilot/utils/chat_flow_utils/nodes/agent/agent.py apps/opspilot/utils/chat_flow_utils/nodes/intent/intent_classifier.py
```

Expected: black/isort 无改动或自动格式化通过；flake8 无 error。

- [ ] **Step 2: 跑本特性全部新测试 + 直接相关回归**

```bash
uv run pytest apps/opspilot/tests/workflow/cases/test_engine_history_anchors.py apps/opspilot/tests/workflow/cases/test_conversation_history.py apps/opspilot/tests/workflow/cases/test_agent_history_injection.py apps/opspilot/tests/workflow/cases/test_intent_history_injection.py apps/opspilot/tests/workflow/cases/test_workflow_e2e.py apps/opspilot/tests/workflow/cases/test_workflow_intent_routing.py -v
```

Expected: 全 PASS。若 `test_workflow_e2e.py` / `test_workflow_intent_routing.py` 有失败，先在 master 跑同命令对比，确认是否本改动引入（参考既有套件污染问题）。

- [ ] **Step 3: 若有格式化改动则补提交**

```bash
git add -A
git commit -m "style(opspilot): isort/black 格式化对话历史相关改动

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## 手动联调验证（实现后由人验证）

后端行为变更，建议在对话应用 UI 实测一次：
1. 用含意图分支（或流水线）的 workflow，发布。
2. 同一会话先问"广州天气如何？"，确认正常回答。
3. 紧接着问"深圳呢？"，确认回答的是**深圳天气**（指代解析成功）。
4. 流水线场景：确认下游"美化"节点输出未被历史污染。
5. 查 `WorkFlowConversationHistory`：仍是每轮两条（user + final），无重复。

---

## Self-Review（计划自检）

**1. Spec 覆盖：**
- §4.2 复用现有表/记录 → Task 2/3 仅读不写、不动表 ✓
- §4.3 锚点 + is_user_turn 规则 → Task 1（锚点）+ Task 3（判定）✓
- §4.4 读取/排除当前轮/窗口在下游 → Task 2（`exclude(execution_id)`、`cap`）；窗口由 agent skill 的 `conversation_window_size`(默认10) / 意图 `INTENT_HISTORY_WINDOW`(5) 经下游 `process_chat_history` 加窗 ✓
- §4.5 改动 4 文件 → Task 1/2-3/4/5 一一对应 ✓
- §4.6 错误兜底（首轮空 / DB 失败降级 / 空 session）→ Task 2 实现 + `test_empty_session_id_returns_empty`、`test_missing_bot_id_returns_empty` ✓
- §5 测试分层 → helper 单测 + agent 单测 + 意图端到端 ✓
- §4.3 已知边界（串联协同需并联、echo）→ 设计层记录，无需代码 ✓

**2. 占位符扫描：** 无 TBD/TODO；每个代码步骤均给出完整代码与命令。

**3. 类型/命名一致性：**
- `load_session_history(bot_id, user_id, session_id, exclude_execution_id, cap=50)` —— Task 2 定义，Task 3 按此调用（kwargs 一致）✓
- `build_node_chat_history(variable_manager, raw_input_message, final_message)` —— Task 3 定义，Task 4（`raw_message`/`final_message`）、Task 5（`message`/`message`）按位置参数调用 ✓
- 变量名 `original_user_message` / `bot_id` / `execution_id` —— Task 1 写入、Task 3 读取，一致 ✓
- 事件结构 `{"event": "user"|"bot", "message": str}` —— 与下游 `process_chat_history` 期望键名一致（`event`/`message`，`assistant→bot` 映射对 `bot` 幂等）✓

无遗留问题。

## specs: 2026-06-22-opspilot-workflow-conversation-history-design.md

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
