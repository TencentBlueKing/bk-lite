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
