"""原生结果文件在真实 Agent 工具循环中的交付与权限契约。"""

from types import SimpleNamespace

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool

from apps.opspilot.metis.llm.chain.deepagent_assembly import DeepAgentAssemblyMixin
from apps.opspilot.services.python_sandbox.runtime import PythonSandbox


@pytest.mark.parametrize("async_call", [False, True])
@pytest.mark.asyncio
async def test_native_result_search_and_range_read_without_execution_tools(async_call):
    from apps.opspilot.metis.llm.chain.planned_agent import create_planned_agent
    from apps.opspilot.services.python_sandbox.result_backend import build_result_backend

    raw = "\n".join(f"record {i}: " + ("ROOT_CAUSE" if i == 250 else "healthy") for i in range(500))

    @tool
    def query_alerts() -> str:
        """查询告警。"""
        return raw

    visible, hidden = DeepAgentAssemblyMixin._build_planned_execution_tool_visibility(
        skill_sources=[], skills_only_plan=False, registered_tools=[query_alerts]
    )

    class Model(FakeMessagesListChatModel):
        def bind_tools(self, tools, **kwargs):
            names = {item.name for item in tools}
            assert {"read_file", "grep", "query_alerts"} <= names
            assert not names & {"execute", "write_file", "edit_file", "python_execute_direct", "read_tool_result"}
            return self

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            results = [m for m in messages if isinstance(m, ToolMessage)]
            calls = [
                ("query_alerts", {}, "query"),
                ("grep", {"pattern": "ROOT_CAUSE", "path": "/large_tool_results/query", "output_mode": "content"}, "search"),
                ("read_file", {"file_path": "/large_tool_results/query", "offset": 240, "limit": 20}, "read"),
            ]
            if results:
                assert results[-1].status == "success"
            if len(results) == 1:
                assert "/large_tool_results/query" in results[-1].content
                assert "ROOT_CAUSE" not in results[-1].content
            if len(results) >= 2:
                assert "ROOT_CAUSE" in results[-1].content
            if len(results) < len(calls):
                name, args, call_id = calls[len(results)]
                answer = AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}])
            else:
                answer = AIMessage(content="已定位 record 250")
            return ChatResult(generations=[ChatGeneration(message=answer)])

    assembly = DeepAgentAssemblyMixin()
    assembly.get_llm_client = lambda *args, **kwargs: None
    graph_request = SimpleNamespace(
        model="gpt-4o",
        extra_config={"input_working_tokens": 8192},
        message_trim_config={"max_single_message_tokens": 4000},
    )
    runtime, _, _, _ = assembly._build_planned_execution_runtime_middleware(
        registered_tools=[query_alerts],
        active_tools=[query_alerts],
        always_visible=visible,
        hidden_tools=hidden,
        skills_only_plan=False,
        graph_request=graph_request,
        token_usage_accumulator=None,
    )
    sandbox = PythonSandbox()
    try:
        backend = build_result_backend(sandbox)
        agent = create_planned_agent(
            model=Model(responses=[]),
            tools=[query_alerts],
            backend=backend,
            result_token_limit=500,
            middleware=runtime,
        )
        payload = {"messages": [HumanMessage(content="找出告警原因")]}
        if async_call:
            result = await agent.ainvoke(payload)
        else:
            import asyncio

            result = await asyncio.to_thread(agent.invoke, payload)
        assert result["messages"][-1].content == "已定位 record 250"
        assert backend.read("/large_tool_results/query", limit=1000).file_data["content"] == raw
    finally:
        sandbox.close()


def test_result_backend_is_run_scoped_and_rejects_symlinks(tmp_path):
    from apps.opspilot.services.python_sandbox.result_backend import build_result_backend

    first, second = PythonSandbox(), PythonSandbox()
    try:
        backend, other = build_result_backend(first), build_result_backend(second)
        assert backend.write("/large_tool_results/query", "RESULT_SENTINEL").error is None
        assert other.read("/large_tool_results/query").error
        secret = tmp_path / "secret.txt"
        secret.write_text("PRIVATE_SENTINEL")
        assert backend.read(str(secret)).error
        assert backend.read("/large_tool_results/../../secret.txt").error
        from pathlib import Path

        target = Path(first.workspace) / "large_tool_results" / "query"
        target.unlink()
        target.symlink_to(secret)
        assert backend.read("/large_tool_results/query").error
        assert "PRIVATE_SENTINEL" not in str(backend.grep("PRIVATE_SENTINEL", "/large_tool_results/"))
        first.close()
        assert backend.read("/large_tool_results/query").error
        assert backend.write("/large_tool_results/new", "closed run").error
    finally:
        first.close()
        second.close()


