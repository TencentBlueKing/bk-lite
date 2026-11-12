"""Run the production execution interface without Docker or an LLM."""
import shlex
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from langchain_core.messages import ToolMessage

from apps.opspilot.metis.llm.middleware.python_sandbox import PythonSandboxMiddleware
from apps.opspilot.services.python_sandbox.runtime import PythonSandbox, SandboxUnavailable


@pytest.fixture
def runtime():
    runtime = PythonSandbox()
    yield runtime
    runtime.close()


def test_large_result_is_local_file_without_starting_process(runtime, mocker):
    launch = mocker.patch("subprocess.Popen", side_effect=AssertionError("storage must not execute code"))
    payload = '[{"value":2},' + '{"value":3},' * 1000 + '{"value":4}]'
    message = ToolMessage(content=payload, tool_call_id="alerts", name="alerts")
    result = PythonSandboxMiddleware(runtime).wrap_tool_call(SimpleNamespace(tool_call={"name": "alerts"}), lambda _: message)
    path = runtime.files()[0]
    assert Path(path).read_text() == payload
    assert path in result.content and len(result.content) < len(payload)
    assert result.tool_call_id == "alerts"
    launch.assert_not_called()


def test_python_and_shell_use_server_interpreter_and_shared_cwd(runtime, tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PASSWORD", "server-secret-sentinel")
    host_file = tmp_path / "host.txt"
    host_file.write_text("host-visible")
    path = runtime.store_result('[{"value":3},{"value":4}]')
    assert runtime.execute(f"import json\nsum(r['value'] for r in json.load(open({path!r})))") == "7"
    assert runtime.execute_command('python -c \'import pathlib; pathlib.Path("answer.txt").write_text("中文")\'').exit_code == 0
    assert runtime.execute("open('answer.txt').read()") == "中文"
    assert runtime.execute(f"open({str(host_file)!r}).read()") == "host-visible"
    assert runtime.execute("import os\nos.getenv('DB_PASSWORD', 'absent')") == "absent"
    assert runtime.execute("import os\nos.getcwd()") == runtime.workspace
    assert Path(runtime.workspace).is_dir()


def test_close_removes_only_this_run_and_disallows_reuse(runtime):
    other = PythonSandbox()
    try:
        first = Path(runtime.store_result("first"))
        second = Path(other.store_result("second"))
        runtime.close()
        runtime.close()
        assert not first.parent.exists()
        assert second.read_text() == "second"
        with pytest.raises(SandboxUnavailable):
            runtime.execute("42")
    finally:
        other.close()


def test_close_interrupts_active_process(runtime):
    outputs = []
    worker = threading.Thread(target=lambda: outputs.append(runtime.execute_command("echo ready > started; sleep 30")))
    started = Path(runtime.workspace) / "started"
    worker.start()
    import time

    deadline = time.monotonic() + 5
    while not started.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert started.exists()
    runtime.close()
    worker.join(timeout=5)
    assert not worker.is_alive()
    assert outputs[0].exit_code != 0
    assert not started.parent.exists()


def test_timeout_kills_child_processes_and_next_call_recovers(runtime, tmp_path):
    marker = tmp_path / "leaked-child"
    command = "python -c " + shlex.quote(f"import time,pathlib; time.sleep(2); pathlib.Path({str(marker)!r}).touch()") + " & wait"
    result = runtime.execute_command(command, timeout=0.1)
    assert result.exit_code != 0
    assert "超时" in result.output
    assert runtime.execute("6*7") == "42"
    import time

    time.sleep(2.1)
    assert not marker.exists()


def test_output_is_bounded_but_failure_and_unicode_are_preserved(runtime):
    output = runtime.execute_command('python -c \'print("x"*100000); print("错误"); raise SystemExit(7)\'')
    assert output.truncated and len(output.output) < 66000 and output.exit_code == 7
    assert "[输出已截断]" in output.output
    assert "ZeroDivisionError" in runtime.execute("1/0")


def test_attachment_file_interface_rejects_other_paths_and_links(runtime, tmp_path):
    outside = tmp_path / "private"
    outside.write_bytes(b"private")
    target = Path(runtime.workspace) / "artifact.bin"
    runtime.write_workspace_file(str(target), bytes(range(256)))
    assert runtime.read_workspace_file(str(target)) == bytes(range(256))
    with pytest.raises(ValueError):
        runtime.read_workspace_file(str(outside))
    target.unlink()
    target.symlink_to(outside)
    with pytest.raises((ValueError, SandboxUnavailable)):
        runtime.read_workspace_file(str(target))
    with pytest.raises((ValueError, SandboxUnavailable)):
        runtime.write_workspace_file(str(target), b"overwrite")
    assert outside.read_bytes() == b"private"


def test_dependency_environment_is_local_to_run(runtime):
    import json

    data = json.loads(
        runtime.execute("import json,os\nprint(json.dumps({k:os.environ[k] for k in ['HOME','TMPDIR','PIP_TARGET','NPM_CONFIG_PREFIX']}))")
    )
    assert all(Path(path).is_relative_to(runtime.workspace) for path in data.values())
    packages = Path(data["PIP_TARGET"])
    packages.mkdir(parents=True, exist_ok=True)
    (packages / "opspilot_local_probe.py").write_text("value=42")
    assert runtime.execute("import opspilot_local_probe\nopspilot_local_probe.value") == "42"


@pytest.mark.asyncio
async def test_skill_filesystem_async_aliases_share_python_files(runtime):
    from apps.opspilot.services.python_sandbox.skill_backend import LocalSkillBackend

    backend = LocalSkillBackend(runtime, secret_values=["file-secret-sentinel"])
    assert not (await backend.awrite("/skills/demo/SKILL.md", "original text")).error
    assert (await backend.aread("/skills/demo/SKILL.md")).file_data["content"] == "original text"
    assert not (await backend.aedit("/skills/demo/SKILL.md", "original", "revised")).error
    assert runtime.execute("open('skills/demo/SKILL.md').read()") == "revised text"
    assert not (await backend.awrite("/ppt-workspace/report.txt", "PPT workspace")).error
    assert runtime.read_workspace_file(runtime.workspace + "/ppt-workspace/report.txt") == b"PPT workspace"
    assert (await backend.als("/skills/demo")).entries[0]["path"].endswith("/skills/demo/SKILL.md")
    runtime.write_workspace_file(runtime.workspace + "/skills/demo/.skillenv", b"API_KEY=file-secret-sentinel")
    assert (await backend.aread("/skills/demo/.skillenv")).file_data["content"] == "API_KEY=***"
    assert runtime.read_workspace_file(runtime.workspace + "/skills/demo/.skillenv") == b"API_KEY=file-secret-sentinel"
