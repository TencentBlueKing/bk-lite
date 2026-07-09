"""workflow AGUI 入口派发 wiki_citations 事件的行为锁定。

直接智能体入口由 ``agui_chat`` 补发 wiki_citations CUSTOM event；workflow 的
web 应用入口走 ``AgentNode.agui_execute``，也必须保持同样的前端事件契约。
"""

import asyncio
import json
from types import SimpleNamespace

from apps.opspilot.metis.llm.chain.entity import BasicLLMRequest
from apps.opspilot.utils.chat_flow_utils.nodes.agent.agent import AgentNode


def _parse_sse_lines(lines):
    payloads = []
    for line in lines:
        if not line.startswith("data: "):
            continue
        payloads.append(json.loads(line[6:].strip()))
    return payloads


class _FakeGraph:
    async def agui_stream(self, request):  # noqa: ARG002
        yield 'data: {"type": "RUN_FINISHED"}\n\n'


def _collect_agui_lines(node):
    async def _collect():
        lines = []
        async for line in node.agui_execute("agent-1", {"data": {"config": {}}}, {"last_message": "hi"}):
            lines.append(line)
        return lines

    return asyncio.run(_collect())


def test_workflow_agent_node_dispatches_wiki_citations(monkeypatch):
    citations = [{"n": 1, "kb_id": 10, "kind": "page", "id": 100, "title": "服务操作手册"}]
    llm_params = {
        "llm_model": 1,
        "show_think": False,
        "skill_type": "basic_tool",
        "group": 1,
    }

    monkeypatch.setattr(AgentNode, "set_llm_params", lambda *_args, **_kwargs: (llm_params.copy(), "测试技能", False))

    from apps.opspilot.utils.chat_flow_utils.nodes.agent import agent as agent_module

    monkeypatch.setattr(agent_module.LLMModel.objects, "get", lambda **_kwargs: SimpleNamespace(id=1))
    monkeypatch.setattr(
        agent_module.chat_service,
        "format_chat_server_kwargs",
        lambda _params, _llm_model: ({"extra_config": {"wiki_citations": citations}}, {}, {}),
    )
    monkeypatch.setattr(
        agent_module,
        "create_agent_instance",
        lambda _skill_type, chat_kwargs: (_FakeGraph(), BasicLLMRequest(extra_config=chat_kwargs["extra_config"])),
    )

    lines = _collect_agui_lines(AgentNode.__new__(AgentNode))
    payloads = _parse_sse_lines(lines)
    wiki_events = [payload for payload in payloads if payload.get("type") == "CUSTOM" and payload.get("name") == "wiki_citations"]

    assert len(wiki_events) == 1
    assert wiki_events[0]["value"] == {"citations": citations}
    assert payloads.index(wiki_events[0]) < next(i for i, payload in enumerate(payloads) if payload.get("type") == "RUN_FINISHED")


def test_workflow_agent_node_skips_empty_wiki_citations(monkeypatch):
    llm_params = {
        "llm_model": 1,
        "show_think": False,
        "skill_type": "basic_tool",
        "group": 1,
    }

    monkeypatch.setattr(AgentNode, "set_llm_params", lambda *_args, **_kwargs: (llm_params.copy(), "测试技能", False))

    from apps.opspilot.utils.chat_flow_utils.nodes.agent import agent as agent_module

    monkeypatch.setattr(agent_module.LLMModel.objects, "get", lambda **_kwargs: SimpleNamespace(id=1))
    monkeypatch.setattr(
        agent_module.chat_service,
        "format_chat_server_kwargs",
        lambda _params, _llm_model: ({"extra_config": {"wiki_citations": []}}, {}, {}),
    )
    monkeypatch.setattr(
        agent_module,
        "create_agent_instance",
        lambda _skill_type, chat_kwargs: (_FakeGraph(), BasicLLMRequest(extra_config=chat_kwargs["extra_config"])),
    )

    lines = _collect_agui_lines(AgentNode.__new__(AgentNode))
    payloads = _parse_sse_lines(lines)

    assert [payload for payload in payloads if payload.get("name") == "wiki_citations"] == []
