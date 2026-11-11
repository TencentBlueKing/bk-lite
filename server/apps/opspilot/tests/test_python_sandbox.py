from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import ToolMessage

from apps.opspilot.metis.llm.middleware.python_sandbox import PythonSandboxMiddleware
from apps.opspilot.metis.llm.tools.python.executor import python_execute_direct
from apps.opspilot.services.python_sandbox.runtime import PythonSandbox, SandboxUnavailable


def test_large_result_saved_and_tool_metadata_preserved():
    sandbox = MagicMock()
    sandbox.store_result.return_value = "/workspace/result.txt"
    middleware = PythonSandboxMiddleware(sandbox, threshold=5)
    request = SimpleNamespace(tool_call={"name": "alerts_list_alerts"})
    message = ToolMessage(content="abcdefgh", tool_call_id="call-1", name="alerts_list_alerts")
    result = middleware.wrap_tool_call(request, lambda _: message)
    sandbox.store_result.assert_called_once_with("abcdefgh")
    assert result.tool_call_id == "call-1"
    assert "/workspace/result.txt" in result.content
    assert "abcdefgh" in result.content


def test_unavailable_sandbox_never_claims_result_was_saved():
    sandbox = MagicMock()
    sandbox.store_result.side_effect = SandboxUnavailable()
    middleware = PythonSandboxMiddleware(sandbox, threshold=5)
    message = ToolMessage(content="abcdefgh", tool_call_id="call-1")
    result = middleware.wrap_tool_call(SimpleNamespace(tool_call={"name": "alerts"}), lambda _: message)
    assert result is message


@pytest.mark.parametrize("content", ["existing policy", [{"type": "text", "text": "existing policy", "cache_control": {"type": "ephemeral"}}], None])
@pytest.mark.parametrize("async_call", [False, True])
@pytest.mark.asyncio
async def test_execution_guidance_preserves_system_message_without_starting_container(content, async_call):
    from langchain.agents.middleware import ModelRequest
    from langchain_core.messages import AIMessage, SystemMessage

    system = SystemMessage(content=content, id="policy") if content is not None else None
    request = ModelRequest(model=SimpleNamespace(), messages=[], system_message=system, tools=[], state={}, runtime=SimpleNamespace())
    client = MagicMock()
    middleware = PythonSandboxMiddleware(PythonSandbox(client=client))
    answer = AIMessage(content="done")

    def handler(prepared):
        assert "ijson" in prepared.system_message.text
        assert "python -m pip install --user" in prepared.system_message.text
        assert "/opt/opspilot-sandbox/USAGE.md" in prepared.system_message.text
        if system is not None:
            assert prepared.system_message.id == "policy"
            assert "existing policy" in prepared.system_message.text
            if isinstance(content, list):
                assert prepared.system_message.content[0] == content[0]
        return answer

    async def async_handler(prepared):
        return handler(prepared)

    result = await middleware.awrap_model_call(request, async_handler) if async_call else middleware.wrap_model_call(request, handler)
    assert result is answer
    assert request.system_message is system
    if system is not None:
        assert system.content == content
    client.containers.run.assert_not_called()


def test_python_tool_uses_run_sandbox_and_fails_closed():
    sandbox = MagicMock()
    sandbox.execute.return_value = "42"
    assert python_execute_direct.invoke({"code": "6 * 7"}, config={"configurable": {"python_sandbox": sandbox}}) == "42"
    sandbox.execute.assert_called_once_with("6 * 7")
    assert "隔离环境不可用" in python_execute_direct.invoke({"code": "import os"}, config={"configurable": {}})


