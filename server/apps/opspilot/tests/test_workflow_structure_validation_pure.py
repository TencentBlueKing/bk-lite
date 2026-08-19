"""工作流执行前的结构校验契约。"""

import asyncio
import json
from copy import deepcopy
from types import SimpleNamespace

import pytest

from apps.opspilot.utils.chat_flow_utils.engine.engine import ChatFlowEngine

pytestmark = pytest.mark.unit


async def _stream_content(response):
    chunks = []
    async for chunk in response.streaming_content:
        chunks.append(chunk.decode() if isinstance(chunk, bytes) else chunk)
    return "".join(chunks)


@pytest.mark.parametrize(
    ("flow_json", "expected_error"),
    [
        ([], "流程数据必须是对象"),
        ({"nodes": {}, "edges": []}, "nodes 必须是数组"),
        ({"nodes": [], "edges": {}}, "edges 必须是数组"),
        ({"nodes": ["invalid"], "edges": []}, "节点 1 必须是对象"),
        ({"nodes": [{"type": "restful"}], "edges": []}, "节点 1 缺少有效 id"),
        ({"nodes": [{"id": 0, "type": "restful"}], "edges": []}, "节点 1 缺少有效 id"),
        ({"nodes": [{"id": False, "type": "restful"}], "edges": []}, "节点 1 缺少有效 id"),
        ({"nodes": [{"id": 42, "type": "restful"}], "edges": []}, "节点 1 缺少有效 id"),
        ({"nodes": [{"id": "entry", "type": []}], "edges": []}, "节点 1 的 type 必须是字符串"),
        ({"nodes": [{"id": "entry", "type": {}}], "edges": []}, "节点 1 的 type 必须是字符串"),
        ({"nodes": [{"id": "entry", "type": ""}], "edges": []}, "节点 1 缺少有效 type"),
        ({"nodes": [{"id": "entry", "type": "  "}], "edges": []}, "节点 1 缺少有效 type"),
        (
            {"nodes": [{"id": "entry", "type": "restful"}], "edges": ["invalid"]},
            "边 1 必须是对象",
        ),
        (
            {"nodes": [{"id": "entry", "type": "restful"}], "edges": [{"target": "entry"}]},
            "边 1 缺少有效 source",
        ),
        (
            {"nodes": [{"id": "entry", "type": "restful"}], "edges": [{"source": 0, "target": "entry"}]},
            "边 1 缺少有效 source",
        ),
        (
            {"nodes": [{"id": "entry", "type": "restful"}], "edges": [{"source": "entry"}]},
            "边 1 缺少有效 target",
        ),
        (
            {"nodes": [{"id": "entry", "type": "restful"}], "edges": [{"source": "entry", "target": False}]},
            "边 1 缺少有效 target",
        ),
    ],
)
def test_execute_rejects_malformed_workflow_with_readable_error(flow_json, expected_error):
    workflow = SimpleNamespace(id=3763, flow_json=flow_json)

    result = ChatFlowEngine(workflow).execute()

    assert result["success"] is False
    assert expected_error in result["error"]
    assert result["execution_time"] == 0


def test_structure_validation_preserves_minimal_legacy_node_shape():
    workflow = SimpleNamespace(
        id=3763,
        flow_json={"nodes": [{"id": "entry", "type": "restful"}], "edges": []},
    )

    assert ChatFlowEngine(workflow).validate_flow() == []


def test_execute_preserves_minimal_legacy_node_shape(monkeypatch):
    workflow = SimpleNamespace(
        id=3763,
        bot_id=1,
        flow_json={"nodes": [{"id": "entry", "type": "compat_echo"}], "edges": []},
    )
    engine = ChatFlowEngine(workflow)
    engine.custom_node_executors["compat_echo"] = lambda _node_id, _node, data: {"last_message": f"{data['last_message']} ok"}
    monkeypatch.setattr(engine, "_ensure_execution_result_started", lambda *args: None)
    monkeypatch.setattr(engine, "_record_conversation_history", lambda *args: None)
    monkeypatch.setattr(engine, "_record_execution_result", lambda *args: None)
    monkeypatch.setattr(engine, "_record_node_execution_result", lambda *args: None)
    monkeypatch.setattr(engine, "_check_interrupt_requested", lambda: False)

    assert engine.execute({"last_message": "hello"}) == "hello ok"


def test_structure_validation_does_not_mutate_persisted_flow_json():
    flow_json = {
        "nodes": [{"id": "entry", "type": "restful"}, {"type": "restful"}],
        "edges": [{"source": "entry"}],
        "metadata": {"schema_version": "legacy"},
    }
    original = deepcopy(flow_json)

    ChatFlowEngine(SimpleNamespace(id=3763, flow_json=flow_json)).execute()

    assert flow_json == original


def test_sse_structure_validation_returns_detail_before_conversation_side_effect(monkeypatch):
    workflow = SimpleNamespace(
        id=3763,
        bot_id=1,
        flow_json={"nodes": [{"type": "restful"}], "edges": []},
    )
    engine = ChatFlowEngine(workflow)
    recorded_messages = []
    monkeypatch.setattr(engine, "_record_conversation_history", lambda *args: recorded_messages.append(args))

    response = engine.sse_execute({"last_message": "hello"})
    content = asyncio.run(_stream_content(response))
    payload = json.loads(content.splitlines()[0].removeprefix("data: "))

    assert "节点 1 缺少有效 id" in payload["error"]
    assert recorded_messages == []


@pytest.mark.parametrize(
    ("flow_json", "expected_error"),
    [
        (
            {
                "nodes": [
                    {"id": "entry", "type": "restful"},
                    {"id": "entry", "type": "restful"},
                ],
                "edges": [],
            },
            "节点 2 的 id 重复: entry",
        ),
        (
            {
                "nodes": [{"id": "entry", "type": "restful"}],
                "edges": [{"source": "missing", "target": "entry"}],
            },
            "边 1 的 source 未引用现有节点: missing",
        ),
        (
            {
                "nodes": [{"id": "entry", "type": "restful"}],
                "edges": [{"source": "entry", "target": "missing"}],
            },
            "边 1 的 target 未引用现有节点: missing",
        ),
    ],
)
def test_validate_flow_rejects_ambiguous_graph_references(flow_json, expected_error):
    workflow = SimpleNamespace(id=3763, flow_json=flow_json)

    assert expected_error in ChatFlowEngine(workflow).validate_flow()
