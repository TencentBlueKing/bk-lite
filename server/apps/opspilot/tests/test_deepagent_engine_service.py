"""DeepAgent 统一引擎接线单测（service 层，全程 mock，无 DB/网络/真实 LLM）。

覆盖 ToolsNodes.build_deepagent_nodes 及其辅助方法如何把 BK-Lite 的
tools/MCP、knowledge_retrieve 工具、SKILL.md 技能（MinIO backend）、人工审批
（interrupt_on）真实接入 deepagents.create_deep_agent，以及 AG-UI 内置工具过滤。
"""

import asyncio
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.opspilot.metis.llm.chain.node import ToolsNodes


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
        ) as backend_cls, patch(
            "apps.opspilot.services.skill_package.materializer.materialize_skill_package"
        ) as mat:
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
        assert set(env).issubset({"PATH", "LANG", "LC_ALL", "TMPDIR", "HOME"})
        assert env["TMPDIR"] == "/tmp/run-xyz"

    def test_cleanup_sandbox_removes_dir(self):
        import tempfile

        n = ToolsNodes()
        d = tempfile.mkdtemp(prefix="run-")
        assert os.path.isdir(d)
        n._cleanup_sandbox(d)
        assert not os.path.exists(d)
        n._cleanup_sandbox(None)  # None 安全


class _FakeGraphBuilder:
    def __init__(self):
        self.nodes = {}

    def add_node(self, name, fn):
        self.nodes[name] = fn


class TestBuildDeepagentNodes:
    def _run_wrapper(self, node, req, captured):
        gb = _FakeGraphBuilder()

        async def _build():
            return await node.build_deepagent_nodes(gb, composite_node_name="react_agent")

        name = asyncio.get_event_loop().run_until_complete(_build())
        wrapper = gb.nodes[name]

        from langchain_core.messages import AIMessage, HumanMessage

        input_messages = [HumanMessage(content="排查 pod 崩溃")]

        fake_agent = MagicMock()

        async def _ainvoke(payload, config=None):
            captured["ainvoke_messages"] = payload["messages"]
            return {"messages": list(payload["messages"]) + [AIMessage(content="已定位")]}

        fake_agent.ainvoke = _ainvoke

        def _create(**kwargs):
            captured["create_kwargs"] = kwargs
            return fake_agent

        with patch("apps.opspilot.metis.llm.chain.node.create_deep_agent", side_effect=_create), patch.object(
            ToolsNodes, "get_llm_client", return_value="LLM"
        ):
            config = {"configurable": {"graph_request": req}}
            result = asyncio.get_event_loop().run_until_complete(wrapper({"messages": input_messages}, config))
        return result

    def test_passes_tools_and_returns_only_new_messages(self):
        node = ToolsNodes()
        node.all_tools = [_tool("shell")]
        req = _request()
        captured = {}
        with patch.object(ToolsNodes, "_build_knowledge_retrieve_tool", return_value=None):
            result = self._run_wrapper(node, req, captured)
        kwargs = captured["create_kwargs"]
        assert kwargs["model"] == "LLM"
        assert [t.name for t in kwargs["tools"]] == ["shell"]
        assert "system_prompt" in kwargs
        # 无技能/审批时不传 backend/skills/interrupt_on
        assert "backend" not in kwargs
        assert "skills" not in kwargs
        assert "interrupt_on" not in kwargs
        # 只返回 deepagent 新增消息
        assert len(result["messages"]) == 1
        assert result["messages"][0].content == "已定位"

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
