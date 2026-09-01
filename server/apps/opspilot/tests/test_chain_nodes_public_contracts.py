"""LLM 图节点的消息、检索和工具初始化公开契约。"""

from types import SimpleNamespace
from unittest.mock import patch

import pydantic.root_model  # noqa: F401
import pytest
from langchain_core.documents import Document
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool

from apps.opspilot.metis.llm.chain import node

pytestmark = pytest.mark.unit


def graph_config(request, **extra):
    configurable = {
        "graph_request": request,
        "trace_id": "trace-1",
        **extra,
    }
    return {"configurable": configurable}


def test_normalize_messages_merges_system_prompts_without_reordering_dialogue():
    dialogue = [
        HumanMessage(content="question"),
        SystemMessage(content="policy-a"),
        AIMessage(content="answer"),
        SystemMessage(content="policy-b"),
    ]

    normalized = node.normalize_messages_for_llm(dialogue)

    assert [type(message) for message in normalized] == [
        SystemMessage,
        HumanMessage,
        AIMessage,
    ]
    assert "policy-a" in normalized[0].content
    assert "policy-b" in normalized[0].content


@pytest.mark.asyncio
async def test_lightweight_direct_reply_merges_leading_system_for_qwen():
    """图前置 SystemMessage + light_system 必须合并为单条，避免 Qwen 400。"""
    from apps.opspilot.metis.llm.chain.node import ToolsNodes

    captured = {}

    class _FakeLLM:
        async def ainvoke(self, messages, config=None):
            captured["messages"] = list(messages)
            return AIMessage(content="ok")

    node = ToolsNodes()
    result = await node._invoke_lightweight_direct_reply(
        llm=_FakeLLM(),
        light_system="轻量系统",
        original_messages=[
            SystemMessage(content="图前置系统"),
            HumanMessage(content="你好"),
            AIMessage(content="上次回复"),
            HumanMessage(content="再问一句"),
        ],
        config={"configurable": {}},
        token_usage_accumulator=None,
        log_reason="unit",
    )

    msgs = captured["messages"]
    assert isinstance(msgs[0], SystemMessage)
    assert sum(1 for m in msgs if isinstance(m, SystemMessage)) == 1
    assert "轻量系统" in msgs[0].content
    assert "图前置系统" in msgs[0].content
    assert [type(m) for m in msgs[1:]] == [HumanMessage, AIMessage, HumanMessage]
    assert result["messages"][0].content == "ok"


@pytest.mark.asyncio
async def test_lightweight_direct_reply_records_stream_usage_from_final_chunk():
    """轻量直答 astream 终包带 usage 时必须记入 accumulator，不能落成全 0。"""
    from langchain_core.messages import AIMessageChunk

    from apps.opspilot.metis.llm.chain.node import ToolsNodes
    from apps.opspilot.metis.llm.common.token_usage import TokenUsageAccumulator

    class _FakeStreamLLM:
        async def astream(self, messages, config=None, stream_usage=False):
            assert stream_usage is True
            yield AIMessageChunk(content="你好")
            yield AIMessageChunk(
                content="",
                usage_metadata={"input_tokens": 41, "output_tokens": 9, "total_tokens": 50},
            )

        async def ainvoke(self, messages, config=None):
            raise AssertionError("有 astream 时不应回退 ainvoke")

    accumulator = TokenUsageAccumulator()
    node = ToolsNodes()
    result = await node._invoke_lightweight_direct_reply(
        llm=_FakeStreamLLM(),
        light_system="轻量系统",
        original_messages=[HumanMessage(content="你好")],
        config={"configurable": {}},
        token_usage_accumulator=accumulator,
        log_reason="unit",
    )

    assert result["messages"][0].content == "你好"
    assert accumulator.as_openai_usage() == {
        "prompt_tokens": 41,
        "completion_tokens": 9,
        "total_tokens": 50,
    }
    assert accumulator.calls[0].reported is True


def test_unsupported_stream_usage_error_is_callable_on_instance():
    from apps.opspilot.metis.llm.chain.node import ToolsNodes

    node = ToolsNodes()
    assert node._is_unsupported_stream_usage_error(RuntimeError("Unsupported parameter: 'stream_options'")) is True
    assert node._is_unsupported_stream_usage_error(RuntimeError("You've reached your 5-hour usage limit")) is False


