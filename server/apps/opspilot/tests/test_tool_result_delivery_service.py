"""工具结果落盘后仍可分析，且作业展示事件不丢失。"""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from ag_ui.encoder import EventEncoder
from deepagents.middleware.filesystem import FilesystemMiddleware
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from apps.opspilot.metis.llm.chain.deepagent_assembly import DeepAgentAssemblyMixin
from apps.opspilot.metis.llm.chain.graph import encode_job_script_output
from apps.opspilot.metis.llm.chain.planned_agent import create_planned_agent
from apps.opspilot.metis.llm.middleware.tool_runtime import ToolResultCompactionMiddleware, ToolVisibilityMiddleware
from apps.opspilot.metis.llm.tools.job_mgmt.tools import job_mgmt_query
from apps.opspilot.services.job_tool_service import _model_script_json
from apps.opspilot.services.python_sandbox.result_backend import build_result_backend
from apps.opspilot.services.python_sandbox.runtime import PythonSandbox


@pytest.fixture
def workspace():
    sandbox = PythonSandbox()
    yield sandbox
    sandbox.close()


@pytest.mark.parametrize("size", [3500, 6000])
def test_job_result_file_can_be_read_without_python_tool_after_compaction(workspace, monkeypatch, size):
    payload = {
        "task_id": 73,
        "status": "失败",
        "targets": [{"name": "web-1", "stdout": "x" * size, "stderr": "ROOT_CAUSE_AT_END", "exit_code": 1}],
    }
    raw = _model_script_json(payload)
    monkeypatch.setattr("apps.opspilot.metis.llm.tools.job_mgmt.tools.query_job", lambda *args: raw)
    visible, hidden = DeepAgentAssemblyMixin._build_planned_execution_tool_visibility(
        skill_sources=[], skills_only_plan=False, registered_tools=[job_mgmt_query]
    )

    class Model(FakeMessagesListChatModel):
        def bind_tools(self, tools, **kwargs):
            names = {getattr(tool, "name", "") for tool in tools}
            assert {"read_file", "grep"} <= names
            assert "python_execute_direct" not in names
            return self

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            results = [message for message in messages if isinstance(message, ToolMessage)]
            if not results:
                msg = AIMessage(content="", tool_calls=[{"name": "job_mgmt_query", "args": {"task_id": 73}, "id": "job"}])
            elif len(results) == 1:
                assert "ROOT_CAUSE_AT_END" not in results[0].content
                path = "/large_tool_results/job"
                assert path in results[0].content
                msg = AIMessage(
                    content="",
                    tool_calls=[{"name": "grep", "args": {"path": path, "pattern": "ROOT_CAUSE_AT_END", "output_mode": "content"}, "id": "read"}],
                )
            else:
                assert "ROOT_CAUSE_AT_END" in results[-1].content
                msg = AIMessage(content="已从脚本 stderr 定位 ROOT_CAUSE_AT_END")
            return ChatResult(generations=[ChatGeneration(message=msg)])

    agent = create_planned_agent(
        backend=build_result_backend(workspace),
        result_token_limit=750,
        model=Model(responses=[]),
        tools=[job_mgmt_query],
        middleware=[
            ToolVisibilityMiddleware(
                business_tools=[job_mgmt_query],
                active_tools=[job_mgmt_query],
                always_visible_tools=visible,
                hidden_tools=hidden,
                allow_unregistered_tools=False,
            ),
            ToolResultCompactionMiddleware(max_tool_chars=1500, preserve_tool_results=True),
        ],
    )
    result = agent.invoke({"messages": [HumanMessage(content="分析作业失败原因")]})
    assert result["messages"][-1].content == "已从脚本 stderr 定位 ROOT_CAUSE_AT_END"
    assert Path(workspace.files()[0]).read_text() == raw


@pytest.mark.django_db
def test_offloaded_job_message_still_produces_display_event(workspace, monkeypatch):
    payload = {"task_id": 73, "status": "成功", "targets": [{"stdout": "x" * 6000}]}
    monkeypatch.setattr("apps.opspilot.metis.llm.tools.job_mgmt.tools.query_job", lambda *args: _model_script_json(payload))
    monkeypatch.setattr("apps.opspilot.services.job_tool_service.latest_display_payload", lambda task_id: payload if task_id == 73 else None)
    message = job_mgmt_query.invoke({"name": "job_mgmt_query", "args": {"task_id": 73}, "id": "job", "type": "tool_call"})
    result = FilesystemMiddleware(backend=build_result_backend(workspace), tool_token_limit_before_evict=1000).wrap_tool_call(
        SimpleNamespace(tool_call={"name": "job_mgmt_query"}, runtime=None), lambda _: message
    )
    event = encode_job_script_output(EventEncoder(), "job_mgmt_query", result)
    assert event is not None
    assert json.loads(event.removeprefix("data: ").strip())["value"] == payload


@pytest.mark.parametrize("async_call", [False, True])
@pytest.mark.asyncio
async def test_default_offload_boundary_and_metadata(workspace, async_call):
    middleware = FilesystemMiddleware(backend=build_result_backend(workspace), tool_token_limit_before_evict=1000)
    request = SimpleNamespace(tool_call={"name": "job_mgmt_query"}, runtime=None)
    for size in (4000, 4001):
        message = ToolMessage(content="文" * size, tool_call_id="job", name="job_mgmt_query", artifact={"task_id": 73})

        async def handler(_):
            return message

        result = await middleware.awrap_tool_call(request, handler) if async_call else middleware.wrap_tool_call(request, lambda _: message)
        if size == 4000:
            assert result is message
            assert workspace.files() == []
        else:
            assert "read_file" in result.content
            assert result.artifact == {"task_id": 73}
            assert result.tool_call_id == "job"
            assert Path(workspace.files()[0]).read_text() == message.content


def test_result_reader_is_hidden_in_summary_stage(workspace):
    from langchain.agents.middleware import ModelRequest

    visible, hidden = DeepAgentAssemblyMixin._build_planned_execution_tool_visibility(skill_sources=[], skills_only_plan=False, registered_tools=[])
    policy = ToolVisibilityMiddleware(
        business_tools=[],
        active_tools=[],
        always_visible_tools=visible,
        hidden_tools=hidden,
        allow_unregistered_tools=False,
        include_always_visible=False,
    )
    request = ModelRequest(
        model=SimpleNamespace(),
        tools=FilesystemMiddleware(backend=build_result_backend(workspace)).tools,
        messages=[],
        state={},
        runtime=SimpleNamespace(),
    )
    policy.wrap_model_call(request, lambda prepared: pytest.fail("summary exposed a tool") if prepared.tools else None)
