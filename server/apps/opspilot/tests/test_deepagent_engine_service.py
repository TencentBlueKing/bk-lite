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
    SkillExecutionGuardMiddleware,
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

    def test_metadata_approval_required_unions_named_tools(self):
        n = ToolsNodes()
        exec_tool = MagicMock()
        exec_tool.name = "exec_in_pod"
        exec_tool.metadata = {"approval": {"required": True}}
        req = _request(approval_config=SimpleNamespace(enabled=True, tools=["danger_tool"]))
        result = n._build_interrupt_on(req, [_tool("danger_tool"), exec_tool, _tool("safe_tool")])
        assert result == {"danger_tool": True, "exec_in_pod": True}

    def test_metadata_approval_required_ignored_when_approval_disabled(self):
        n = ToolsNodes()
        exec_tool = MagicMock()
        exec_tool.name = "exec_in_pod"
        exec_tool.metadata = {"approval": {"required": True}}
        req = _request(approval_config=SimpleNamespace(enabled=False, tools=[]))
        assert n._build_interrupt_on(req, [exec_tool]) is None

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
        ) as backend_cls, patch("apps.opspilot.services.skill_package.materializer.materialize_skill_package") as mat, patch.object(
            ToolsNodes, "_ensure_skill_deps"
        ) as ensure_deps:
            backend, sources, sandbox_dir = n._build_skill_backend_and_sources(_request())
        assert backend is not None
        assert sources == ["/skills/"]
        assert mat.call_count == 2
        # 建沙箱只物化目录,不预装依赖(寒暄不应 pip install)
        ensure_deps.assert_not_called()
        # 一次性沙箱目录被创建（用完即弃，由调用方清理）
        assert sandbox_dir and os.path.isdir(sandbox_dir)
        # 用的是 LocalShellBackend：虚拟根 + 不继承宿主环境
        _, kwargs = backend_cls.call_args
        assert kwargs["virtual_mode"] is True
        assert kwargs["inherit_env"] is False
        n._cleanup_sandbox(sandbox_dir)

    def test_skill_deps_install_only_when_skill_path_accessed(self):
        """读 /skills/<name>/SKILL.md 才装该包依赖;未访问不装。"""
        n = ToolsNodes()
        pkgs = [
            {"name": "kubernetes-specialist", "package_id": "kubernetes-specialist"},
            {"name": "pdf", "package_id": "pdf"},
        ]
        with patch.object(ToolsNodes, "_resolve_skill_packages", return_value=pkgs), patch(
            "deepagents.backends.LocalShellBackend", return_value=MagicMock()
        ), patch("apps.opspilot.services.skill_package.materializer.materialize_skill_package"), patch.object(
            ToolsNodes, "_ensure_skill_deps"
        ) as ensure_deps:
            backend, _, sandbox_dir = n._build_skill_backend_and_sources(_request())
            ensure_deps.assert_not_called()
            backend.read("/skills/kubernetes-specialist/SKILL.md")
            ensure_deps.assert_called_once()
            ensured = ensure_deps.call_args[0][0]
            assert len(ensured) == 1
            assert ensured[0]["name"] == "kubernetes-specialist"
            # 同一技能再次访问不重复装
            backend.read("/skills/kubernetes-specialist/scripts/foo.py")
            assert ensure_deps.call_count == 1
            # 另一个技能按需再装
            backend.execute("python3 /skills/pdf/create_pdf.py", timeout=5)
            assert ensure_deps.call_count == 2
            assert ensure_deps.call_args[0][0][0]["name"] == "pdf"
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
        allowed = {"PATH", "LANG", "LC_ALL", "TMPDIR", "HOME", "KUBECONFIG"}
        allowed.update(n._WINDOWS_SOCKET_ENV_KEYS)
        assert set(env).issubset(allowed)
        assert env["TMPDIR"] == "/tmp/run-xyz"
        if os.name == "nt":
            assert env.get("SystemRoot")
            assert "SYSTEMROOT" not in env
            assert env.get("TEMP") == "/tmp/run-xyz"
            assert env.get("TMP") == "/tmp/run-xyz"
            path_entries = env["PATH"].split(os.pathsep)
            assert any(p.lower().endswith("\\system32") or p.lower().endswith("/system32") for p in path_entries)

    def test_sandbox_env_can_create_socket(self):
        """精简沙箱 env 必须能初始化套接字。Windows 缺 SystemRoot 会 WinError 10106。"""
        n = ToolsNodes()
        env = n._sandbox_env(os.path.abspath("/tmp/run-socket"))
        completed = subprocess.run(
            [sys.executable, "-c", "import socket; socket.socket().close()"],
            env=env,
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert completed.returncode == 0, completed.stderr

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

        with patch.dict(os.environ, {"PATH": os.pathsep.join(["/usr/bin", "/bin"])}):
            env = n._sandbox_env("/tmp/run-python-path")

        path_entries = env["PATH"].split(os.pathsep)
        assert path_entries[0] == os.path.dirname(sys.executable)
        python_cmd = "python" if os.name == "nt" else "python3"
        completed = subprocess.run(
            [python_cmd, "-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"],
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


def test_should_use_lightweight_direct_reply():
    from apps.opspilot.metis.llm.chain.node import ToolsNodes

    assert ToolsNodes._should_use_lightweight_direct_reply([], []) is True
    assert ToolsNodes._should_use_lightweight_direct_reply([], None) is True
    assert ToolsNodes._should_use_lightweight_direct_reply([_tool("shell")], []) is False
    assert ToolsNodes._should_use_lightweight_direct_reply([], ["/skills/"]) is False


def test_should_use_lightweight_after_empty_plan():
    from apps.opspilot.metis.llm.agent.tool_execution_planner import ToolExecutionPlan, ToolExecutionStep
    from apps.opspilot.metis.llm.chain.node import ToolsNodes

    assert ToolsNodes._should_use_lightweight_after_empty_plan(ToolExecutionPlan(goal="hi", steps=[])) is True
    assert (
        ToolsNodes._should_use_lightweight_after_empty_plan(
            ToolExecutionPlan(goal="use skill", steps=[ToolExecutionStep(objective="读技能", tools=["__use_skills__"])])
        )
        is False
    )


def test_build_lightweight_system_prompt_is_short():
    from apps.opspilot.metis.llm.chain.node import ToolsNodes

    prompt = ToolsNodes._build_lightweight_system_prompt("你是运维助手")
    assert "你是运维助手" in prompt
    assert "DeepAgent" not in prompt
    assert "write_todos" not in prompt
    assert "read_file" not in prompt
    assert len(prompt) < 500
    with_skills = ToolsNodes._build_lightweight_system_prompt("你是运维助手", skills_available=True)
    assert "不需要调用工具或读取技能文件" in with_skills
    assert "当前没有可用工具与技能" not in with_skills


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
        direct_reply_content=None,
        agent_reply=None,
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
            appended_messages = [AIMessage(content=agent_reply or f"执行结果 {call_index}")]
            if call_index in failing_agent_calls:
                from langchain_core.messages import ToolMessage

                fail_spec = failing_agent_calls[call_index] if isinstance(failing_agent_calls, dict) else None
                if isinstance(fail_spec, dict):
                    tool_content = fail_spec.get("content", "connection refused")
                    tool_status = fail_spec.get("status", "error")
                    tool_name = fail_spec.get("name", "diagnose_kubernetes_pod_issues")
                else:
                    tool_content = "connection refused"
                    tool_status = "error"
                    tool_name = "diagnose_kubernetes_pod_issues"
                appended_messages.insert(
                    0,
                    ToolMessage(
                        content=tool_content,
                        name=tool_name,
                        tool_call_id=f"failed-{call_index}",
                        status=tool_status,
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
                captured.setdefault("llm_calls", []).append(messages)
                joined = "\n".join(str(getattr(message, "content", "") or "") for message in messages)
                is_planner = "工具执行规划器" in joined or "紧凑工具目录" in joined
                if is_planner:
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
                captured.setdefault("direct_reply_calls", []).append(messages)
                return AIMessage(
                    content=direct_reply_content or "轻量直答",
                    usage_metadata={
                        "input_tokens": 80,
                        "output_tokens": 10,
                        "total_tokens": 90,
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

    def test_lightweight_direct_reply_skips_planner_and_deepagent(self):
        node = ToolsNodes()
        node.all_tools = []
        req = _request(user_message="你好", system_message_prompt="你是助手")
        captured = {}

        with patch.object(ToolsNodes, "_build_knowledge_retrieve_tool", return_value=None), patch.object(
            ToolsNodes, "_build_skill_backend_and_sources", return_value=(None, [], None)
        ):
            result = self._run_wrapper(
                node,
                req,
                captured,
                direct_reply_content="你好！有什么可以帮你的？",
            )

        assert "create_kwargs" not in captured
        assert captured.get("planner_calls") in (None, [])
        assert len(captured["direct_reply_calls"]) == 1
        system_text = str(captured["direct_reply_calls"][0][0].content)
        assert "DeepAgent" not in system_text
        assert "read_file" not in system_text
        assert result["messages"][0].content == "你好！有什么可以帮你的？"

    def test_empty_plan_with_skill_packages_skips_deepagent(self):
        """已启用技能包但规划器返回空 steps（寒暄）时，不物化沙箱、不创建 DeepAgent。"""
        node = ToolsNodes()
        node.all_tools = []
        req = _request(user_message="你好")
        captured = {}
        pkgs = [{"name": "kubernetes-specialist", "description": "K8s 排障"}]

        with patch.object(ToolsNodes, "_build_knowledge_retrieve_tool", return_value=None), patch.object(
            ToolsNodes, "_resolve_skill_packages", return_value=pkgs
        ), patch.object(ToolsNodes, "_build_skill_backend_and_sources", return_value=(MagicMock(), ["/skills/"], None)) as build_skills:
            result = self._run_wrapper(
                node,
                req,
                captured,
                plan_payload={"goal": "问候", "steps": []},
                direct_reply_content="你好！",
            )

        assert "create_kwargs" not in captured
        build_skills.assert_not_called()
        assert len(captured["planner_calls"]) == 1
        planner_text = "\n".join(str(m.content) for m in captured["planner_calls"][0])
        assert "可用技能包" in planner_text
        assert "kubernetes-specialist" in planner_text
        assert len(captured["direct_reply_calls"]) == 1
        assert "不需要调用工具或读取技能文件" in str(captured["direct_reply_calls"][0][0].content)
        assert result["messages"][0].content == "你好！"

    def test_use_skills_step_materializes_sandbox_and_enables_fs(self):
        node = ToolsNodes()
        node.all_tools = []
        req = _request(user_message="用 kubernetes 技能排查 Pod")
        captured = {}
        pkgs = [{"name": "kubernetes-specialist", "description": "K8s 排障"}]
        fake_backend = MagicMock()

        with patch.object(ToolsNodes, "_build_knowledge_retrieve_tool", return_value=None), patch.object(
            ToolsNodes, "_resolve_skill_packages", return_value=pkgs
        ), patch.object(ToolsNodes, "_build_skill_backend_and_sources", return_value=(fake_backend, ["/skills/"], None)) as build_skills:
            self._run_wrapper(
                node,
                req,
                captured,
                plan_payload={
                    "goal": "排查 Pod",
                    "steps": [{"objective": "按技能执行", "tools": ["__use_skills__"]}],
                },
            )

        build_skills.assert_called_once()
        kwargs = captured["create_kwargs"]
        assert kwargs["backend"] is fake_backend
        assert kwargs["skills"] == ["/skills/"]
        visibility = next(m for m in kwargs["middleware"] if isinstance(m, ToolVisibilityMiddleware))
        # 纯技能步不再常驻整套 FS（避免每轮 ~7k schema），但必须把 execute
        # 放进 always_visible（仅 discard hidden 不够，allow_unregistered=False）。
        assert "read_file" not in visibility._always_visible_tools
        assert "execute" not in visibility._hidden_tools
        assert "execute" in visibility._always_visible_tools
        skill_guard = next(m for m in kwargs["middleware"] if isinstance(m, SkillExecutionGuardMiddleware))
        assert skill_guard.enabled is True

    def test_context_overflow_skips_current_step_and_continues_remaining(self):
        node = ToolsNodes()
        node.all_tools = [
            _tool("list_kubernetes_events"),
            _tool("get_kubernetes_pod_logs"),
            _tool("validate_probe_configuration"),
        ]
        req = _request(user_message="告警：Unhealthy startup probe")
        captured = {}

        gb = _FakeGraphBuilder()
        name = asyncio.run(node.build_deepagent_nodes(gb, composite_node_name="deep_agent"))
        wrapper = gb.nodes[name]

        from langchain_core.messages import AIMessage, HumanMessage

        class _OverflowLLM:
            async def ainvoke(self, messages, config=None):
                captured.setdefault("planner_calls", []).append(messages)
                return AIMessage(
                    content=json.dumps(
                        {
                            "goal": "诊断",
                            "steps": [
                                {"objective": "查日志与事件", "tools": ["get_kubernetes_pod_logs", "list_kubernetes_events"]},
                                {"objective": "验证探针配置", "tools": ["validate_probe_configuration"]},
                            ],
                        },
                        ensure_ascii=False,
                    )
                )

        fake_agent = MagicMock()

        async def _ainvoke(payload, config=None):
            captured.setdefault("agent_calls", 0)
            captured["agent_calls"] += 1
            joined = "\n".join(str(getattr(m, "content", "") or "") for m in payload["messages"])
            captured.setdefault("ainvoke_joined", []).append(joined)
            if captured["agent_calls"] == 1:
                raise Exception(
                    "BadRequestError: Error code: 400 - "
                    "{'error': {'message': 'request (9132 tokens) exceeds the available context size (8192 tokens)', "
                    "'type': 'exceed_context_size_error'}}"
                )
            return {
                **payload,
                "messages": list(payload["messages"]) + [AIMessage(content=f"执行结果 {captured['agent_calls']}")],
            }

        fake_agent.ainvoke = _ainvoke

        with patch("apps.opspilot.metis.llm.chain.node.create_deep_agent", return_value=fake_agent), patch.object(
            ToolsNodes, "get_llm_client", return_value=_OverflowLLM()
        ), patch.object(ToolsNodes, "_build_knowledge_retrieve_tool", return_value=None), patch.object(
            ToolsNodes, "_build_skill_backend_and_sources", return_value=(None, [], None)
        ):
            result = asyncio.run(
                wrapper(
                    {"messages": [HumanMessage(content="告警：Unhealthy")]},
                    {"configurable": {"graph_request": req}},
                )
            )

        # 规划 1 次；第 1 步溢出后不重规划，压缩上下文后继续第 2 步，再走总结
        assert len(captured["planner_calls"]) == 1
        assert captured["agent_calls"] == 3
        assert "上下文压缩" in captured["ainvoke_joined"][1]
        assert result["messages"][-1].content == "执行结果 3"

    def test_successful_step_compacts_history_before_next_step(self):
        node = ToolsNodes()
        node.all_tools = [
            _tool("resolve_k8s_target_from_alert"),
            _tool("diagnose_kubernetes_pod_issues"),
        ]
        req = _request(user_message="告警：Unhealthy startup probe")
        captured = {}

        gb = _FakeGraphBuilder()
        name = asyncio.run(node.build_deepagent_nodes(gb, composite_node_name="deep_agent"))
        wrapper = gb.nodes[name]

        from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

        class _PlanLLM:
            async def ainvoke(self, messages, config=None):
                captured.setdefault("planner_calls", []).append(messages)
                return AIMessage(
                    content=json.dumps(
                        {
                            "goal": "诊断",
                            "steps": [
                                {"objective": "反查命名空间", "tools": ["resolve_k8s_target_from_alert"]},
                                {"objective": "诊断 Pod", "tools": ["diagnose_kubernetes_pod_issues"]},
                            ],
                        },
                        ensure_ascii=False,
                    )
                )

        fake_agent = MagicMock()

        async def _ainvoke(payload, config=None):
            captured.setdefault("agent_calls", 0)
            captured["agent_calls"] += 1
            joined = "\n".join(str(getattr(m, "content", "") or "") for m in payload["messages"])
            captured.setdefault("ainvoke_joined", []).append(joined)
            if captured["agent_calls"] == 1:
                return {
                    **payload,
                    "messages": list(payload["messages"])
                    + [
                        ToolMessage(content="HUGE_TOOL_RESULT_" + ("x" * 8000), tool_call_id="t1", name="resolve_k8s_target_from_alert"),
                        AIMessage(content="已解析 namespace=bk-lite"),
                    ],
                }
            return {
                **payload,
                "messages": list(payload["messages"]) + [AIMessage(content=f"执行结果 {captured['agent_calls']}")],
            }

        fake_agent.ainvoke = _ainvoke

        with patch("apps.opspilot.metis.llm.chain.node.create_deep_agent", return_value=fake_agent), patch.object(
            ToolsNodes, "get_llm_client", return_value=_PlanLLM()
        ), patch.object(ToolsNodes, "_build_knowledge_retrieve_tool", return_value=None), patch.object(
            ToolsNodes, "_build_skill_backend_and_sources", return_value=(None, [], None)
        ):
            asyncio.run(
                wrapper(
                    {"messages": [HumanMessage(content="告警：Unhealthy")]},
                    {"configurable": {"graph_request": req}},
                )
            )

        assert captured["agent_calls"] == 3
        assert "步骤摘要" in captured["ainvoke_joined"][1]
        assert "HUGE_TOOL_RESULT_" not in captured["ainvoke_joined"][1]
        assert "步骤摘要" in captured["ainvoke_joined"][2] or "工具执行计划目标" in captured["ainvoke_joined"][2]

    def test_runtime_middleware_includes_tool_result_compaction(self):
        from apps.opspilot.metis.llm.middleware.context_window import ContextWindowMiddleware
        from apps.opspilot.metis.llm.middleware.tool_runtime import ToolResultCompactionMiddleware

        node = ToolsNodes()
        node.all_tools = [_tool("list_kubernetes_events")]
        req = _request(user_message="查事件")
        captured = {}
        with patch.object(ToolsNodes, "_build_knowledge_retrieve_tool", return_value=None):
            self._run_wrapper(
                node,
                req,
                captured,
                plan_payload={
                    "goal": "查事件",
                    "steps": [{"objective": "读事件", "tools": ["list_kubernetes_events"]}],
                },
            )
        middlewares = captured["create_kwargs"]["middleware"]
        assert any(isinstance(item, ToolResultCompactionMiddleware) for item in middlewares)
        assert any(isinstance(item, ContextWindowMiddleware) for item in middlewares)

    def test_planned_step_prepare_passes_active_tools(self):
        seen_tool_names = []

        async def _spy(self, messages, graph_request, *, tools=None):
            seen_tool_names.append([getattr(tool, "name", "") for tool in (tools or [])])
            return list(messages or [])

        node = ToolsNodes()
        node.all_tools = [_tool("list_kubernetes_events")]
        req = _request(user_message="查事件")
        captured = {}
        with patch.object(ToolsNodes, "_prepare_messages_for_llm", _spy), patch.object(
            ToolsNodes, "_build_knowledge_retrieve_tool", return_value=None
        ):
            self._run_wrapper(
                node,
                req,
                captured,
                plan_payload={
                    "goal": "查事件",
                    "steps": [{"objective": "读事件", "tools": ["list_kubernetes_events"]}],
                },
            )
        assert any("list_kubernetes_events" in names for names in seen_tool_names)

    def test_passes_tools_and_returns_only_new_messages(self):
        node = ToolsNodes()
        node.all_tools = [_tool("shell")]
        req = _request()
        captured = {}
        with patch.object(ToolsNodes, "_build_knowledge_retrieve_tool", return_value=None):
            result = self._run_wrapper(
                node,
                req,
                captured,
                plan_payload={
                    "goal": "排查",
                    "steps": [{"objective": "执行命令", "tools": ["shell"]}],
                },
            )
        kwargs = captured["create_kwargs"]
        assert kwargs["model"].__class__.__name__ == "_FakeLLM"
        assert [t.name for t in kwargs["tools"]] == ["shell"]
        assert "system_prompt" in kwargs
        # 无技能/审批时不传 backend/skills/interrupt_on
        assert "backend" not in kwargs
        assert "skills" not in kwargs
        assert "interrupt_on" not in kwargs
        # 只返回 deepagent 新增消息（执行步 + 总结轮）
        assert len(result["messages"]) == 2
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
        from apps.opspilot.metis.llm.middleware.planned_execution_limits import PlannedExecutionLimitMiddleware

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
        # 无技能包时不常驻 FS 工具，避免 8K 模型被 read_file/ls schema 撑爆。
        assert "read_file" not in visibility._always_visible_tools
        assert captured["visible_tool_calls"] == [
            ["list_kubernetes_events"],
            [],
        ]
        call_limit = next(middleware for middleware in kwargs["middleware"] if isinstance(middleware, PlannedExecutionLimitMiddleware))
        assert call_limit.run_limit == 10
        assert call_limit.token_budget == 0
        assert call_limit.enforce_limits is False  # 总结轮关闭硬限制

    def test_tool_failure_replans_only_unfinished_steps(self):
        # 不用 namespace 反查类工具，避免规划硬校验改写步骤顺序。
        node = ToolsNodes()
        node.all_tools = [
            _tool("current_time"),
            _tool("diagnose_kubernetes_pod_issues"),
            _tool("validate_probe_configuration"),
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
                        "goal": "改验探针配置",
                        "steps": [
                            {
                                "objective": "验证探针配置",
                                "tools": ["validate_probe_configuration"],
                            }
                        ],
                    },
                ],
                failing_agent_calls={2},
            )

        assert captured["visible_tool_calls"] == [
            ["current_time"],
            ["diagnose_kubernetes_pod_issues"],
            ["validate_probe_configuration"],
            [],
        ]
        assert len(captured["planner_calls"]) == 2
        replan_prompt = "\n".join(str(message.content) for message in captured["planner_calls"][1])
        assert "确认时间: 执行结果 1" in replan_prompt
        assert "connection refused" in replan_prompt

    def test_replan_keeps_unfinished_followup_steps(self):
        node = ToolsNodes()
        node.all_tools = [
            _tool("normalize_alert_event"),
            _tool("diagnose_node_issues"),
            _tool("list_kubernetes_nodes"),
            _tool("check_pvc_capacity"),
        ]
        req = _request(user_message="诊断节点磁盘不可调度")
        captured = {}

        with patch.object(ToolsNodes, "_build_knowledge_retrieve_tool", return_value=None):
            self._run_wrapper(
                node,
                req,
                captured,
                plan_payloads=[
                    {
                        "goal": "诊断节点磁盘",
                        "steps": [
                            {"objective": "解析告警", "tools": ["normalize_alert_event"]},
                            {"objective": "检查节点", "tools": ["diagnose_node_issues"]},
                            {"objective": "检查 PVC", "tools": ["check_pvc_capacity"]},
                        ],
                    },
                    {
                        "goal": "先确认节点是否存在",
                        "steps": [
                            {"objective": "获取集群节点列表", "tools": ["list_kubernetes_nodes"]},
                        ],
                    },
                ],
                failing_agent_calls={
                    2: {
                        "content": '{"error": "Node不存在: k3s-worker02"}',
                        "status": "success",
                        "name": "diagnose_node_issues",
                    }
                },
            )

        assert captured["visible_tool_calls"] == [
            ["normalize_alert_event"],
            ["diagnose_node_issues"],
            ["list_kubernetes_nodes"],
            ["check_pvc_capacity"],
            [],
        ]
        assert len(captured["planner_calls"]) == 2

    def test_json_tool_error_payload_triggers_replan(self):
        # 不用 list_kubernetes_pods：避免规划硬校验前置反查，干扰「JSON error → replan」断言。
        node = ToolsNodes()
        node.all_tools = [
            _tool("diagnose_kubernetes_pod_issues"),
            _tool("validate_probe_configuration"),
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
                            {
                                "objective": "诊断 Pod",
                                "tools": ["diagnose_kubernetes_pod_issues"],
                            },
                        ],
                    },
                    {
                        "goal": "改验探针配置",
                        "steps": [
                            {
                                "objective": "验证探针配置",
                                "tools": ["validate_probe_configuration"],
                            }
                        ],
                    },
                ],
                failing_agent_calls={
                    1: {
                        "content": '{"error": "Pod server-x 在命名空间 default 中不存在"}',
                        "status": "success",
                        "name": "diagnose_kubernetes_pod_issues",
                    }
                },
            )

        assert captured["visible_tool_calls"] == [
            ["diagnose_kubernetes_pod_issues"],
            ["validate_probe_configuration"],
            [],
        ]
        assert len(captured["planner_calls"]) == 2
        replan_prompt = "\n".join(str(message.content) for message in captured["planner_calls"][1])
        assert "不存在" in replan_prompt

    def test_auth_tool_error_aborts_remaining_steps_without_replan(self):
        node = ToolsNodes()
        node.all_tools = [
            _tool("diagnose_kubernetes_pod_issues"),
            _tool("validate_probe_configuration"),
        ]
        req = _request(user_message="定位 Pod 告警")
        captured = {}

        with patch.object(ToolsNodes, "_build_knowledge_retrieve_tool", return_value=None):
            result = self._run_wrapper(
                node,
                req,
                captured,
                plan_payload={
                    "goal": "定位 Pod 告警",
                    "steps": [
                        {
                            "objective": "诊断 Pod",
                            "tools": ["diagnose_kubernetes_pod_issues"],
                        },
                        {
                            "objective": "验证探针配置",
                            "tools": ["validate_probe_configuration"],
                        },
                    ],
                },
                failing_agent_calls={
                    1: {
                        "content": '{"error": "获取Pod列表失败: (401)\\nReason: Unauthorized"}',
                        "status": "success",
                        "name": "diagnose_kubernetes_pod_issues",
                    }
                },
                agent_reply="kubeconfig 鉴权失败，请检查 Token 或证书后重试。",
            )

        assert captured["visible_tool_calls"] == [
            ["diagnose_kubernetes_pod_issues"],
        ]
        assert len(captured["planner_calls"]) == 1
        joined = "\n".join(str(getattr(message, "content", "") or "") for message in result["messages"])
        assert "401" in joined or "鉴权" in joined or "Unauthorized" in joined

    def test_unresolved_k8s_target_skips_namespace_required_followup_without_replan(self):
        node = ToolsNodes()
        node.all_tools = [
            _tool("resolve_k8s_target_from_alert"),
            _tool("diagnose_kubernetes_pod_issues"),
            _tool("generate_attachment_file"),
        ]
        req = _request(user_message="告警：Unhealthy server-69bf94649c-b8szc")
        captured = {}
        unresolved = json.dumps(
            {
                "cluster": "bk-lite-k3s",
                "namespace": None,
                "resource_type": "pod",
                "resource_name": "server-69bf94649c-b8szc",
                "resolved": False,
                "lookup_exhausted": True,
                "conclusive": True,
                "missing_data": ["namespace"],
                "reason": "Namespace not found for resource server-69bf94649c-b8szc via pods/events lookup",
            },
            ensure_ascii=False,
        )

        with patch.object(ToolsNodes, "_build_knowledge_retrieve_tool", return_value=None):
            self._run_wrapper(
                node,
                req,
                captured,
                plan_payload={
                    "goal": "定位 Pod 告警",
                    "steps": [
                        {
                            "objective": "反查命名空间",
                            "tools": ["resolve_k8s_target_from_alert"],
                        },
                        {
                            "objective": "诊断 Pod",
                            "tools": ["diagnose_kubernetes_pod_issues"],
                        },
                        {
                            "objective": "写报告",
                            "tools": ["generate_attachment_file"],
                        },
                    ],
                },
                failing_agent_calls={
                    1: {
                        "content": unresolved,
                        "status": "success",
                        "name": "resolve_k8s_target_from_alert",
                    }
                },
                agent_reply="当前集群无法定位该对象。",
            )

        assert captured["visible_tool_calls"] == [
            ["resolve_k8s_target_from_alert"],
            ["generate_attachment_file"],
            [],
        ]
        assert len(captured["planner_calls"]) == 1

    def test_permission_tool_error_aborts_without_replan(self):
        node = ToolsNodes()
        node.all_tools = [
            _tool("list_kubernetes_deployments"),
            _tool("analyze_deployment_configurations"),
        ]
        req = _request(user_message="检查部署配置")
        captured = {}

        with patch.object(ToolsNodes, "_build_knowledge_retrieve_tool", return_value=None):
            self._run_wrapper(
                node,
                req,
                captured,
                plan_payload={
                    "goal": "检查部署配置",
                    "steps": [
                        {
                            "objective": "列出 Deployment",
                            "tools": ["list_kubernetes_deployments"],
                        },
                        {
                            "objective": "分析配置",
                            "tools": ["analyze_deployment_configurations"],
                        },
                    ],
                },
                failing_agent_calls={
                    1: {
                        "content": '{"error": "获取Deployment列表失败: (403)\\nReason: Forbidden"}',
                        "status": "success",
                        "name": "list_kubernetes_deployments",
                    }
                },
            )

        assert captured["visible_tool_calls"] == [
            ["list_kubernetes_deployments"],
            [],
        ]
        assert len(captured["planner_calls"]) == 1

    def test_internal_tool_exception_aborts_without_replan(self):
        node = ToolsNodes()
        node.all_tools = [
            _tool("list_kubernetes_nodes"),
            _tool("diagnose_kubernetes_pod_issues"),
        ]
        req = _request(user_message="列出节点")
        captured = {}

        with patch.object(ToolsNodes, "_build_knowledge_retrieve_tool", return_value=None):
            self._run_wrapper(
                node,
                req,
                captured,
                plan_payload={
                    "goal": "列出节点",
                    "steps": [
                        {"objective": "列出节点", "tools": ["list_kubernetes_nodes"]},
                        {
                            "objective": "诊断 Pod",
                            "tools": ["diagnose_kubernetes_pod_issues"],
                        },
                    ],
                },
                failing_agent_calls={
                    1: {
                        "content": "AttributeError: 'NoneType' object has no attribute 'items'",
                        "status": "error",
                        "name": "list_kubernetes_nodes",
                    }
                },
            )

        assert captured["visible_tool_calls"] == [
            ["list_kubernetes_nodes"],
            [],
        ]
        assert len(captured["planner_calls"]) == 1

    def test_skill_auth_error_aborts_remaining_steps_without_replan(self):
        node = ToolsNodes()
        node.all_tools = []
        req = _request(user_message="查 AD 用户")
        captured = {}
        pkgs = [{"name": "ad-domain-ops", "package_id": "ad-domain-ops", "description": "AD"}]
        fake_backend = MagicMock()

        with patch.object(ToolsNodes, "_build_knowledge_retrieve_tool", return_value=None), patch.object(
            ToolsNodes, "_resolve_skill_packages", return_value=pkgs
        ), patch.object(ToolsNodes, "_build_skill_backend_and_sources", return_value=(fake_backend, ["/skills/"], None)):
            result = self._run_wrapper(
                node,
                req,
                captured,
                plan_payload={
                    "goal": "查 AD 用户",
                    "steps": [
                        {"objective": "查用户", "tools": ["__use_skills__"]},
                        {"objective": "查组", "tools": ["__use_skills__"]},
                    ],
                },
                failing_agent_calls={
                    1: {
                        "content": ('{"ok":false,"error":"invalid credentials"}\n' "[OPSPILOT_SKILL_RESULT] 脚本失败。最多修正参数后重试 1 次。"),
                        "status": "success",
                        "name": "execute",
                    }
                },
                agent_reply="LDAP 凭据无效，请检查技能包连接配置后重试。",
            )

        assert captured["visible_tool_calls"] == [["execute"]]
        assert len(captured["planner_calls"]) == 1
        joined = "\n".join(str(getattr(message, "content", "") or "") for message in result["messages"])
        assert "invalid credentials" in joined or "凭据" in joined

    def test_wires_skills_and_approval_when_configured(self):
        node = ToolsNodes()
        node.all_tools = [_tool("shell")]
        req = _request(approval_config=SimpleNamespace(enabled=True, tools=["shell"]))
        captured = {}
        fake_backend = MagicMock()
        pkgs = [{"name": "kubernetes-specialist", "description": "K8s"}]
        with patch.object(ToolsNodes, "_build_knowledge_retrieve_tool", return_value=None), patch.object(
            ToolsNodes, "_resolve_skill_packages", return_value=pkgs
        ), patch.object(ToolsNodes, "_build_skill_backend_and_sources", return_value=(fake_backend, ["/skills/"], None)):
            self._run_wrapper(
                node,
                req,
                captured,
                plan_payload={
                    "goal": "按技能排查",
                    "steps": [{"objective": "读技能并执行", "tools": ["__use_skills__", "shell"]}],
                },
            )
        kwargs = captured["create_kwargs"]
        assert kwargs["backend"] is fake_backend
        assert kwargs["skills"] == ["/skills/"]
        assert kwargs["interrupt_on"] == {"shell": True}

    def test_build_skill_backend_and_sources_called_only_once_per_run(self):
        """S2 回归测试:每次 deepagent 流只调一次 _build_skill_backend_and_sources。

        之前 node.py 的 deep_wrapper_node 把 setup 块 copy-paste 了两遍(2664-2682 一次,
        2684-2693 一次),导致 _build_skill_backend_and_sources 被双倍调,每次请求多 mkdtemp
        一个沙箱,第一个永远不清理。本测试锁住"setup 只跑一次",防止回退。

        改后版本里 _build_skill_backend_and_sources 应在规划需要技能运行时时恰好 1 次;
        回退到旧版本时会变 2 次,本测试 fail 并报具体计数。
        """
        node = ToolsNodes()
        # _skill_package_capabilities 是 ToolsNodes 实例属性,deep_wrapper_node 路径会读,
        # 手动设一个空集合(测试不依赖具体 capability,只关心调用次数)
        node._skill_package_capabilities = set()
        node.all_tools = [_tool("shell")]
        req = _request()
        captured = {}
        pkgs = [{"name": "kubernetes-specialist", "description": "K8s"}]

        fake_backend = MagicMock()
        call_counter = {"n": 0}

        def _counting_side_effect(*args, **kwargs):
            call_counter["n"] += 1
            return (fake_backend, ["/skills/"], None)

        with patch.object(ToolsNodes, "_build_knowledge_retrieve_tool", return_value=None), patch.object(
            ToolsNodes, "_resolve_skill_packages", return_value=pkgs
        ), patch.object(ToolsNodes, "_build_skill_backend_and_sources", side_effect=_counting_side_effect):
            self._run_wrapper(
                node,
                req,
                captured,
                plan_payload={
                    "goal": "按技能排查",
                    "steps": [{"objective": "读技能", "tools": ["__use_skills__"]}],
                },
            )

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

    def test_planned_execution_skips_summary_when_step_already_showed_table(self):
        node = ToolsNodes()
        node.all_tools = [_tool("execute")]
        req = _request(user_message="查询域控前10个用户")
        captured = {}
        table = "已成功查询\n\n| 序号 | sAMAccountName |\n| --- | --- |\n| 1 | Administrator |"

        with patch.object(ToolsNodes, "_build_knowledge_retrieve_tool", return_value=None):
            result = self._run_wrapper(
                node,
                req,
                captured,
                plan_payload={
                    "goal": "查用户",
                    "steps": [{"objective": "调用 AD 技能包", "tools": ["execute"]}],
                },
                agent_reply=table,
            )

        assert len(captured["ainvoke_messages"]) == 1
        assert len(result["messages"]) == 1
        assert result["messages"][0].content == table

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


def test_planned_step_already_answered_detects_markdown_table():
    from langchain_core.messages import AIMessage, ToolMessage

    table = "已成功查询\n\n| 序号 | sAMAccountName |\n| --- | --- |\n| 1 | Administrator |"
    assert ToolsNodes._planned_step_already_answered([AIMessage(content=table)]) is True
    assert ToolsNodes._planned_step_already_answered([AIMessage(content="执行结果 1")]) is False
    assert ToolsNodes._planned_step_already_answered([ToolMessage(content=table, tool_call_id="t1")]) is False


def test_planned_step_already_answered_detects_tool_sentence():
    from langchain_core.messages import AIMessage

    answer = "当前时间是 **2026-08-18 17:54:29**（默认时区：Asia/Shanghai）。"
    tool_call = AIMessage(content="", tool_calls=[{"id": "1", "name": "get_current_time", "args": {}}])
    assert ToolsNodes._planned_step_already_answered([tool_call, AIMessage(content=answer)]) is True
    assert ToolsNodes._planned_step_already_answered([tool_call]) is False


def test_plan_is_skills_only_and_step_guidance():
    from apps.opspilot.metis.llm.agent.tool_execution_planner import ToolExecutionPlan, ToolExecutionStep

    skills_only = ToolExecutionPlan(
        goal="查 AD",
        steps=[ToolExecutionStep(objective="跑技能", tools=["__use_skills__"])],
    )
    mixed = ToolExecutionPlan(
        goal="查 AD",
        steps=[ToolExecutionStep(objective="跑技能", tools=["__use_skills__", "shell"])],
    )
    assert ToolsNodes._plan_is_skills_only(skills_only) is True
    assert ToolsNodes._plan_is_skills_only(mixed) is False
    guidance = ToolsNodes._skill_only_step_guidance([{"package_id": "ad-domain-ops"}])
    assert "禁止 echo" in guidance or "禁止" in guidance
    assert "/skills/ad-domain-ops/scripts/" in guidance
    assert "一张表" in guidance
    assert "禁止发明" in guidance
    assert "--help" in guidance
    assert "管道" in guidance
    assert "不要重试" in guidance or "凭据" in guidance


def test_planned_tool_step_guidance_is_policy_not_skill_scan():
    guidance = ToolsNodes._planned_tool_step_guidance()
    assert "【工具执行】" in guidance
    assert "未计划工具" in guidance
    assert "空列表" in guidance
    assert "重规划" in guidance
    assert "第二份" in guidance
    assert "execute" not in guidance
    assert "扫技能包" not in guidance


def test_skill_only_step_guidance_lists_real_scripts(tmp_path):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "ad_search.py").write_text("# search\n", encoding="utf-8")
    (scripts / "_lib.py").write_text("# private\n", encoding="utf-8")
    guidance = ToolsNodes._skill_only_step_guidance(
        [{"package_id": "ad-domain-ops", "extracted_root": tmp_path}],
    )
    assert "python3 /skills/ad-domain-ops/scripts/ad_search.py" in guidance
    assert "_lib.py" not in guidance
    assert "query_users.py" not in guidance
