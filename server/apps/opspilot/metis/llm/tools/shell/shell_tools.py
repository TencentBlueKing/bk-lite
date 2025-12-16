
from langchain_community.tools import ShellTool
from langchain_core.tools import tool

# 兼容 tools_loader 自动发现，导出一个 @tool 装饰的 shell_execute
shell_tool = ShellTool()


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
    return shell_tool.run({"commands": commands})
