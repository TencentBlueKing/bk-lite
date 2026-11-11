"""Shell commands execute only in the agent's shared task container."""

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.opspilot.services.python_sandbox.runtime import SandboxUnavailable


@tool(parse_docstring=True)
def shell_execute(commands: list[str], config: RunnableConfig) -> str:
    """在当前任务的隔离容器中执行 shell 命令，与 Python、技能 execute 共享 /workspace。

    支持 curl、管道、重定向和脚本执行。文件和环境变量属于容器，不代表宿主或目标主机。
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
        return "Shell 隔离环境不可用：当前任务没有配置沙箱"
    try:
        # Preserve the old BashProcess batch semantics: one shell, sequential
        # commands, with cwd/variables shared inside this call.
        return sandbox.execute_command(";".join(commands)).output
    except SandboxUnavailable:
        return "Shell 隔离环境不可用，请检查 Docker 和沙箱镜像配置"