def test_container_creation_has_no_host_mounts():
    client = MagicMock()
    client.containers.run.return_value.exec_run.return_value.exit_code = 0
    sandbox = PythonSandbox(client=client, image="test-image")
    sandbox._ensure_container()
    kwargs = client.containers.run.call_args.kwargs
    assert "volumes" not in kwargs
    assert kwargs["cap_drop"] == ["ALL"]
    assert kwargs["security_opt"] == ["no-new-privileges:true"]
    assert kwargs["user"] == "65534:65534"
    assert kwargs["auto_remove"] is True
    assert "network_mode" not in kwargs
    assert kwargs["mem_limit"] == "1g"
    assert kwargs["nano_cpus"] == 1_000_000_000
    assert kwargs["pids_limit"] == 128
    assert "size=256m" in kwargs["tmpfs"]["/workspace"]
    assert "size=128m" in kwargs["tmpfs"]["/tmp"]
    sandbox.close()
    client.containers.run.return_value.remove.assert_called_once_with(force=True)


@pytest.mark.skipif(not __import__("os").getenv("OPSPILOT_TEST_DOCKER"), reason="requires Docker")
def test_real_container_reads_large_result_and_isolates_tasks(tmp_path):
    first = PythonSandbox(image="python:3.12-alpine")
    second = PythonSandbox(image="python:3.12-alpine")
    try:
        path = first.store_result('[{"value": 2}, {"value": 5}]')
        result = first.execute(f'import json\nwith open({path!r}) as f: data = json.load(f)\nsum(x["value"] for x in data)')
        assert result == "7"
        assert "FileNotFoundError" in second.execute(f"open({path!r}).read()")
        host_file = tmp_path / "host-only.txt"
        host_file.write_text("host-secret")
        assert first.execute(f"import os\nos.path.exists({str(host_file)!r})") == "False"
        assert first.execute('import subprocess\nsubprocess.check_output(["echo", "ok"]).decode().strip()') == "ok"
    finally:
        first.close()
        second.close()


@pytest.mark.skipif(not __import__("os").getenv("OPSPILOT_TEST_DOCKER"), reason="requires Docker")
def test_real_middleware_to_python_tool_chain():
    sandbox = PythonSandbox(image="python:3.12-alpine")
    try:
        payload = "[" + ",".join('{"value": 2}' for _ in range(1000)) + "]"
        middleware = PythonSandboxMiddleware(sandbox)
        request = SimpleNamespace(tool_call={"name": "alerts_list_alerts"})
        tool_message = ToolMessage(content=payload, tool_call_id="call-chain")
        output = middleware.wrap_tool_call(request, lambda _: tool_message)
        path = sandbox.files()[0]
        assert path in output.content
        assert len(output.content) < len(payload)
        code = f'import json\nwith open({path!r}) as f: rows = json.load(f)\nsum(row["value"] for row in rows)'
        result = python_execute_direct.invoke({"code": code}, config={"configurable": {"python_sandbox": sandbox}})
        assert result == "2000"
    finally:
        sandbox.close()


@pytest.mark.skipif(not __import__("os").getenv("OPSPILOT_TEST_DOCKER"), reason="requires Docker")
def test_agent_middlewares_pass_file_path_and_sandbox_to_python():
    import re

    from deepagents.middleware.filesystem import FilesystemMiddleware
    from langchain.agents import create_agent
    from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
    from langchain_core.messages import AIMessage, HumanMessage
    from langchain_core.outputs import ChatGeneration, ChatResult
    from langchain_core.tools import tool

    @tool
    def alerts_list_alerts() -> str:
        """Return alerts."""
        return "[" + ",".join('{"value": 2}' for _ in range(1000)) + "]"

    class Model(FakeMessagesListChatModel):
        def bind_tools(self, tools, **kwargs):
            return self

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            tool_messages = [m for m in messages if isinstance(m, ToolMessage)]
            if not tool_messages:
                msg = AIMessage(content="", tool_calls=[{"name": "alerts_list_alerts", "args": {}, "id": "alerts"}])
            elif len(tool_messages) == 1:
                match = re.search(r"/workspace/tool-result-[a-f0-9]+\.txt", tool_messages[0].content)
                assert match is not None
                code = f'import json\nwith open({match.group()!r}) as f: rows=json.load(f)\nsum(r["value"] for r in rows)'
                msg = AIMessage(content="", tool_calls=[{"name": "python_execute_direct", "args": {"code": code}, "id": "python"}])
            else:
                msg = AIMessage(content=tool_messages[-1].content)
            return ChatResult(generations=[ChatGeneration(message=msg)])

    sandbox = PythonSandbox(image="python:3.12-alpine")
    try:
        agent = create_agent(
            model=Model(responses=[]),
            tools=[alerts_list_alerts, python_execute_direct],
            middleware=[FilesystemMiddleware(), PythonSandboxMiddleware(sandbox)],
        )
        result = agent.invoke({"messages": [HumanMessage(content="统计告警")]}, config={"configurable": {"python_sandbox": sandbox}})
        assert result["messages"][-1].content == "2000"
    finally:
        sandbox.close()


