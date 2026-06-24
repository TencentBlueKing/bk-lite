# OpsPilot Workflow 对话历史注入（方案 A）Implementation Plan

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
