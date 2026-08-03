"""DeepAgent 统一引擎接线单测（service 层，全程 mock，无 DB/网络/真实 LLM）。

覆盖 ToolsNodes.build_deepagent_nodes 及其辅助方法如何把 BK-Lite 的
tools/MCP、knowledge_retrieve 工具、SKILL.md 技能（MinIO backend）、人工审批
（interrupt_on）真实接入 deepagents.create_deep_agent，以及 AG-UI 内置工具过滤。
"""

import asyncio
import json
import os
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import HumanMessage

from apps.opspilot.metis.llm.chain.node import ToolsNodes
from apps.opspilot.metis.llm.middleware.tool_runtime import (
    PLANNED_EXECUTION_HIDDEN_DEEPAGENT_TOOLS,
    ToolVisibilityMiddleware,
    is_progressive_tools_enabled,
)

pytestmark = pytest.mark.unit


def _tool(name):
    t = MagicMock()
    t.name = name
    return t


def _request(**overrides):
    base = dict(
        system_message_prompt="你是运维助手",
        naive_rag_request=[],
        extra_config={},
        approval_config=None,
        user_id="u1",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


class TestBuildInterruptOn:
    def test_disabled_returns_none(self):
        n = ToolsNodes()
        req = _request(approval_config=SimpleNamespace(enabled=False, tools=[]))
        assert n._build_interrupt_on(req, [_tool("a")]) is None

    def test_no_approval_config_returns_none(self):
        n = ToolsNodes()
        assert n._build_interrupt_on(_request(), [_tool("a")]) is None

    def test_named_tools_only(self):
        n = ToolsNodes()
        req = _request(approval_config=SimpleNamespace(enabled=True, tools=["danger_tool"]))
        result = n._build_interrupt_on(req, [_tool("danger_tool"), _tool("safe_tool")])
        assert result == {"danger_tool": True}

    def test_empty_tools_means_all_business_tools_excluding_builtins(self):
        n = ToolsNodes()
        req = _request(approval_config=SimpleNamespace(enabled=True, tools=[]))
        tools = [_tool("shell"), _tool("read_file"), _tool("write_todos"), _tool("k8s")]
        result = n._build_interrupt_on(req, tools)
        # deepagents 内置工具（read_file/write_todos）被排除
        assert result == {"shell": True, "k8s": True}


class TestCollectTools:
    def test_uses_all_tools_and_appends_kb_tool(self):
        n = ToolsNodes()
        n.all_tools = [_tool("shell"), _tool("k8s")]
        kb = _tool("knowledge_retrieve")
        with patch.object(ToolsNodes, "_build_knowledge_retrieve_tool", return_value=kb):
            tools = n._collect_deepagent_tools(_request())
        assert [t.name for t in tools] == ["shell", "k8s", "knowledge_retrieve"]

    def test_no_kb_tool_when_none(self):
        n = ToolsNodes()
        n.all_tools = [_tool("shell")]
        with patch.object(ToolsNodes, "_build_knowledge_retrieve_tool", return_value=None):
            tools = n._collect_deepagent_tools(_request())
        assert [t.name for t in tools] == ["shell"]


class TestSkillBackendSources:
    def test_no_packages_returns_none_empty(self):
        n = ToolsNodes()
        with patch.object(ToolsNodes, "_resolve_skill_packages", return_value=[]):
            backend, sources, sandbox_dir = n._build_skill_backend_and_sources(_request())
        assert backend is None and sources == [] and sandbox_dir is None

    def test_materializes_packages_into_ephemeral_sandbox(self):
        import os

        n = ToolsNodes()
        pkgs = [{"name": "k8s-triage"}, {"name": "log-analysis"}]
        with patch.object(ToolsNodes, "_resolve_skill_packages", return_value=pkgs), patch(
            "deepagents.backends.LocalShellBackend", return_value=MagicMock()
        ) as backend_cls, patch("apps.opspilot.services.skill_package.materializer.materialize_skill_package") as mat:
            backend, sources, sandbox_dir = n._build_skill_backend_and_sources(_request())
        assert backend is not None
        assert sources == ["/skills/"]
        assert mat.call_count == 2
        # 一次性沙箱目录被创建（用完即弃，由调用方清理）
        assert sandbox_dir and os.path.isdir(sandbox_dir)
        # 用的是 LocalShellBackend：虚拟根 + 不继承宿主环境
        _, kwargs = backend_cls.call_args
        assert kwargs["virtual_mode"] is True
        assert kwargs["inherit_env"] is False
        n._cleanup_sandbox(sandbox_dir)

    def test_single_package_materialize_failure_is_isolated(self):
        n = ToolsNodes()
        pkgs = [{"name": "a"}, {"name": "b"}]
        with patch.object(ToolsNodes, "_resolve_skill_packages", return_value=pkgs), patch(
            "deepagents.backends.LocalShellBackend", return_value=MagicMock()
        ), patch(
            "apps.opspilot.services.skill_package.materializer.materialize_skill_package",
            side_effect=[RuntimeError("boom"), None],
        ):
            backend, sources, sandbox_dir = n._build_skill_backend_and_sources(_request())
        # 单包失败不影响整体返回
        assert backend is not None and sources == ["/skills/"]
        n._cleanup_sandbox(sandbox_dir)

    def test_sandbox_env_excludes_host_secrets(self):
        n = ToolsNodes()
        os.environ["DB_PASSWORD"] = "should-not-leak"
        try:
            env = n._sandbox_env("/tmp/run-xyz")
        finally:
            os.environ.pop("DB_PASSWORD", None)
        assert "DB_PASSWORD" not in env
        assert set(env).issubset({"PATH", "LANG", "LC_ALL", "TMPDIR", "HOME", "KUBECONFIG"})
        assert env["TMPDIR"] == "/tmp/run-xyz"

    def test_cleanup_sandbox_removes_dir(self):
        import tempfile

        n = ToolsNodes()
        d = tempfile.mkdtemp(prefix="run-")
        assert os.path.isdir(d)
        n._cleanup_sandbox(d)
        assert not os.path.exists(d)
        n._cleanup_sandbox(None)  # None 安全

    def test_sandbox_prefers_runtime_python_when_parent_path_only_has_system_python(self):
        n = ToolsNodes()

        with patch.dict(os.environ, {"PATH": "/usr/bin:/bin"}):
            env = n._sandbox_env("/tmp/run-python-path")

        path_entries = env["PATH"].split(":")
        assert path_entries[0] == os.path.dirname(sys.executable)
        completed = subprocess.run(
            ["python3", "-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"],
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        assert completed.stdout.strip() == f"{sys.version_info.major}.{sys.version_info.minor}"


class _FakeGraphBuilder:
    def __init__(self):
        self.nodes = {}

    def add_node(self, name, fn):
        self.nodes[name] = fn


class TestBuildDeepagentNodes:
    def _run_wrapper(
        self,
        node,
        req,
        captured,
        *,
        plan_payload=None,
        plan_payloads=None,
        failing_agent_calls=(),
    ):
        gb = _FakeGraphBuilder()

        async def _build():
            return await node.build_deepagent_nodes(gb, composite_node_name="deep_agent")

        # 主线程无 event loop 时 `asyncio.get_event_loop()` 抛 RuntimeError;
        # 用 `asyncio.run()` 自管理 loop 创建/关闭。
        name = asyncio.run(_build())
        wrapper = gb.nodes[name]

        from langchain_core.messages import AIMessage, HumanMessage

        input_messages = [HumanMessage(content="排查 pod 崩溃")]

        fake_agent = MagicMock()

        async def _ainvoke(payload, config=None):
            captured.setdefault("ainvoke_messages", []).append(payload["messages"])
            middleware_list = list(captured["create_kwargs"].get("middleware") or [])
            visibility = next(
                (middleware for middleware in middleware_list if isinstance(middleware, ToolVisibilityMiddleware)),
                None,
            )
            if visibility is not None:
                visible_request = visibility._filter_request(
                    SimpleNamespace(
                        tools=[
                            *captured["create_kwargs"]["tools"],
                            _tool("write_todos"),
                            _tool("task"),
                            _tool("execute"),
                        ],
                        override=lambda **changes: SimpleNamespace(**changes),
                    )
                )
                captured.setdefault("visible_tool_calls", []).append([tool.name for tool in visible_request.tools])
            else:
                captured.setdefault("visible_tool_calls", []).append([tool.name for tool in captured["create_kwargs"]["tools"]])
            call_index = len(captured["visible_tool_calls"])
            appended_messages = [AIMessage(content=f"执行结果 {call_index}")]
            if call_index in failing_agent_calls:
                from langchain_core.messages import ToolMessage

                appended_messages.insert(
                    0,
                    ToolMessage(
                        content="connection refused",
                        name="diagnose_kubernetes_pod_issues",
                        tool_call_id=f"failed-{call_index}",
                        status="error",
                    ),
                )
            return {
                **payload,
                "messages": list(payload["messages"]) + appended_messages,
            }

        fake_agent.ainvoke = _ainvoke

        def _create(**kwargs):
            captured["create_kwargs"] = kwargs
            return fake_agent

        planned_responses = iter(plan_payloads or [])

        class _FakeLLM:
            async def ainvoke(self, messages, config=None):
                captured.setdefault("planner_calls", []).append(messages)
                payload = next(planned_responses) if plan_payloads is not None else plan_payload or {"goal": "直接回答", "steps": []}
                return AIMessage(
                    content=json.dumps(
                        payload,
                        ensure_ascii=False,
                    ),
                    usage_metadata={
                        "input_tokens": 100,
                        "output_tokens": 20,
                        "total_tokens": 120,
                    },
                )

        with patch("apps.opspilot.metis.llm.chain.node.create_deep_agent", side_effect=_create), patch.object(
            ToolsNodes, "get_llm_client", return_value=_FakeLLM()
        ):
            config = {"configurable": {"graph_request": req}}
            # 主线程无 event loop 时 `asyncio.get_event_loop()` 抛 RuntimeError;
            # 用 `asyncio.run()` 自管理 loop 创建/关闭。
            result = asyncio.run(wrapper({"messages": input_messages}, config))
        return result

    def test_passes_tools_and_returns_only_new_messages(self):
        node = ToolsNodes()
        node.all_tools = [_tool("shell")]
        req = _request()
        captured = {}
        with patch.object(ToolsNodes, "_build_knowledge_retrieve_tool", return_value=None):
            result = self._run_wrapper(node, req, captured)
        kwargs = captured["create_kwargs"]
        assert kwargs["model"].__class__.__name__ == "_FakeLLM"
        assert [t.name for t in kwargs["tools"]] == ["shell"]
        assert "system_prompt" in kwargs
        # 无技能/审批时不传 backend/skills/interrupt_on
        assert "backend" not in kwargs
        assert "skills" not in kwargs
        assert "interrupt_on" not in kwargs
        # 只返回 deepagent 新增消息
        assert len(result["messages"]) == 1
        assert result["messages"][0].content == "执行结果 1"

    def test_planned_execution_reuses_agent_and_replaces_tools_per_step(self):
        node = ToolsNodes()
        node._dynamic_mode = True
        node.all_tools = [
            _tool("current_time"),
            _tool("diagnose_kubernetes_pod_issues"),
            _tool("restart_pod"),
        ]
        node.active_tools = []
        req = _request(user_message="检查 Pod 故障")
        captured = {}

        with patch.object(ToolsNodes, "_build_knowledge_retrieve_tool", return_value=None):
            result = self._run_wrapper(
                node,
                req,
                captured,
                plan_payload={
                    "goal": "定位 Pod 故障",
                    "steps": [
                        {"objective": "确认当前时间", "tools": ["current_time"]},
                        {
                            "objective": "诊断 Pod",
                            "tools": ["diagnose_kubernetes_pod_issues"],
                        },
                    ],
                },
            )

        kwargs = captured["create_kwargs"]
        assert [tool.name for tool in kwargs["tools"]] == [
            "current_time",
            "diagnose_kubernetes_pod_issues",
            "restart_pod",
        ]
        assert captured["visible_tool_calls"] == [
            ["current_time"],
            ["diagnose_kubernetes_pod_issues"],
            [],
        ]
        assert len(captured["ainvoke_messages"]) == 3
        assert len(result["messages"]) == 3
        assert all(not isinstance(message, HumanMessage) for message in result["messages"])

    def test_planned_execution_hides_deepagent_builtin_tools(self):
        from langchain.agents.middleware import ModelCallLimitMiddleware

        node = ToolsNodes()
        node._dynamic_mode = True
        node.all_tools = [_tool("list_kubernetes_events"), _tool("restart_pod")]
        node.active_tools = []
        req = _request(
            user_message="告警：K8s Warning Failed on Pod/ns/pod-1",
            extra_config={"entry_type": "nats"},
        )
        captured = {}

        with patch.object(ToolsNodes, "_build_knowledge_retrieve_tool", return_value=None):
            self._run_wrapper(
                node,
                req,
                captured,
                plan_payload={
                    "goal": "检查事件",
                    "steps": [
                        {
                            "objective": "读取事件",
                            "tools": ["list_kubernetes_events"],
                        }
                    ],
                },
            )

        kwargs = captured["create_kwargs"]
        visibility = next(middleware for middleware in kwargs["middleware"] if isinstance(middleware, ToolVisibilityMiddleware))
        assert visibility._hidden_tools == PLANNED_EXECUTION_HIDDEN_DEEPAGENT_TOOLS
        assert "write_todos" in visibility._hidden_tools
        assert "task" in visibility._hidden_tools
        assert "read_file" not in visibility._hidden_tools
        assert visibility._always_visible_tools >= frozenset({"read_file", "write_file", "ls"})
        assert captured["visible_tool_calls"] == [
            ["list_kubernetes_events"],
            [],
        ]
        call_limit = next(middleware for middleware in kwargs["middleware"] if isinstance(middleware, ModelCallLimitMiddleware))
        assert call_limit.run_limit == 3
        assert call_limit.thread_limit == 10

    def test_tool_failure_replans_only_unfinished_steps(self):
        node = ToolsNodes()
        node.all_tools = [
            _tool("current_time"),
            _tool("diagnose_kubernetes_pod_issues"),
            _tool("list_kubernetes_events"),
        ]
        req = _request(user_message="定位 Pod 告警")
        captured = {}

        with patch.object(ToolsNodes, "_build_knowledge_retrieve_tool", return_value=None):
            self._run_wrapper(
                node,
                req,
                captured,
                plan_payloads=[
                    {
                        "goal": "定位 Pod 告警",
                        "steps": [
                            {"objective": "确认时间", "tools": ["current_time"]},
                            {
                                "objective": "诊断 Pod",
                                "tools": ["diagnose_kubernetes_pod_issues"],
                            },
                        ],
                    },
                    {
                        "goal": "改用事件定位",
                        "steps": [
                            {
                                "objective": "读取事件",
                                "tools": ["list_kubernetes_events"],
                            }
                        ],
                    },
                ],
                failing_agent_calls={2},
            )

        assert captured["visible_tool_calls"] == [
            ["current_time"],
            ["diagnose_kubernetes_pod_issues"],
            ["list_kubernetes_events"],
            [],
        ]
        assert len(captured["planner_calls"]) == 2
        replan_prompt = "\n".join(str(message.content) for message in captured["planner_calls"][1])
        assert "确认时间: 执行结果 1" in replan_prompt
        assert "connection refused" in replan_prompt

    def test_wires_skills_and_approval_when_configured(self):
        node = ToolsNodes()
        node.all_tools = [_tool("shell")]
        req = _request(approval_config=SimpleNamespace(enabled=True, tools=["shell"]))
        captured = {}
        fake_backend = MagicMock()
        with patch.object(ToolsNodes, "_build_knowledge_retrieve_tool", return_value=None), patch.object(
            ToolsNodes, "_build_skill_backend_and_sources", return_value=(fake_backend, ["/skills/"], None)
        ):
            self._run_wrapper(node, req, captured)
        kwargs = captured["create_kwargs"]
        assert kwargs["backend"] is fake_backend
        assert kwargs["skills"] == ["/skills/"]
        assert kwargs["interrupt_on"] == {"shell": True}

    def test_build_skill_backend_and_sources_called_only_once_per_run(self):
        """S2 回归测试:每次 deepagent 流只调一次 _build_skill_backend_and_sources。

        之前 node.py 的 deep_wrapper_node 把 setup 块 copy-paste 了两遍(2664-2682 一次,
        2684-2693 一次),导致 _build_skill_backend_and_sources 被双倍调,每次请求多 mkdtemp
        一个沙箱,第一个永远不清理。本测试锁住"setup 只跑一次",防止回退。

        改后版本里 _build_skill_backend_and_sources 应该恰好 1 次(整个 wrapper 一次);
        回退到旧版本时会变 2 次,本测试 fail 并报具体计数。
        """
        node = ToolsNodes()
        # _skill_package_capabilities 是 ToolsNodes 实例属性,deep_wrapper_node 路径会读,
        # 手动设一个空集合(测试不依赖具体 capability,只关心调用次数)
        node._skill_package_capabilities = set()
        node.all_tools = [_tool("shell")]
        req = _request()
        captured = {}

        fake_backend = MagicMock()
        call_counter = {"n": 0}

        def _counting_side_effect(*args, **kwargs):
            call_counter["n"] += 1
            return (fake_backend, ["/skills/"], None)

        with patch.object(ToolsNodes, "_build_knowledge_retrieve_tool", return_value=None), patch.object(
            ToolsNodes, "_build_skill_backend_and_sources", side_effect=_counting_side_effect
        ):
            self._run_wrapper(node, req, captured)

        assert call_counter["n"] == 1, (
            f"期望 deep_wrapper_node 整个 setup 期间 _build_skill_backend_and_sources " f"只调 1 次,实际 {call_counter['n']} 次。" f"S2 修复前为 2 次(setup 块被复制粘贴)。"
        )
        # 同时确认 kwargs 透传正确(防御 setup 块改坏后端到端数据流)
        kwargs = captured["create_kwargs"]
        assert kwargs["backend"] is fake_backend
        assert kwargs["skills"] == ["/skills/"]

    def test_planned_execution_keeps_hitl_tools_always_on_until_summary(self):
        node = ToolsNodes()
        node.all_tools = [
            _tool("list_kubernetes_events"),
            _tool("request_user_choice"),
            _tool("restart_pod"),
        ]
        req = _request(user_message="检查事件")
        captured = {}

        with patch.object(ToolsNodes, "_build_knowledge_retrieve_tool", return_value=None):
            self._run_wrapper(
                node,
                req,
                captured,
                plan_payload={
                    "goal": "检查事件",
                    "steps": [
                        {
                            "objective": "读取事件",
                            "tools": ["list_kubernetes_events"],
                        }
                    ],
                },
            )

        assert captured["visible_tool_calls"] == [
            ["list_kubernetes_events", "request_user_choice"],
            [],
        ]

    def test_progressive_disabled_skips_planner_and_binds_all_tools(self, monkeypatch):
        monkeypatch.setenv("OPSPILOT_DEEPAGENT_PROGRESSIVE_TOOLS", "0")
        assert is_progressive_tools_enabled() is False

        node = ToolsNodes()
        node.all_tools = [_tool("shell"), _tool("k8s")]
        req = _request(user_message="随便问问")
        captured = {}

        with patch.object(ToolsNodes, "_build_knowledge_retrieve_tool", return_value=None):
            self._run_wrapper(node, req, captured, plan_payload={"goal": "x", "steps": []})

        assert "planner_calls" not in captured
        assert [tool.name for tool in captured["create_kwargs"]["tools"]] == ["shell", "k8s"]
        middleware = captured["create_kwargs"].get("middleware") or []
        assert not any(isinstance(item, ToolVisibilityMiddleware) for item in middleware)
        assert len(captured["ainvoke_messages"]) == 1
        assert captured["ainvoke_messages"][0][0].content == "排查 pod 崩溃"
