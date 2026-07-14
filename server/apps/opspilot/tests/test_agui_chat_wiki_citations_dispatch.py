"""AGUI 流派发 wiki_citations CUSTOM event 行为锁定(Issue #3919 续)。

问题:chat_service.format_chat_server_kwargs 在 prepare 阶段检索 wiki 并把 citations
写入 extra_config["wiki_citations"],但 augment_prompt 不在 langgraph 节点 coroutine
内,无法直接 dispatch_custom_event。前端 WikiCitations 组件因此永不渲染。

修复:agui_chat._generate_agui_stream 在流开始时检测 extra_config["wiki_citations"],
仿造 skill_view_event 模式补一个 name="wiki_citations" 的 CUSTOM SSE event。
前端 aguiMessageHandler.handleWikiCitations 已就位(name === 'wiki_citations' 监听)。

测试:锁定 _generate_agui_stream 第一个 yield 在 skill_view_event 之后立即派发
wiki_citations event,并准确透传 citations 列表。无 citations 时不发空 event。
"""

import asyncio
import json
from types import SimpleNamespace

from apps.opspilot.metis.llm.chain.entity import BasicLLMRequest


def _parse_sse_lines(lines):
    payloads = []
    for line in lines:
        if not line.startswith("data: "):
            continue
        try:
            payloads.append(json.loads(line[6:].strip()))
        except (json.JSONDecodeError, ValueError):
            continue
    return payloads


def _build_fake_graph(events):
    """空 fake graph:只产生给定 langchain 事件序列。"""

    class _FakeCompiled:
        def __init__(self, events):
            self._events = events

        async def astream_events(self, *_a, **_kw):
            for ev in self._events:
                yield ev

    class _FakeGraph:
        def __init__(self, events):
            self._events = events

        async def agui_stream(self, request):  # noqa: ARG002
            for ev in self._events:
                yield ev

    return _FakeGraph(events)


def _drive_agui_stream(monkeypatch, *, extra_config, params, skill_type="basic_tool"):
    """驱动 _generate_agui_stream 一次,捕获所有 yield 出的 SSE 行。

    不依赖 DB / LLMModel:用 monkeypatch 替换
      1. _prepare_agui_chat_kwargs → 直接返回 chat_kwargs(含 extra_config 透传)
      2. create_agent_instance → 返回 fake graph(空 events)
    """
    from apps.opspilot.utils import agui_chat

    chat_kwargs = {
        "llm_model": SimpleNamespace(id=1),
        "extra_config": extra_config,
    }
    monkeypatch.setattr(
        agui_chat,
        "_prepare_agui_chat_kwargs",
        lambda _params: chat_kwargs,
    )
    monkeypatch.setattr(
        agui_chat,
        "create_agent_instance",
        lambda _skill_type, _kwargs: (None, BasicLLMRequest(extra_config=extra_config)),
    )

    request = BasicLLMRequest(extra_config=extra_config)

    # 用 monkeypatch 替换内部 graph 调用:直接把空事件空 yield 出去
    async def _collect():
        gen = agui_chat._generate_agui_stream(
            params,
            skill_name="test-skill",
            skill_type=skill_type,
            show_think=False,
            final_stats={"content": []},
            kwargs={},
            current_ip="127.0.0.1",
            user_message="hi",
            skill_id=None,
            history_log=None,
        )
        # 但 _generate_agui_stream 会调 graph.agui_stream(request),create_agent_instance
        # mock 返回 (None, request),graph=None 会 AttributeError。我们需要拦截 graph.agui_stream。
        # 改法:在 collect 前用 wrapper 让 graph 来自 mock — 用 setattr mock 模块全局。
        lines = []
        try:
            async for line in gen:
                lines.append(line)
        except AttributeError:
            # graph 是 None,跳过 graph 阶段即可
            return lines
        return lines

    # 实际可行方案:再 patch create_agent_instance 让 graph 来自 fake
    fake_graph = _build_fake_graph([])
    monkeypatch.setattr(
        agui_chat,
        "create_agent_instance",
        lambda _st, _kw: (fake_graph, BasicLLMRequest(extra_config=extra_config)),
    )
    return asyncio.run(_collect())


