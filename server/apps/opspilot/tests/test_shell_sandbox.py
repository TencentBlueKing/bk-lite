"""Shell tool integration with the local Server task workspace."""
import shlex

import pytest

from apps.opspilot.metis.llm.tools.python.executor import python_execute_direct
from apps.opspilot.metis.llm.tools.shell.shell_tools import shell_execute
from apps.opspilot.services.python_sandbox.runtime import PythonSandbox
from apps.opspilot.services.python_sandbox.skill_backend import LocalSkillBackend


@pytest.fixture
def runtime():
    sandbox = PythonSandbox()
    try:
        yield sandbox
    finally:
        sandbox.close()


def test_shell_shares_files_with_python_and_skills_with_local_server_access(runtime, tmp_path, monkeypatch):
    host_file = tmp_path / "host-only.txt"
    host_file.write_text("host-file-sentinel")
    monkeypatch.setenv("OPSPILOT_HOST_ONLY_SECRET", "host-env-sentinel")
    config = {"configurable": {"python_sandbox": runtime}}
    commands = [
        "mkdir -p data",
        "cd data",
        "value=41",
        "printf '%s' \"$value\" > input.txt",
        "pwd",
        "printf '%s' \"${OPSPILOT_HOST_ONLY_SECRET:-absent}\"",
    ]
    result = shell_execute.invoke({"commands": commands}, config=config)
    assert result == runtime.workspace + "/data\nabsent"
    assert "host-env-sentinel" not in result
    assert python_execute_direct.invoke({"code": "p='data/input.txt'\nopen(p).read()"}, config=config) == "41"
    backend = LocalSkillBackend(runtime)
    assert (
        backend.execute(
            "python -c 'from pathlib import Path; " 'Path("output.txt").write_text(str(int(Path("data/input.txt").read_text())+1))\''
        ).exit_code
        == 0
    )
    assert shell_execute.invoke({"commands": ["cat output.txt"]}, config=config) == "42"
    # Each call starts at its task directory, while files persist for the entire task.
    assert shell_execute.invoke({"commands": ["pwd"]}, config=config) == runtime.workspace
    attempted = shell_execute.invoke({"commands": [f"printf changed > {shlex.quote(str(host_file))}"]}, config=config)
    assert "Exit code:" not in attempted
    assert host_file.read_text() == "changed"
    assert shell_execute.invoke({"commands": ["curl --version"]}, config=config).startswith("curl ")
    assert "中文输出" in shell_execute.invoke({"commands": ["python -c 'print(\"中文输出\")'"]}, config=config)
    other = PythonSandbox()
    try:
        assert "Exit code:" in shell_execute.invoke({"commands": ["cat output.txt"]}, config={"configurable": {"python_sandbox": other}})
    finally:
        other.close()


def test_shell_returns_failures_and_bounded_output(runtime, monkeypatch):
    config = {"configurable": {"python_sandbox": runtime}}
    assert "Exit code: 7" in shell_execute.invoke({"commands": ["echo failed >&2", "exit 7"]}, config=config)
    # Preserve the previous semicolon-separated batch behavior.
    assert shell_execute.invoke({"commands": ["false", "printf continued"]}, config=config) == "continued"
    output = shell_execute.invoke({"commands": ["python -c 'print(\"x\" * 100000)'"]}, config=config)
    assert "[输出已截断]" in output and len(output) < 66000
    original = runtime.execute_command
    monkeypatch.setattr(runtime, "execute_command", lambda command: original(command, timeout=1))
    assert "Exit code:" in shell_execute.invoke({"commands": ["sleep 10"]}, config=config)
    assert shell_execute.invoke({"commands": ["printf recovered"]}, config=config) == "recovered"
