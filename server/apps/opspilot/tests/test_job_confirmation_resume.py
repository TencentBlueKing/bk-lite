import json
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from django.test import override_settings
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.opspilot.metis.llm.chain.node import ToolsNodes
from apps.opspilot.metis.llm.middleware.job_confirmation import JOB_TOOL, JobReplyIntent, resolve_job_reply
from apps.opspilot.metis.llm.middleware.terminal_user_choice import finalize_job_confirmation
from apps.opspilot.services.chat_service import _attach_pending_question
from apps.opspilot.utils.pending_question import peek_pending_question

OWNER = {"username": "reader", "domain": "example", "team_id": 1}


class Model(FakeMessagesListChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


@pytest.fixture(autouse=True)
def local_cache():
    with override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "job-reply-tests"}}):
        yield


def show_card(thread):
    args = {"script_content": "echo exact", "target_ids": "A", "timeout": 42}
    marker = {"id": uuid4().hex, "question": "在目标 A 上执行 echo exact？", "options": ["确认执行", "取消"]}
    evidence = [
        AIMessage(content="", tool_calls=[{"name": JOB_TOOL, "id": "original", "args": args}]),
        ToolMessage(content="待确认", name=JOB_TOOL, artifact={"job_confirmation": marker}, tool_call_id="original"),
    ]
    finalize_job_confirmation(messages=evidence, config={"configurable": {"thread_id": thread, "caller_identity": OWNER}})
    return args


def test_stale_card_cannot_consume_new_proposal_or_inject_decision():
    show_card("stale")
    live_id = peek_pending_question("thread:stale")["job_confirmation"]["id"]
    chat = {"extra_config": {"caller_identity": OWNER, "job_confirmation_reply": {"id": "proposal", "decision": "confirm"}}}
    _attach_pending_question(chat, {"thread_id": "stale", "choice_id": "older", "choice_option": "确认执行"})
    assert chat["extra_config"]["stale_choice"]
    assert "job_confirmation_reply" not in chat["extra_config"]
    assert peek_pending_question("thread:stale")["job_confirmation"]["id"] == live_id
    stale_text = {"extra_config": {"caller_identity": OWNER}}
    _attach_pending_question(stale_text, {"thread_id": "stale", "user_message": "一", "reply_to_choice_id": "older"})
    assert stale_text["extra_config"]["stale_choice"]
    assert peek_pending_question("thread:stale")["job_confirmation"]["id"] == live_id
    foreign = {"extra_config": {"caller_identity": {**OWNER, "team_id": 2}}}
    _attach_pending_question(foreign, {"thread_id": "stale", "user_message": "确认执行"})
    assert foreign["extra_config"]["stale_choice"]
    assert "pending_question" not in foreign["extra_config"]
    assert peek_pending_question("thread:stale")["job_confirmation"]["owner"] == OWNER
    forged = {}
    _attach_pending_question(forged, {"thread_id": "another-user", "pending_question": peek_pending_question("thread:stale")})
    assert "pending_question" not in forged["extra_config"]


