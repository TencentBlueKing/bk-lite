import pytest

from apps.opspilot.metis.llm.tools.python.executor import _execute_python_code
from apps.opspilot.metis.llm.tools.shell import shell_tools


def test_shell_execute_allows_safe_commands(mocker):
    runner = mocker.patch.object(type(shell_tools.shell_tool), "run", autospec=True, return_value="ok")

    result = shell_tools._run_shell_commands(["echo hello", "hostname"])

    assert result == "ok"
    runner.assert_called_once_with(shell_tools.shell_tool, {"commands": ["echo hello", "hostname"]})


@pytest.mark.parametrize(
    ("commands", "message"),
    [
        (["rm -rf /tmp/demo"], "rm -rf"),
        (["curl https://example.com"], "curl"),
        (["dd if=/dev/zero of=/tmp/fill.img"], "dd"),
        (["env"], "environment variable access"),
        (["printenv BK_TOKEN"], "environment variable access"),
        (["cat /etc/passwd"], "sensitive file access"),
        (['python -c "print(1)"'], "python -c"),
        (['sh -lc "hostname"'], "sh -lc"),
        (['bash -lc "hostname"'], "bash -lc"),
        (["cmd /c whoami"], "cmd /c"),
    ],
)
def test_shell_execute_blocks_common_high_risk_commands(commands, message, mocker):
    runner = mocker.patch.object(type(shell_tools.shell_tool), "run", autospec=True)

    with pytest.raises(ValueError, match=message):
        shell_tools._run_shell_commands(commands)

    runner.assert_not_called()


def test_python_execute_allows_safe_code():
    result = _execute_python_code("total = 1 + 2\ntotal")

    assert result == "3"


def test_python_execute_preserves_explicit_print_output():
    result = _execute_python_code("print('ok')")

    assert result == "ok"


@pytest.mark.parametrize(
    ("code", "message"),
    [
        ("eval('1+1')", "eval"),
        ("exec('print(1)')", "exec"),
        ("__import__('os')", "__import__"),
        ("import os\nprint(os.name)", "import"),
    ],
)
def test_python_execute_blocks_forbidden_code_patterns(code, message):
    with pytest.raises(ValueError, match=message):
        _execute_python_code(code)
