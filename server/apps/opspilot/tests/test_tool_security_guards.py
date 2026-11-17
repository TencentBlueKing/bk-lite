import pytest

from apps.opspilot.metis.llm.tools.python.executor import _execute_python_code
from apps.opspilot.metis.llm.tools.shell import shell_tools


def test_shell_execute_uses_shared_runtime_without_legacy_shell(mocker, capsys, caplog):
    from types import SimpleNamespace

    sandbox = mocker.Mock()
    sandbox.execute_command.return_value = SimpleNamespace(output="ok")
    host = mocker.patch("langchain_community.tools.ShellTool", side_effect=AssertionError("host shell"))
    sentinel = "shell-command-secret-sentinel"
    commands = ["cd /workspace", f"echo {sentinel}"]
    result = shell_tools.shell_execute.invoke({"commands": commands}, config={"configurable": {"python_sandbox": sandbox}})
    assert result == "ok"
    sandbox.execute_command.assert_called_once_with(";".join(commands))
    host.assert_not_called()
    captured = capsys.readouterr()
    assert sentinel not in captured.out + captured.err + caplog.text


@pytest.mark.parametrize(
    "command",
    [
        "curl --version",
        "wget --help",
        "env",
        'python -c "print(1)"',
        'sh -c "hostname"',
        'bash -lc "hostname"',
        "rm -rf /workspace/temporary",
    ],
)
def test_shell_commands_are_delegated_to_runtime_without_command_blacklist(command, mocker):
    from types import SimpleNamespace

    sandbox = mocker.Mock()
    sandbox.execute_command.return_value = SimpleNamespace(output="ok")
    assert shell_tools.shell_execute.invoke({"commands": [command]}, config={"configurable": {"python_sandbox": sandbox}}) == "ok"
    sandbox.execute_command.assert_called_once_with(command)


@pytest.mark.parametrize("commands", [[], [""], ["echo ok", "  "]])
def test_shell_rejects_empty_commands_before_execution(commands, mocker):
    sandbox = mocker.Mock()
    with pytest.raises(ValueError, match="空"):
        shell_tools.shell_execute.invoke({"commands": commands}, config={"configurable": {"python_sandbox": sandbox}})
    sandbox.execute_command.assert_not_called()


def test_shell_missing_or_unavailable_workspace_never_falls_back(mocker):
    from apps.opspilot.services.python_sandbox.runtime import SandboxUnavailable

    host = mocker.patch("subprocess.run", side_effect=AssertionError("host shell"))
    assert "没有配置工作区" in shell_tools.shell_execute.invoke({"commands": ["echo test"]}, config={"configurable": {}})
    sandbox = mocker.Mock()
    sandbox.execute_command.side_effect = SandboxUnavailable("secret-daemon-error")
    result = shell_tools.shell_execute.invoke({"commands": ["echo test"]}, config={"configurable": {"python_sandbox": sandbox}})
    assert "执行环境不可用" in result and "secret-daemon-error" not in result
    host.assert_not_called()


def test_shell_runtime_configuration_is_not_a_model_argument():
    assert set(shell_tools.shell_execute.tool_call_schema.model_fields) == {"commands"}


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


@pytest.mark.parametrize(
    "code",
    [
        # BL-NEW-001 文档 PoC：经无害对象继承链取得 os.system 执行系统命令。
        "().__class__.__bases__[0].__subclasses__()",
        "''.__class__.__mro__[1].__subclasses__()",
        "[].__class__.__base__.__subclasses__()[0].__init__.__globals__",
        "(lambda: 0).__globals__",
        "type('x', (), {}).__subclasses__",
    ],
)
def test_python_execute_blocks_object_chain_sandbox_escape(code):
    """对象继承链 / dunder 反射逃逸必须被拦截（攻击者借此拿到 os/subprocess）。"""
    with pytest.raises(ValueError, match="(危险属性|禁止使用的标识符)"):
        _execute_python_code(code)


@pytest.mark.parametrize(
    ("code", "message"),
    [
        ("getattr(str, 'mro')", "getattr"),
        ("globals()", "globals"),
        ("open('/etc/passwd')", "open"),
        ("compile('1', 'x', 'eval')", "compile"),
        ("vars(str)", "vars"),
    ],
)
def test_python_execute_blocks_reflection_builtins(code, message):
    """反射 / 文件 / 动态编译类内建函数被 AST 层按名字拦截。"""
    with pytest.raises(ValueError, match=message):
        _execute_python_code(code)


def test_python_execute_allows_dunder_free_attribute_access():
    """非 dunder 的普通属性访问不受影响（如 str 方法），确保不误伤正常代码。"""
    assert _execute_python_code("'Hello'.upper()") == "HELLO"