@pytest.mark.skipif(not __import__("os").getenv("OPSPILOT_TEST_DOCKER"), reason="requires Docker")
def test_skill_command_and_python_share_container_workspace(tmp_path):
    sandbox = PythonSandbox(image="python:3.12-alpine")
    try:
        path = sandbox.store_result("42")
        result = sandbox.execute_command(f"cat {path} > /workspace/skill-output.txt")
        assert result.exit_code == 0
        assert sandbox.execute("open('/workspace/skill-output.txt').read()") == "42"
        assert sandbox.execute_command("printf '%s' \"$SKILL_TEST\"", env={"SKILL_TEST": "value"}).output == "value"
        assert sandbox.execute_command("exit 3").exit_code == 3
        host_file = tmp_path / "host-only.txt"
        host_file.write_text("secret")
        assert sandbox.execute_command(f"test -e {host_file}").exit_code != 0
    finally:
        sandbox.close()


def test_skill_command_fails_closed_when_container_is_unavailable():
    client = MagicMock()
    client.containers.run.side_effect = RuntimeError("unavailable")
    sandbox = PythonSandbox(client=client, image="missing")
    with pytest.raises(SandboxUnavailable):
        sandbox.execute_command("echo cannot-run-on-host")


@pytest.mark.skipif(not __import__("os").getenv("OPSPILOT_TEST_DOCKER"), reason="requires Docker")
def test_skill_command_timeout_reports_failure():
    sandbox = PythonSandbox(image="python:3.12-alpine")
    try:
        result = sandbox.execute_command("sleep 10", timeout=1)
        assert result.exit_code != 0
    finally:
        sandbox.close()


@pytest.mark.skipif(not __import__("os").getenv("OPSPILOT_TEST_DOCKER"), reason="requires Docker")
def test_binary_file_transfer_is_confined_and_round_trips():
    sandbox = PythonSandbox(image="python:3.12-alpine")
    try:
        data = bytes(range(256)) * 500
        sandbox.write_workspace_file("/workspace/input/report.xlsx", data)
        assert sandbox.read_workspace_file("/workspace/input/report.xlsx") == data
        sandbox.execute_command("ln -s /etc/passwd /workspace/input/escape")
        with pytest.raises(SandboxUnavailable):
            sandbox.read_workspace_file("/workspace/input/escape")
        with pytest.raises(ValueError):
            sandbox.read_workspace_file("/workspace/../etc/passwd")
    finally:
        sandbox.close()


def test_attachment_tool_publishes_sandbox_bytes(mocker):
    import importlib

    module = importlib.import_module("apps.opspilot.metis.llm.tools.attachment.generate_attachment")
    sandbox = MagicMock()
    sandbox.read_workspace_file.return_value = b"%PDF-document"
    asset = SimpleNamespace(attachment_id="a", filename="report.pdf", mime_type="application/pdf", id=5)
    mocker.patch.object(module, "build_workflow_attachment_id", return_value="a")
    create = mocker.patch.object(module, "create_workflow_attachment_asset", return_value=asset)
    mocker.patch.object(module, "build_signed_attachment_download_url", return_value="/download")
    result = module.generate_attachment_file.invoke(
        {"filename": "report.pdf", "file_type": "pdf", "sandbox_path": "/workspace/report.pdf"},
        config={"configurable": {"execution_id": "run", "python_sandbox": sandbox}},
    )
    assert result["file_url"] == "/download"
    assert create.call_args.kwargs["content_bytes"] == b"%PDF-document"
    sandbox.read_workspace_file.assert_called_once_with("/workspace/report.pdf")


