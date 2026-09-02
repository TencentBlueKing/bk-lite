"""Usage ring snapshot is derived from the next packet, not stored session fields."""

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from apps.opspilot.metis.llm.chain.compaction import SUMMARY_HUMAN_PREFIX
from apps.opspilot.metis.llm.chain.context_usage import summarize_llm_context_usage
from apps.opspilot.metis.llm.chain.entity import BasicLLMRequest
from apps.opspilot.metis.llm.chain.token_utils import count_llm_request_tokens, count_tool_schema_tokens

_SECRET = "sk-usage-ring-PROMPT-SENTINEL"


class _LookupArgs(BaseModel):
    query: str = Field(description="lookup query")


def _lookup_tool():
    def _run(query: str) -> str:
        return query

    return StructuredTool.from_function(
        func=_run,
        name="lookup",
        description="lookup",
        args_schema=_LookupArgs,
    )


def test_usage_splits_wiki_tools_summary_and_conversation():
    tool = _lookup_tool()
    messages = [
        SystemMessage(content="你是排障助手。\n\n【相关知识库信息】请严格依据以下知识库内容回答。\n[1] CrashLoop"),
        HumanMessage(content=f"{SUMMARY_HUMAN_PREFIX}旧轮次已压缩。"),
        HumanMessage(content="【技能包执行】lookup k8s events"),
        AIMessage(content="", tool_calls=[{"name": "lookup", "args": {"query": "events"}, "id": "c1"}]),
        ToolMessage(content="ok", tool_call_id="c1", name="lookup"),
        HumanMessage(content="CURRENT_QUESTION"),
    ]
    request = BasicLLMRequest(
        model="gpt-4o",
        extra_config={"input_working_tokens": 6_800, "context_window_tokens": 8_000},
        compaction_max_token_threshold=5_100,
    )

    usage = summarize_llm_context_usage(messages, request=request, tools=[tool], model_name="gpt-4o")

    assert usage is not None
    ids = [segment["id"] for segment in usage["segments"]]
    assert "system" in ids
    assert "wiki" in ids
    assert "tools" in ids
    assert "skills" in ids
    assert "summary" in ids
    assert "conversation" in ids
    assert usage["compacted"] is True
    assert usage["input_working_tokens"] == 6_800
    assert usage["window_tokens"] == 8_000
    assert usage["compaction_threshold_tokens"] == 5_100
    assert usage["packet_tokens"] == count_llm_request_tokens(messages, [tool], "gpt-4o")
    tools_segment = next(segment for segment in usage["segments"] if segment["id"] == "tools")
    assert tools_segment["tokens"] == count_tool_schema_tokens([tool], "gpt-4o")
    rendered = str(usage)
    assert _SECRET not in rendered
    assert "CURRENT_QUESTION" not in rendered
    assert "CrashLoop" not in rendered
    assert "技能包执行" not in rendered


def test_usage_omits_empty_segments_and_requires_working_budget():
    messages = [HumanMessage(content="hi")]
    empty = summarize_llm_context_usage(messages, request=BasicLLMRequest(model="gpt-4o"), model_name="gpt-4o")
    assert empty is None

    usage = summarize_llm_context_usage(
        messages,
        request=BasicLLMRequest(model="gpt-4o", extra_config={"input_working_tokens": 6_800, "context_window_tokens": 8_000}),
        model_name="gpt-4o",
    )
    assert usage is not None
    assert [segment["id"] for segment in usage["segments"]] == ["conversation"]
    assert usage["compacted"] is False
