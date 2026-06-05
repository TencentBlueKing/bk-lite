import re

from langchain_community.tools import ShellTool
from langchain_core.tools import tool

# 兼容 tools_loader 自动发现，导出一个 @tool 装饰的 shell_execute
shell_tool = ShellTool()

FORBIDDEN_SHELL_PATTERNS = (
    (re.compile(r"\brm\s+-rf\b", re.IGNORECASE), "rm -rf"),
    (re.compile(r"\bdd\b", re.IGNORECASE), "dd"),
    (re.compile(r"\bmkfs(?:\.\w+)?\b", re.IGNORECASE), "mkfs"),
    (re.compile(r"\bcurl\b", re.IGNORECASE), "curl"),
    (re.compile(r"\bwget\b", re.IGNORECASE), "wget"),
    (re.compile(r"\b(?:env|printenv)\b", re.IGNORECASE), "environment variable access"),
    (re.compile(r"\bcat\s+/(?:etc/(?:passwd|shadow)|root/\.ssh/authorized_keys)\b", re.IGNORECASE), "sensitive file access"),
    (re.compile(r"\bpython(?:3)?\s+-c\b", re.IGNORECASE), "python -c"),
    (re.compile(r"\bsh\s+-c\b", re.IGNORECASE), "sh -c"),
    (re.compile(r"\bsh\s+-lc\b", re.IGNORECASE), "sh -lc"),
    (re.compile(r"\bbash\s+-c\b", re.IGNORECASE), "bash -c"),
    (re.compile(r"\bbash\s+-lc\b", re.IGNORECASE), "bash -lc"),
    (re.compile(r"\bcmd(?:\.exe)?\s+/c\b", re.IGNORECASE), "cmd /c"),
    (re.compile(r"\bpowershell(?:\.exe)?\b", re.IGNORECASE), "powershell"),
    (re.compile(r"\b(?:sudo|su|passwd)\b", re.IGNORECASE), "privileged command"),
)


def _validate_shell_commands(commands: list[str]) -> None:
    for command in commands:
        normalized = (command or "").strip()
        if not normalized:
            raise ValueError("命令不能为空")
        for pattern, keyword in FORBIDDEN_SHELL_PATTERNS:
            if pattern.search(normalized):
                raise ValueError(f"检测到禁止执行的高危命令: {keyword}")


def _run_shell_commands(commands: list[str]) -> str:
    _validate_shell_commands(commands)
    return shell_tool.run({"commands": commands})


@tool(parse_docstring=True)
def shell_execute(commands: list[str]) -> str:
    """
    在系统 shell 中执行一组命令,用于自动化运维、构建、部署、信息获取等场景。
        要求:
            1. 不允许执行高危命令(如 rm -rf /, dd, mkfs 等)
            2. 不允许执行需要交互式输入的命令
            3. 不允许执行可能泄露敏感信息的命令
            4. 执行前应明确命令用途与风险

    Args:
        commands: 要执行的 shell 命令列表,按顺序执行

    Returns:
        所有命令的执行结果(stdout 和 stderr 合并输出)
    """
    return _run_shell_commands(commands)