def test_attachment_tool_rejects_mismatched_sandbox_file(mocker):
    import importlib

    module = importlib.import_module("apps.opspilot.metis.llm.tools.attachment.generate_attachment")
    sandbox = MagicMock()
    mocker.patch.object(module, "build_workflow_attachment_id", return_value="a")
    with pytest.raises(ValueError, match="扩展名"):
        module.generate_attachment_file.invoke(
            {"filename": "report.pdf", "file_type": "pdf", "sandbox_path": "/workspace/report.txt"},
            config={"configurable": {"execution_id": "run", "python_sandbox": sandbox}},
        )
    sandbox.read_workspace_file.assert_not_called()


@pytest.mark.skipif(not __import__("os").getenv("OPSPILOT_TEST_DOCKER"), reason="requires Docker")
def test_real_sandbox_to_attachment_preserves_binary(mocker):
    import importlib

    module = importlib.import_module("apps.opspilot.metis.llm.tools.attachment.generate_attachment")
    sandbox = PythonSandbox(image="python:3.12-alpine")
    try:
        payload = bytes(range(256)) * 500
        sandbox.write_workspace_file("/workspace/report.pdf", payload)
        asset = SimpleNamespace(attachment_id="a", filename="report.pdf", mime_type="application/pdf", id=5)
        mocker.patch.object(module, "build_workflow_attachment_id", return_value="a")
        create = mocker.patch.object(module, "create_workflow_attachment_asset", return_value=asset)
        mocker.patch.object(module, "build_signed_attachment_download_url", return_value="/download")
        result = module.generate_attachment_file.invoke(
            {"filename": "report.pdf", "file_type": "pdf", "sandbox_path": "/workspace/report.pdf"},
            config={"configurable": {"execution_id": "run", "python_sandbox": sandbox}},
        )
        assert result["file_url"] == "/download"
        assert create.call_args.kwargs["content_bytes"] == payload
    finally:
        sandbox.close()


@pytest.mark.skipif(not __import__("os").getenv("OPSPILOT_TEST_DOCKER"), reason="requires Docker")
def test_deepagents_skill_backend_shares_container_files():
    from apps.opspilot.services.python_sandbox.skill_backend import ContainerSkillBackend

    sandbox = PythonSandbox(image="python:3.12-alpine")
    backend = ContainerSkillBackend(sandbox)
    try:
        path = sandbox.store_result("41")
        result = backend.execute(f"python -c 'print(int(open(\"{path}\").read())+1)'")
        assert result.exit_code == 0
        assert result.output == "42"
        written = backend.write("/workspace/skills/demo/SKILL.md", "skill content")
        assert not written.error
        assert "skill content" in sandbox.execute("open('/workspace/skills/demo/SKILL.md').read()")
        assert backend.read("/workspace/skills/demo/SKILL.md").file_data["content"] == "skill content"
    finally:
        sandbox.close()


@pytest.mark.skipif(not __import__("os").getenv("OPSPILOT_TEST_DOCKER"), reason="requires Docker")
def test_skill_environment_is_scoped_and_output_is_redacted():
    from apps.opspilot.services.python_sandbox.skill_backend import ContainerSkillBackend

    sandbox = PythonSandbox(image="python:3.12-alpine")
    backend = ContainerSkillBackend(sandbox, params_by_package={"demo": {"API_KEY": "secret-sentinel"}}, secret_values=["secret-sentinel"])
    try:
        result = backend.execute("echo /workspace/skills/demo/test $API_KEY")
        assert result.exit_code == 0
        assert "secret-sentinel" not in result.output
        assert "***" in result.output
        result = backend.execute("echo ${API_KEY:-missing}")
        assert result.output == "missing"
    finally:
        sandbox.close()