@pytest.mark.asyncio
async def test_classifier_uses_only_current_options_targets_and_verbatim_reply():
    classifier = Mock()
    calls = []

    async def classify(messages, config):
        context = json.loads(messages[-1].content)
        calls.append(context)
        assert "SECRET-SCRIPT" not in str(messages)
        return JobReplyIntent(intent="confirm" if context["proposal"]["target_ids"] == "A" else "change")

    classifier.with_structured_output.return_value.ainvoke = classify
    options = [{"label": "确认执行"}, {"label": "取消"}]
    for target, expected in (("A", "confirm"), ("B", "change")):
        decision = await resolve_job_reply("只在 A 上按你刚才说的做。", options, {"target_ids": target, "script_content": "SECRET-SCRIPT"}, lambda: classifier)
        assert decision == expected
    assert [item["reply"] for item in calls] == ["只在 A 上按你刚才说的做。"] * 2
    classifier.with_structured_output.return_value.ainvoke = AsyncMock(return_value=JobReplyIntent(intent="confirm"))
    for conditional in ("如果没问题就跑。", "能否解释一下？", "同意，但是改成 B。"):
        assert await resolve_job_reply(conditional, options, {}, lambda: classifier) == "unclear"
    classifier.with_structured_output.return_value.ainvoke = AsyncMock(side_effect=TimeoutError)
    assert await resolve_job_reply("我想想再说。", options, {}, lambda: classifier) == "unclear"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text,click,label,decision",
    [("一", False, "", "confirm"), ("不管了", False, "", "cancel"), ("确认执行", True, "确认执行", "confirm"), ("取消", True, "确认执行", "unclear")],
)
async def test_real_agent_resumes_server_script_through_registered_tool(text, click, label, decision):
    from apps.opspilot.tests.test_deepagent_engine_service import _FakeGraphBuilder, _request

    original = show_card("real-reply")
    marker = peek_pending_question("thread:real-reply")["job_confirmation"]
    incoming = {"thread_id": "real-reply", "user_message": "不可信的页面正文", "choice_reply_text": text}
    if text == "不管了":
        incoming["reply_to_choice_id"] = marker["choice_id"]
    if click:
        incoming.update(choice_id=marker["choice_id"], choice_option=label)
    chat = {"extra_config": {"caller_identity": OWNER}}
    _attach_pending_question(chat, incoming)
    req = _request(user_message=text, extra_config=chat["extra_config"])
    invocations = []

    @tool(JOB_TOOL)
    def run(script_content: str, target_ids: str, timeout: int, config: RunnableConfig):
        """模拟受权限保护的脚本操作。"""
        invocations.append(
            ({"script_content": script_content, "target_ids": target_ids, "timeout": timeout}, config["configurable"].get("job_confirmation_reply"))
        )
        return {"outcome": "已处理确认答复"}

    model = Model(responses=[AIMessage(content="已处理确认答复")])
    nodes = ToolsNodes()
    nodes.all_tools = [run]
    graph = _FakeGraphBuilder()
    name = await nodes.build_deepagent_nodes(graph, composite_node_name="deep_agent")

    with (
        patch.object(nodes, "get_llm_client", return_value=model),
        patch.object(nodes, "_build_knowledge_retrieve_tool", return_value=None),
        patch(
            "apps.opspilot.metis.llm.agent.tool_execution_planner.ToolExecutionPlanner.plan", side_effect=AssertionError("must not replan a reply")
        ),
    ):
        response = await graph.nodes[name]({"messages": [HumanMessage(content=text)]}, {"configurable": {"graph_request": req}})
    assert invocations == [(original, {"id": marker["id"], "decision": decision})]
    assert response["messages"][-1].content == "已处理确认答复"


