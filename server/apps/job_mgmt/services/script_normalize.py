"""脚本换行符规范化公共函数。

集中使用, 避免在 serializer / service / runner 多处重复;
行为必须与历史 ``ExecutionTaskBaseService.normalize_script_line_endings`` 完全一致。
"""

from typing import Optional

from apps.job_mgmt.constants import ScriptType


def normalize_script_line_endings(script_content: Optional[str], script_type: Optional[str]) -> str:
    """规范化脚本换行符 - CRLF 或 CR 全部转 LF。

    - 空串或 None: 原样返回空串
    - BAT 或 POWERSHELL: 保持原样 (Windows 原生脚本依赖 CRLF)
    - 其他类型: CRLF 与裸 CR 统一转 LF

    Idempotent: 已是 LF 的脚本返回相同字符串。
    """
    if not script_content:
        return script_content or ""
    if script_type in (ScriptType.BAT, ScriptType.POWERSHELL):
        return script_content
    return script_content.replace("\r\n", "\n").replace("\r", "\n")