@pytest.mark.skipif(not __import__("os").getenv("OPSPILOT_TEST_DOCKER"), reason="requires Docker")
def test_skill_command_supports_existing_virtual_skill_paths():
    from apps.opspilot.services.python_sandbox.skill_backend import ContainerSkillBackend

    sandbox = PythonSandbox(image="python:3.12-alpine")
    backend = ContainerSkillBackend(sandbox)
    try:
        sandbox.write_workspace_file("/workspace/skills/demo/script.py", b'print("skill-ok")')
        result = backend.execute("python /skills/demo/script.py")
        assert result.exit_code == 0
        assert result.output == "skill-ok"
    finally:
        sandbox.close()


@pytest.mark.skipif(not __import__("os").getenv("OPSPILOT_TEST_DOCKER"), reason="requires Docker")
def test_formal_skill_builder_uses_same_container_as_python(mocker, tmp_path):
    from apps.opspilot.metis.llm.chain.skill_sandbox import SkillSandboxMixin
    from apps.opspilot.services.python_sandbox.skill_backend import ContainerSkillBackend

    node = SkillSandboxMixin()
    mocker.patch.object(node, "_load_skill_package_runtime_params", return_value=({}, []))
    host_shell = mocker.patch("deepagents.backends.LocalShellBackend", side_effect=AssertionError("host execution"))
    sandbox = PythonSandbox(image="python:3.12-alpine")
    package = {
        "name": "demo",
        "scripts": {"change.py": 'from pathlib import Path\np=Path("/workspace/value.txt")\np.write_text(str(int(p.read_text())+1))'},
    }
    try:
        backend, sources, directory = node._build_skill_backend_and_sources(SimpleNamespace(extra_config={}), packages=[package], sandbox=sandbox)
        assert isinstance(backend, ContainerSkillBackend)
        assert sources == ["/workspace/skills/"] and directory is None
        assert sandbox.execute('open("/workspace/value.txt", "w").write("41")') == "2"
        result = backend.execute("python /skills/demo/scripts/change.py")
        assert result.exit_code == 0
        assert sandbox.read_workspace_file("/workspace/value.txt") == b"42"
        host_shell.assert_not_called()
    finally:
        sandbox.close()


def test_attachment_grant_rejects_tampering_before_query(mocker):
    from django.core import signing

    from apps.opspilot.services.python_sandbox.attachments import issue_attachment_grant, resolve_attachment_grant

    query = mocker.patch("apps.opspilot.models.ChatAttachment.objects.filter")
    token = issue_attachment_grant(owner_key="alice", team_id="a")
    with pytest.raises(signing.BadSignature):
        resolve_attachment_grant(token + "tampered")
    query.assert_not_called()


def test_attachment_grant_rechecks_owner_team_and_conversation(mocker):
    from apps.opspilot.services.python_sandbox.attachments import issue_attachment_grant, resolve_attachment_grant

    upload = SimpleNamespace(id=42, owner_key="alice", team_id="a")
    token = issue_attachment_grant(owner_key="alice", team_id="a", attachments=[upload])
    query = mocker.patch("apps.opspilot.models.ChatAttachment.objects.filter", return_value=[])
    mocker.patch("apps.opspilot.models.WorkflowAttachmentAsset.objects.filter", return_value=[])
    assert resolve_attachment_grant(token) == []
    assert query.call_args.kwargs == {"pk__in": [42], "owner_key": "alice", "team_id": "a", "status": "ready"}


def test_attachment_grant_expiration(mocker):
    from django.core import signing

    from apps.opspilot.services.python_sandbox.attachments import issue_attachment_grant, resolve_attachment_grant

    mocker.patch("django.core.signing.time.time", return_value=1000)
    token = issue_attachment_grant(owner_key="alice", team_id="a")
    mocker.patch("django.core.signing.time.time", return_value=5000)
    with pytest.raises(signing.SignatureExpired):
        resolve_attachment_grant(token)


def test_skill_and_attachment_plan_exposes_execute():
    from apps.opspilot.metis.llm.chain.deepagent_assembly import DeepAgentAssemblyMixin

    visible, hidden = DeepAgentAssemblyMixin._build_planned_execution_tool_visibility(
        skill_sources=["/workspace/skills/"],
        skills_only_plan=False,
        registered_tools=[],
    )
    assert "execute" in visible and "execute" not in hidden


