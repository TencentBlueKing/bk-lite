"""Shell commands execute in the Server's local task workspace."""

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.opspilot.services.python_sandbox.runtime import SandboxUnavailable


@tool(parse_docstring=True)
def shell_execute(commands: list[str], config: RunnableConfig) -> str:
    """在 Server 内执行 shell 命令，与 Python、技能 execute 共享本轮工作目录。

    支持 curl、管道、重定向和脚本执行。这是本地执行环境，拥有 Server 运行用户的系统权限，不提供宿主隔离。
    命令列表在同一 shell 中依次执行，保留列表内的 cd 和变量；默认总超时 120 秒。
    非交互执行，合并输出最多 64 KiB。访问目标主机应使用对应的 SSH 或 K8s 工具。

    Args:
        commands: shell 命令列表，按顺序执行；遇到非零退出码是否继续由 shell 语义决定

    Returns:
        合并的标准输出和标准错误，执行失败时附带退出码
    """
    if not commands or any(not command.strip() for command in commands):
        raise ValueError("命令列表不能为空，且不能包含空命令")
    sandbox = (config or {}).get("configurable", {}).get("python_sandbox")
    if sandbox is None:
        return "Shell 执行环境不可用：当前任务没有配置工作区"
    try:
        # Preserve the old BashProcess batch semantics: one shell, sequential
        # commands, with cwd/variables shared inside this call.
        return sandbox.execute_command(";".join(commands)).output
    except SandboxUnavailable:
        return "Shell 执行环境不可用，请检查 Server 的 Shell 和任务工作目录"