@pytest.mark.asyncio
async def test_lightweight_stream_reraises_quota_error_instead_of_typeerror():
    """网关 403/配额失败不得被 stream_usage 探测函数二次 TypeError 盖掉。"""
    from apps.opspilot.metis.llm.chain.node import ToolsNodes

    class QuotaError(Exception):
        pass

    async def astream(messages, config=None, stream_usage=False):
        raise QuotaError("You've reached your 5-hour usage limit")
        yield  # noqa: B901 — 保持 async generator 签名

    node = ToolsNodes()
    with pytest.raises(QuotaError, match="5-hour usage limit"):
        await node._astream_lightweight_reply(astream, [HumanMessage(content="你好")], {})


@pytest.mark.asyncio
async def test_lightweight_stream_retries_without_usage_when_gateway_rejects_stream_options():
    from langchain_core.messages import AIMessageChunk

    from apps.opspilot.metis.llm.chain.node import ToolsNodes

    calls = []

    async def astream(messages, config=None, stream_usage=False):
        calls.append(stream_usage)
        if stream_usage:
            raise RuntimeError("Unsupported parameter: 'stream_options'")
        yield AIMessageChunk(content="ok")

    node = ToolsNodes()
    result = await node._astream_lightweight_reply(astream, [HumanMessage(content="你好")], {})
    assert result.content == "ok"
    assert calls == [True, False]


def test_normalize_messages_empty_input():
    assert node.normalize_messages_for_llm([]) == []


def test_without_system_messages_drops_graph_system_for_deepagent():
    from apps.opspilot.metis.llm.chain.node import without_system_messages

    kept = without_system_messages(
        [
            SystemMessage(content="图前置"),
            HumanMessage(content="写月报"),
            AIMessage(content="好的"),
        ]
    )
    assert [type(message) for message in kept] == [HumanMessage, AIMessage]


def test_merge_openai_payload_system_messages_moves_mid_conversation_system_to_front():
    from apps.opspilot.metis.llm.chain.lc_patches import merge_openai_payload_system_messages

    leading = [
        {"role": "system", "content": "only"},
        {"role": "user", "content": "hi"},
    ]
    assert merge_openai_payload_system_messages(leading) is leading

    merged = merge_openai_payload_system_messages(
        [
            {"role": "system", "content": "graph-system"},
            {"role": "user", "content": "生成附件"},
            {"role": "assistant", "content": "开始"},
            {"role": "system", "content": "deepagent-system"},
        ]
    )
    assert merged[0]["role"] == "system"
    assert "graph-system" in merged[0]["content"]
    assert "deepagent-system" in merged[0]["content"]
    assert [item["role"] for item in merged[1:]] == ["user", "assistant"]
    assert sum(1 for item in merged if item.get("role") == "system") == 1


def test_chatopenai_request_payload_merges_mid_conversation_system():
    """ChatOpenAI 覆盖了 Base._get_request_payload；补丁必须打在实际发请求的类上。"""
    from langchain_openai import ChatOpenAI

    import apps.opspilot.metis.llm.chain.lc_patches  # noqa: F401

    llm = ChatOpenAI(model="qwen-plus", api_key="test-key", base_url="http://127.0.0.1")
    payload = llm._get_request_payload(
        [
            SystemMessage(content="graph-system"),
            HumanMessage(content="生成附件"),
            AIMessage(content="开始"),
            SystemMessage(content="deepagent-system"),
        ]
    )
    messages = payload["messages"]
    assert messages[0]["role"] in {"system", "developer"}
    assert "graph-system" in messages[0]["content"]
    assert "deepagent-system" in messages[0]["content"]
    assert [item["role"] for item in messages[1:]] == ["user", "assistant"]
    assert sum(1 for item in messages if item.get("role") in {"system", "developer"}) == 1