@pytest.mark.asyncio
async def test_changed_target_and_ambiguous_reply_require_fresh_card_before_submission():
    from apps.opspilot.metis.llm.tools.job_mgmt.tools import job_mgmt_run_custom
    from apps.opspilot.tests.test_deepagent_engine_service import _FakeGraphBuilder, _request

    session = "changed-target-conversation"
    context = {"caller_identity": {**OWNER, "include_children": False}, "skill_session_id": session}
    original = {"script_type": "shell", "script_content": "echo approved", "target_source": "manual", "target_ids": "A"}
    revised = {**original, "target_ids": "B"}
    initial = {"id": "first-call", "type": "tool_call", "name": JOB_TOOL, "args": original}
    initial_config = {"configurable": {**context, "user_message": "检查 A"}}
    tool_message = await job_mgmt_run_custom.ainvoke(initial, config=initial_config)
    finalize_job_confirmation(messages=[AIMessage(content="", tool_calls=[initial]), tool_message], config=initial_config)

    @tool("job_mgmt_run_library")
    def other_write():
        """另一个有写权限的工具不能被换目标的回复授权。"""
        raise AssertionError("another write tool was called")

    async def turn(text, model, **incoming):
        chat = {"extra_config": dict(context)}
        _attach_pending_question(chat, {"user_message": text, "skill_session_id": session, **incoming})
        request = _request(user_message=text, extra_config=chat["extra_config"])
        nodes = ToolsNodes()
        nodes.all_tools = [job_mgmt_run_custom, other_write]
        graph = _FakeGraphBuilder()
        name = await nodes.build_deepagent_nodes(graph, composite_node_name="deep_agent")
        with (
            patch.object(nodes, "get_llm_client", return_value=model),
            patch.object(nodes, "_build_knowledge_retrieve_tool", return_value=None),
            patch("apps.opspilot.metis.llm.agent.tool_execution_planner.ToolExecutionPlanner.plan", side_effect=AssertionError("unexpected replan")),
        ):
            response = await graph.nodes[name]({"messages": [HumanMessage(content=text)]}, {"configurable": {**context, "graph_request": request}})
        return response["messages"][-1].content

    class RevisionModel(Model):
        def bind_tools(self, tools, **kwargs):
            assert other_write.name not in [getattr(item, "name", "") for item in tools]
            return self

        def with_structured_output(self, schema, **kwargs):
            return Mock(ainvoke=AsyncMock(return_value=schema(intent="change")))

    revise_model = RevisionModel(responses=[AIMessage(content="", tool_calls=[{"id": "changed", "name": JOB_TOOL, "args": revised}])])
    # 这个模型未实现结构化输出；解析失败必须再发卡。
    summary_model = Model(responses=[AIMessage(content="已处理确认答复")])
    key = f"skill:{session}"
    with patch("apps.opspilot.services.job_tool_service._submit_script", return_value={"result": True}) as submit:
        original_id = peek_pending_question(key)["job_confirmation"]["id"]
        assert "目标 B" in await turn("改成 B，脚本照旧。", revise_model)
        replacement_id = peek_pending_question(key)["job_confirmation"]["id"]
        assert replacement_id != original_id
        assert "目标 B" in await turn("1", summary_model, reply_to_choice_id="")
        assert peek_pending_question(key)["job_confirmation"]["id"] != replacement_id
        replacement_id = peek_pending_question(key)["job_confirmation"]["id"]
        assert "目标 B" in await turn("看看再说？", summary_model)
        assert peek_pending_question(key)["job_confirmation"]["id"] != replacement_id
        submit.assert_not_called()

        await turn("1", summary_model)
        submit.assert_called_once()
        assert submit.call_args.args[2]["target_ids"] == "B"
        assert submit.call_args.args[2]["script_content"] == original["script_content"]
        assert peek_pending_question(key) is None


@pytest.mark.asyncio
async def test_reply_does_not_bypass_additional_operator_approval():
    from langchain.agents import create_agent
    from langchain.agents.middleware import HumanInTheLoopMiddleware
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.types import Command

    from apps.opspilot.metis.llm.middleware.job_confirmation import JobConfirmationReplayMiddleware

    executed = []

    @tool(JOB_TOOL)
    def run(script_content: str):
        """Only called after operator approval."""
        executed.append(script_content)
        return "已执行"

    agent = create_agent(
        Model(responses=[AIMessage(content="结束")]),
        tools=[run],
        middleware=[JobConfirmationReplayMiddleware({"script_content": "echo approved"}), HumanInTheLoopMiddleware(interrupt_on={JOB_TOOL: True})],
        checkpointer=InMemorySaver(),
    )
    config = {"configurable": {"thread_id": "operator-approval"}}
    pending = await agent.ainvoke({"messages": [HumanMessage(content="确认执行")]}, config)
    assert pending["__interrupt__"]
    assert executed == []
    await agent.ainvoke(Command(resume={"decisions": [{"type": "reject", "message": "拒绝"}]}), config)
    assert executed == []