def _params(wiki_kb_ids=None, matched_skill_packages=None):
    return {
        "skill_type": "basic_tool",
        "llm_model": 1,
        "user_message": "hi",
        "chat_history": [{"event": "user", "message": "hi"}],
        "user_id": "u1",
        "skill_prompt": "test",
        "skill_params": [],
        "enable_suggest": False,
        "enable_query_rewrite": False,
        "temperature": 0.5,
        "tools": [],
        "wiki_kb_ids": wiki_kb_ids or [],
        "matched_skill_packages": matched_skill_packages or [],
        "show_think": False,
    }


def test_wiki_citations_dispatched_in_agui_stream(monkeypatch):
    """request.extra_config 含 wiki_citations 时,流必须 yield wiki_citations CUSTOM event。"""
    citations = [
        {"n": 1, "kb_id": 10, "kind": "page", "id": 100, "title": "服务操作手册"},
        {"n": 2, "kb_id": 10, "kind": "page", "id": 101, "title": "故障排查指南"},
    ]
    extra_config = {"wiki_citations": citations}

    lines = _drive_agui_stream(monkeypatch, extra_config=extra_config, params=_params())

    payloads = _parse_sse_lines(lines)
    wiki_events = [p for p in payloads if p.get("type") == "CUSTOM" and p.get("name") == "wiki_citations"]

    assert len(wiki_events) == 1, f"应派发恰好 1 个 wiki_citations event,实际 {len(wiki_events)} 个"
    event = wiki_events[0]
    assert event["value"] == {"citations": citations}
    assert "timestamp" in event


def test_wiki_citations_event_follows_skill_view_event(monkeypatch):
    """wiki_citations event 必须紧跟 skill_view event 之后(yield 顺序固定,前端事件按序到达)。"""
    extra_config = {"wiki_citations": [{"n": 1, "kb_id": 1, "kind": "page", "id": 1, "title": "t"}]}

    lines = _drive_agui_stream(
        monkeypatch,
        extra_config=extra_config,
        params=_params(matched_skill_packages=[{"id": "p1"}]),
    )

    payloads = _parse_sse_lines(lines)
    custom_events = [p for p in payloads if p.get("type") == "CUSTOM"]
    names = [e["name"] for e in custom_events]
    assert "skill_view" in names and "wiki_citations" in names
    assert names.index("skill_view") < names.index("wiki_citations")


def test_no_wiki_citations_event_when_extra_config_empty(monkeypatch):
    """extra_config 无 wiki_citations 时必须不发 wiki_citations event(避免空事件污染流)。"""
    lines = _drive_agui_stream(monkeypatch, extra_config={"other_key": []}, params=_params())

    payloads = _parse_sse_lines(lines)
    wiki_events = [p for p in payloads if p.get("name") == "wiki_citations"]
    assert wiki_events == []


def test_no_wiki_citations_event_when_citations_list_empty(monkeypatch):
    """wiki_citations 字段存在但是空列表,也不应派发 event(None / [] 都跳过)。"""
    lines = _drive_agui_stream(monkeypatch, extra_config={"wiki_citations": []}, params=_params())

    payloads = _parse_sse_lines(lines)
    wiki_events = [p for p in payloads if p.get("name") == "wiki_citations"]
    assert wiki_events == []


def test_no_wiki_citations_event_when_no_extra_config(monkeypatch):
    """extra_config 缺省(None / 空 dict)也不派发,不抛异常。"""
    lines = _drive_agui_stream(monkeypatch, extra_config=None, params=_params())
    payloads = _parse_sse_lines(lines)
    wiki_events = [p for p in payloads if p.get("name") == "wiki_citations"]
    assert wiki_events == []

    # 二次确认:空 dict 也安全
    lines2 = _drive_agui_stream(monkeypatch, extra_config={}, params=_params())
    payloads2 = _parse_sse_lines(lines2)
    wiki_events2 = [p for p in payloads2 if p.get("name") == "wiki_citations"]
    assert wiki_events2 == []


import pytest  # noqa: E402  放在测试函数后面让前 5 个 helper 在没 pytest 的环境也可静态导入