def test_prompt_suggestion_and_history_nodes_build_valid_message_sequence():
    request = SimpleNamespace(
        system_message_prompt="Follow operations policy.",
        enable_suggest=True,
        chat_history=[
            SimpleNamespace(
                event="user",
                message="inspect this",
                image_data=["data:image/png;base64,abc"],
            ),
            SimpleNamespace(
                event="user",
                message="plain question",
                image_data=[],
            ),
            SimpleNamespace(
                event="assistant",
                message="previous answer",
                image_data=[],
            ),
        ],
    )
    state = {"messages": []}
    rendered = {
        "prompts/graph/base_node_system_message": "base policy",
        "prompts/graph/suggest_question_prompt": "suggest follow-ups",
    }

    with patch.object(
        node.TemplateLoader,
        "render_template",
        side_effect=lambda path, _data: rendered[path],
    ):
        basic = node.BasicNode()
        basic.prompt_message_node(state, graph_config(request))
        basic.suggest_question_node(state, graph_config(request))
        basic.add_chat_history_node(state, graph_config(request))

    assert state["messages"][0].content == "base policy\n\nsuggest follow-ups"
    assert state["messages"][1].content == [
        {"type": "text", "text": "inspect this"},
        {
            "type": "image_url",
            "image_url": {"url": "data:image/png;base64,abc"},
        },
    ]
    assert state["messages"][2].content == "plain question"
    assert state["messages"][3].content == "previous answer"


def test_history_node_keeps_bot_replies_from_skill_channel():
    """skill_channel 历史 event=bot；漏掉则模型会把旧问题当成未答再讲一遍。"""
    request = SimpleNamespace(
        chat_history=[
            SimpleNamespace(event="user", message="介绍下系统负载趋势", image_data=[]),
            SimpleNamespace(event="bot", message="负载约 1.98 / 1.80 / 1.58", image_data=[]),
            SimpleNamespace(event="user", message="分析下磁盘使用率情况", image_data=[]),
            SimpleNamespace(event="bot", message="磁盘使用率约 80.9%", image_data=[]),
        ],
    )
    state = {"messages": []}
    node.BasicNode().add_chat_history_node(state, graph_config(request))
    assert [type(msg).__name__ for msg in state["messages"]] == [
        "HumanMessage",
        "AIMessage",
        "HumanMessage",
        "AIMessage",
    ]
    assert state["messages"][1].content == "负载约 1.98 / 1.80 / 1.58"
    assert state["messages"][3].content == "磁盘使用率约 80.9%"