@pytest.mark.asyncio
async def test_run_container_cleanup_on_setup_failure_preserves_exception(mocker, caplog):
    import logging

    from apps.opspilot.metis.llm.chain.node import ToolsNodes

    nodes = {}
    graph = SimpleNamespace(add_node=lambda name, fn: nodes.update({name: fn}))
    node = ToolsNodes()
    name = await node.build_deepagent_nodes(graph, composite_node_name="sandbox-test")
    sandbox = mocker.MagicMock()
    sandbox.close.side_effect = RuntimeError("secret-cleanup-sentinel")
    mocker.patch("apps.opspilot.services.python_sandbox.runtime.PythonSandbox", return_value=sandbox)
    error = RuntimeError("original-setup-error")
    mocker.patch.object(node, "get_llm_client", side_effect=error)
    request = SimpleNamespace(extra_config={}, system_message_prompt="", thread_id="cleanup-test")
    caplog.set_level(logging.WARNING, logger="opspilot")
    with pytest.raises(RuntimeError) as caught:
        await nodes[name]({"messages": []}, {"configurable": {"graph_request": request}})
    assert caught.value is error
    sandbox.close.assert_called_once()
    records = [r for r in caplog.records if "python_sandbox_cleanup_failed" in r.msg]
    assert len(records) == 1
    record = records[0]
    assert record.msg == "event=python_sandbox_cleanup_failed execution_id=%s failed_stage=cleanup error_type=%s"
    assert record.args == ("cleanup-test", "RuntimeError")
    assert record.getMessage().endswith("execution_id=cleanup-test failed_stage=cleanup error_type=RuntimeError")
    assert not record.exc_info
    assert "secret-cleanup-sentinel" not in logging.Formatter().format(record)


@pytest.mark.skipif(not __import__("os").getenv("OPSPILOT_TEST_DOCKER"), reason="requires built production sandbox image")
def test_ppt_master_materializes_and_exports_inside_production_container(mocker, tmp_path, monkeypatch):
    import io
    import zipfile
    from pathlib import Path

    from apps.opspilot.metis.llm.chain.skill_sandbox import SkillSandboxMixin
    from apps.opspilot.services.ppt_master_runtime import discard_ppt_run, inspect_ppt_run, newest_export_pptx, settle_ppt_export

    monkeypatch.setenv("OPSPILOT_PPT_TMP_ROOT", str(tmp_path))
    package_root = Path(__file__).resolve().parents[1] / "support-files" / "skill_packages" / "ppt-master"
    package = {"package_id": "ppt-master", "name": "ppt-master", "extracted_root": package_root}
    request = SimpleNamespace(extra_config={}, thread_id="ppt-container-test")
    node = SkillSandboxMixin()
    mocker.patch.object(node, "_load_skill_package_runtime_params", return_value=({}, []))
    sandbox = PythonSandbox()
    try:
        backend, _, directory = node._build_skill_backend_and_sources(request, packages=[package], sandbox=sandbox)
        for number in range(1, 4):
            svg = (
                '<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" viewBox="0 0 1280 720">'
                '<rect width="1280" height="720" fill="#fff"/>'
                f'<text x="80" y="150" font-size="42" font-family="Microsoft YaHei">容器验证 {number}</text></svg>'
            )
            assert not backend.write(f"/ppt-workspace/projects/demo/svg_output/slide_{number:02}.svg", svg).error
        assert inspect_ppt_run(Path(directory), sandbox=sandbox) == (False, 3)
        host_exec = mocker.patch("apps.opspilot.services.ppt_master_runtime.subprocess.run", side_effect=AssertionError("host exporter used"))
        execution = mocker.spy(sandbox, "execute_command")
        assert settle_ppt_export(Path(directory), sandbox=sandbox) == "exported", execution.spy_return.output
        host_exec.assert_not_called()
        data = newest_export_pptx(Path(directory)).read_bytes()
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            slides = [name for name in archive.namelist() if name.startswith("ppt/slides/slide") and name.endswith(".xml")]
            assert len(slides) == 3
    finally:
        sandbox.close()
        discard_ppt_run(request)
