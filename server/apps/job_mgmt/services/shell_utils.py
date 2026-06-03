"""Shell 解释器工具函数"""

from typing import Optional

# 支持的解释器白名单：非白名单的 Shebang 解析结果将被忽略，回退到默认值
SUPPORTED_SHELLS = {"sh", "bash", "python", "python3", "powershell", "pwsh"}

# ansible_shell_executable 只支持真正的 shell，不能设为 python/powershell
ANSIBLE_SHELL_EXECUTABLES = {"sh", "bash"}


def parse_shebang(script: str) -> Optional[str]:
    """
    解析脚本首行 Shebang，提取解释器名称。

    支持格式：
    - #!/bin/bash          -> "bash"
    - #!/bin/sh            -> "sh"
    - #!/usr/bin/env bash  -> "bash"
    - #!/usr/bin/python3   -> "python3"

    解析结果不在 SUPPORTED_SHELLS 白名单时返回 None，由调用方回退到默认值。

    Args:
        script: 脚本内容（完整字符串）

    Returns:
        解释器名称（在白名单内），或 None（无 Shebang / 解释器不在白名单）
    """
    if not script:
        return None

    first_line = script.splitlines()[0].strip()
    if not first_line.startswith("#!"):
        return None

    shebang_content = first_line[2:].strip()
    parts = shebang_content.split()
    if not parts:
        return None

    # #!/usr/bin/env bash -> parts = ["/usr/bin/env", "bash"] -> 取 parts[1]
    # #!/bin/bash         -> parts = ["/bin/bash"]             -> 取路径末段 "bash"
    if parts[0].endswith("/env") and len(parts) > 1:
        interpreter = parts[1]
    else:
        interpreter = parts[0].rsplit("/", 1)[-1]

    if interpreter in SUPPORTED_SHELLS:
        return interpreter
    return None


def build_heredoc_command(interpreter: str, script: str) -> str:
    """
    构造通过指定解释器读取 heredoc 的命令字符串。

    用于无法通过 ansible_shell_executable 直接切换解释器的场景，
    例如 python3 / pwsh 需要显式作为命令入口执行。
    """
    return f"{interpreter} <<'__SCRIPT__'\n{script}\n__SCRIPT__"