def test_history_image_without_text_does_not_inject_weather_prompt():
    request = SimpleNamespace(
        chat_history=[
            SimpleNamespace(event="user", message="", image_data=["data:image/png;base64,abc"]),
        ]
    )
    state = {"messages": []}
    node.BasicNode().add_chat_history_node(state, graph_config(request))
    content = state["messages"][0].content
    assert content == [{"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}}]
    assert "weather" not in str(content).lower()


def test_user_message_node_attaches_current_images_to_question():
    request = SimpleNamespace(
        user_message="介绍下网络吞吐趋势",
        graph_user_message="",
        enable_query_rewrite=False,
        extra_config={"current_image_data": ["data:image/png;base64,abc"]},
    )
    state = {"messages": []}
    node.BasicNode().user_message_node(state, graph_config(request))
    assert state["messages"][0].content == [
        {"type": "text", "text": "介绍下网络吞吐趋势"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
    ]
    assert request.graph_user_message == "介绍下网络吞吐趋势"


def test_suggestion_node_inserts_system_prompt_when_state_has_no_system_message():
    request = SimpleNamespace(enable_suggest=True)
    state = {"messages": [HumanMessage(content="question")]}

    with patch.object(
        node.TemplateLoader,
        "render_template",
        return_value="suggestion policy",
    ):
        node.BasicNode().suggest_question_node(state, graph_config(request))

    assert isinstance(state["messages"][0], SystemMessage)
    assert state["messages"][0].content == "suggestion policy"


def test_user_message_node_uses_rewrite_and_falls_back_on_rewrite_failure():
    request = SimpleNamespace(
        user_message="它恢复了吗？",
        graph_user_message="",
        enable_query_rewrite=True,
        chat_history=[],
    )
    basic = node.BasicNode()
    state = {"messages": []}
    with patch.object(
        node.LLMClientFactory,
        "invoke_isolated",
        return_value="数据库恢复了吗？ ",
    ), patch.object(node.TemplateLoader, "render_template", return_value="rewrite"):
        basic.user_message_node(state, graph_config(request))

    assert state["messages"][0].content == "数据库恢复了吗？"
    assert request.graph_user_message == "数据库恢复了吗？"

    fallback_state = {"messages": []}
    request.user_message = "保留原问题"
    with patch.object(
        node.LLMClientFactory,
        "invoke_isolated",
        side_effect=RuntimeError("LLM unavailable"),
    ), patch.object(node.TemplateLoader, "render_template", return_value="rewrite"):
        basic.user_message_node(fallback_state, graph_config(request))

    assert fallback_state["messages"][0].content == "保留原问题"
    assert request.graph_user_message == "保留原问题"


def test_chat_node_invokes_configured_llm_with_current_messages():
    llm = SimpleNamespace(invoke=lambda messages: AIMessage(content=str(len(messages))))
    request = SimpleNamespace()
    messages = [HumanMessage(content="hello")]
    with patch.object(
        node.LLMClientFactory,
        "create_client",
        return_value=llm,
    ) as factory:
        result = node.BasicNode().chat_node(
            {"messages": messages},
            graph_config(request),
        )

    assert result["messages"].content == "1"
    factory.assert_called_once_with(
        request,
        disable_stream=False,
        isolated=False,
    )


@pytest.mark.asyncio
async def test_naive_rag_node_formats_documents_graph_metadata_and_images():
    requests = [
        SimpleNamespace(
            index_name="knowledge-1",
            enable_graph_rag=False,
            search_query="",
        )
    ]
    graph_request = SimpleNamespace(
        naive_rag_request=requests,
        graph_user_message="why is postgres slow",
    )
    vector_docs = [
        Document(
            "ignored",
            metadata={
                "is_doc": "0",
                "qa_question": "How to inspect locks?",
                "qa_answer": "Query pg_locks.",
                "knowledge_id": 11,
            },
        ),
        Document(
            "Runbook",
            metadata={
                "is_doc": "1",
                "qa_answer": "Drain traffic first.",
                "knowledge_title": "Database runbook",
            },
        ),
        Document(
            "topology OCR",
            metadata={
                "format": "image",
                "page": 3,
                "image_base64": "YWJj",
            },
        ),
    ]

    class ExternalVectorStore:
        def search(self, search_request):
            assert search_request.search_query == "why is postgres slow"
            return vector_docs

    captured = {}

    def render(_path, template_data):
        captured.update(template_data)
        return "retrieval context"

    state = {"messages": []}
    with (
        patch.object(node, "PgvectorRag", ExternalVectorStore),
        patch.object(node.TemplateLoader, "render_template", side_effect=render),
    ):
        result = await node.BasicNode().naive_rag_node(
            state,
            graph_config(
                graph_request,
                enable_rag_source=True,
                enable_rag_strict_mode=True,
            ),
        )

    assert result is state
    assert captured["enable_rag_source"] is True
    assert captured["enable_rag_strict_mode"] is True
    assert captured["rag_results"][0]["content"] == ("问题: How to inspect locks?\n答案: Query pg_locks.")
    assert captured["rag_results"][0]["chunk_type"] == "QA"
    assert captured["rag_results"][1]["content"] == ("Runbook\nDrain traffic first.")
    assert state["messages"][0].content == ("retrieval context\n\n=== 图片识别内容 ===\n[图片 1]\ntopology OCR")
    assert state["messages"][1].content == [
        {
            "type": "image_url",
            "image_url": {"url": "data:image/jpeg;base64,YWJj"},
        }
    ]


def test_graph_result_processing_deduplicates_relations_and_summaries():
    graph_results = [
        {
            "source_node": {"name": "api", "summary": "frontend tier"},
            "target_node": {"name": "db", "summary": "storage tier"},
            "fact": "depends on",
        },
        {
            "source_node": {"name": "api", "summary": "frontend tier"},
            "target_node": {"name": "db", "summary": "storage tier"},
            "fact": "depends on",
        },
        {
            "source_node": {"name": "worker", "summary": "frontend tier"},
            "target_node": {"name": "db", "summary": "storage tier"},
            "fact": "",
        },
    ]

    processed = node.BasicNode()._process_graph_results(
        graph_results,
        ["group-1"],
    )

    assert len(processed) == 3
    assert processed[0].page_content == "关系事实: api - depends on - db"
    assert processed[0].metadata["knowledge_id"] == "group-1"
    assert processed[0].metadata["chunk_id"].startswith("relation_")
    assert "[api, worker]" in processed[1].page_content
    assert processed[1].metadata["chunk_type"] == "Graph"
    assert processed[2].page_content.endswith("storage tier")


@tool
def kubernetes_status(namespace: str) -> str:
    """Read Kubernetes status."""
    return namespace


@tool
def remote_health() -> str:
    """Read remote health."""
    return "ok"


@pytest.mark.asyncio
async def test_tools_setup_loads_authenticated_mcp_and_dynamic_catalog():
    class ExternalMCPClient:
        received = None

        def __init__(self, config):
            self.__class__.received = config

        async def get_tools(self):
            return [remote_health]

    servers = [
        SimpleNamespace(
            name="cluster",
            url="langchain:kubernetes",
            command="",
            args=[],
            transport="",
            enable_auth=False,
            auth_token="",
            extra_tools_prompt="Kubernetes operations",
            extra_param_prompt="",
        ),
        SimpleNamespace(
            name="inventory",
            url="https://93.184.216.34/mcp?transport=streamable_http",
            command="",
            args=[],
            transport="",
            enable_auth=True,
            auth_token="mcp-secret",
            extra_tools_prompt="Inventory operations",
            extra_param_prompt="",
        ),
    ]
    request = SimpleNamespace(
        tools_servers=servers,
        tool_pool_config=SimpleNamespace(
            enabled=True,
            auto_activate_threshold=1,
        ),
        done_tool_config=None,
        extra_config={
            "_require_choice_before_tools": True,
            "_multi_instance_options": [{"id": "cluster-a"}],
            "skill_package_capabilities": ["config_analysis_report"],
        },
    )
    tools_node = node.ToolsNodes()
    with (
        patch.object(node, "MultiServerMCPClient", ExternalMCPClient),
        patch.object(
            node.ToolsLoader,
            "load_tools",
            return_value=[kubernetes_status],
        ),
        patch.object(
            node.LLMClientFactory,
            "create_client",
            return_value=SimpleNamespace(),
        ),
    ):
        await tools_node.setup(request)

    assert ExternalMCPClient.received == {
        "inventory": {
            "url": servers[1].url,
            "transport": "streamable_http",
            "headers": {"Authorization": "mcp-secret"},
        }
    }
    assert tools_node._dynamic_mode is True
    assert tools_node.tools == []
    assert [item.name for item in tools_node.all_tools] == [
        "remote_health",
        "kubernetes_status",
    ]
    assert tools_node.tool_catalog == {
        "kubernetes": ["kubernetes_status"],
        "inventory": ["remote_health"],
    }
    assert tools_node._require_choice_before_tools is True
    assert tools_node._has_report_capability("config_analysis_report") is True

    activate = tools_node._build_activate_tools_meta_tool()
    activation = activate.invoke({"categories": "kubernetes,kubernetes,missing"})
    assert "已激活: kubernetes (1 个工具)" in activation
    assert "已存在: kubernetes" in activation
    assert "未找到: missing" in activation
    assert [item.name for item in tools_node.active_tools] == ["kubernetes_status"]


def test_remote_transport_and_kubernetes_greeting_filters():
    tools_node = node.ToolsNodes()

    assert tools_node._resolve_remote_transport("https://example.com/sse") == "sse"
    assert tools_node._resolve_remote_transport("https://example.com/mcp") == "streamable_http"
    assert (
        tools_node._resolve_remote_transport(
            "https://example.com/anything",
            "streamable_http",
        )
        == "streamable_http"
    )
    request = SimpleNamespace(
        tools_servers=[
            SimpleNamespace(url="langchain:kubernetes"),
            SimpleNamespace(url="langchain:kubernetes_data_collection"),
        ]
    )
    assert tools_node._should_apply_first_turn_greeting_filter(request) is True
    request.tools_servers.append(SimpleNamespace(url="langchain:mysql"))
    assert tools_node._should_apply_first_turn_greeting_filter(request) is False