def test_skill_success_keeps_only_result_readers_available():
    from langchain.agents.middleware import ModelRequest

    from apps.opspilot.metis.llm.middleware.tool_runtime import SkillExecutionGuardMiddleware

    messages = [
        AIMessage(content="", tool_calls=[{"name": "execute", "args": {"command": "python /skills/demo/scripts/query.py"}, "id": "run"}]),
        ToolMessage(content="[OPSPILOT_SKILL_RESULT] 脚本已成功返回数据。", name="execute", tool_call_id="run"),
    ]
    tools = [SimpleNamespace(name=name) for name in ("execute", "read_file", "grep", "write_file")]
    request = ModelRequest(model=SimpleNamespace(), tools=tools, messages=messages, state={}, runtime=SimpleNamespace())
    guard = SkillExecutionGuardMiddleware(enabled=True)
    filtered = guard.wrap_model_call(request, lambda prepared: prepared)
    assert {t.name for t in filtered.tools} == {"read_file", "grep"}


def test_native_eviction_preserves_media_and_failed_storage_does_not_claim_success():
    from unittest.mock import patch

    from deepagents.backends.protocol import WriteResult
    from deepagents.middleware.filesystem import FilesystemMiddleware

    from apps.opspilot.services.python_sandbox.result_backend import build_result_backend

    sandbox = PythonSandbox()
    try:
        backend = build_result_backend(sandbox)
        middleware = FilesystemMiddleware(backend=backend, tool_token_limit_before_evict=500)
        message = ToolMessage(
            content=[{"type": "text", "text": "结果\n" * 2000}, {"type": "image_url", "image_url": {"url": "https://example.invalid/image.png"}}],
            tool_call_id="mixed",
            name="query",
            artifact={"task_id": 73},
            status="error",
        )
        request = SimpleNamespace(tool_call={"name": "query"}, runtime=None)
        with patch.object(backend, "write", return_value=WriteResult(error="disk unavailable")):
            assert middleware.wrap_tool_call(request, lambda _: message) is message
        result = middleware.wrap_tool_call(request, lambda _: message)
        assert result.artifact == message.artifact and result.status == "error"
        assert result.tool_call_id == "mixed"
        assert any(block.get("type") == "image" for block in result.content)
        assert "/large_tool_results/mixed" in result.content[0]["text"]
    finally:
        sandbox.close()


def test_context_cleanup_keeps_native_file_reference_and_identity():
    from apps.opspilot.metis.llm.chain.prepare_llm_context import drop_old_tool_results

    original = ToolMessage(
        content=(
            "Tool result too large, the result of this tool call query was saved in the filesystem "
            "at this path: /large_tool_results/query\n\nPREVIEW_BODY"
        ),
        name="query",
        tool_call_id="query",
        artifact={"task_id": 73},
        status="error",
    )
    result = drop_old_tool_results([original], keep_recent=0)[0]
    assert "/large_tool_results/query" in result.content
    assert "PREVIEW_BODY" not in result.content
    assert result.artifact == original.artifact and result.status == original.status
    assert result.tool_call_id == original.tool_call_id


@pytest.mark.parametrize("path", ["/large_tool_results/query", "large_tool_results/query", "//large_tool_results/query"])
@pytest.mark.parametrize("name", ["write_file", "edit_file"])
def test_saved_results_cannot_be_mutated_by_file_tools(path, name):
    from apps.opspilot.metis.llm.middleware.python_sandbox import PythonSandboxMiddleware

    sandbox = PythonSandbox()
    try:
        request = SimpleNamespace(tool_call={"name": name, "args": {"file_path": path}, "id": "write"})
        result = PythonSandboxMiddleware(sandbox).wrap_tool_call(request, lambda _: pytest.fail("result mutation reached handler"))
        assert result.status == "error" and "只读" in result.content
    finally:
        sandbox.close()


@pytest.mark.parametrize("single, expected", [(4000, 1000), (8000, 2000), (32000, 8000), (128000, 20000)])
def test_native_result_threshold_uses_existing_single_message_budget(single, expected):
    from apps.opspilot.metis.llm.chain.planned_agent import result_token_limit_for_request

    assert result_token_limit_for_request(SimpleNamespace(message_trim_config={"max_single_message_tokens": single})) == expected


def test_native_skill_output_can_be_read_without_executing_script_again(mocker):
    from deepagents.backends.protocol import ExecuteResponse

    from apps.opspilot.metis.llm.chain.planned_agent import create_planned_agent
    from apps.opspilot.metis.llm.middleware.python_sandbox import PythonSandboxMiddleware
    from apps.opspilot.metis.llm.middleware.tool_runtime import SkillExecutionGuardMiddleware
    from apps.opspilot.services.python_sandbox.result_backend import build_result_backend
    from apps.opspilot.services.python_sandbox.skill_backend import LocalSkillBackend

    sandbox = PythonSandbox()
    try:
        local = LocalSkillBackend(sandbox)
        execute = mocker.patch.object(local, "execute", return_value=ExecuteResponse(output="line\n" * 1000, exit_code=0))

        class Model(FakeMessagesListChatModel):
            def bind_tools(self, tools, **kwargs):
                return self

            def _generate(self, messages, stop=None, run_manager=None, **kwargs):
                results = [m for m in messages if isinstance(m, ToolMessage)]
                if not results:
                    call = {"name": "execute", "args": {"command": "python /skills/demo/scripts/query.py"}, "id": "run"}
                elif len(results) == 1:
                    assert "/large_tool_results/run" in results[-1].content
                    call = {"name": "read_file", "args": {"file_path": "/large_tool_results/run", "offset": 500, "limit": 20}, "id": "read"}
                elif len(results) == 2:
                    assert results[-1].status == "success" and "line" in results[-1].content
                    call = {"name": "execute", "args": {"command": "python /skills/demo/scripts/query.py"}, "id": "retry"}
                else:
                    assert results[-1].status == "error"
                    return ChatResult(generations=[ChatGeneration(message=AIMessage(content="done"))])
                return ChatResult(generations=[ChatGeneration(message=AIMessage(content="", tool_calls=[call]))])

        agent = create_planned_agent(
            model=Model(responses=[]),
            tools=[],
            backend=build_result_backend(sandbox, local),
            result_token_limit=500,
            middleware=[SkillExecutionGuardMiddleware(enabled=True), PythonSandboxMiddleware(sandbox)],
        )
        result = agent.invoke({"messages": [HumanMessage(content="执行技能并分析结果")]})
        assert result["messages"][-1].content == "done"
        execute.assert_called_once()
    finally:
        sandbox.close()


def test_planned_native_agent_keeps_human_approval_before_execution():
    from apps.opspilot.metis.llm.chain.planned_agent import create_planned_agent
    from apps.opspilot.services.python_sandbox.result_backend import build_result_backend

    @tool
    def run_job() -> str:
        """运行需要批准的作业。"""
        pytest.fail("job ran before approval")

    class Model(FakeMessagesListChatModel):
        def bind_tools(self, tools, **kwargs):
            return self

    sandbox = PythonSandbox()
    try:
        agent = create_planned_agent(
            model=Model(responses=[AIMessage(content="", tool_calls=[{"name": "run_job", "args": {}, "id": "job"}])]),
            tools=[run_job],
            backend=build_result_backend(sandbox),
            interrupt_on={"run_job": True},
        )
        result = agent.invoke({"messages": [HumanMessage(content="运行作业")]})
        assert result["__interrupt__"]
        assert result["__interrupt__"][0].value["action_requests"][0]["name"] == "run_job"
    finally:
        sandbox.close()
