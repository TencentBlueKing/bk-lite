"""记录智能体工具绑定的替换。只记 id 和名称，不记 kwargs。"""

from apps.core.logger import opspilot_logger as logger

_MAX_TOOLS = 20
_MAX_TOKEN = 64


def _one_line(value, limit: int) -> str:
    text = " ".join(str(value or "").split())
    return text[:limit]


def _summarize_skill_tools(tools) -> tuple[int, str]:
    if not isinstance(tools, list):
        return 0, "-"
    parts = []
    for tool in tools[:_MAX_TOOLS]:
        if not isinstance(tool, dict):
            parts.append("-")
            continue
        tool_id = tool.get("id")
        id_text = str(tool_id) if isinstance(tool_id, int) else "-"
        name = _one_line(tool.get("name"), _MAX_TOKEN) or "-"
        parts.append(f"{id_text}:{name}")
    extra = len(tools) - len(parts)
    summary = ",".join(parts) if parts else "-"
    if extra > 0:
        summary = f"{summary},+{extra}"
    return len(tools), summary


def skill_tools_before_save(params, current):
    """请求带 tools 时留下保存前的名单。不带则返回 None，表示这次不替换。"""
    if not isinstance(params, dict) or "tools" not in params:
        return None
    return list(current or [])


def log_skill_tools_replaced(*, skill_id, actor, before, after) -> None:
    """工具名单发生变化时记一条。相同名单不记。before 为 None 表示本次没有替换。"""
    if before is None:
        return
    before_count, before_text = _summarize_skill_tools(before)
    after_count, after_text = _summarize_skill_tools(after)
    if before_count == after_count and before_text == after_text:
        return
    logger.info(
        "event=skill_tools_replaced skill_id=%s actor=%s before_count=%s after_count=%s before=%s after=%s",
        skill_id,
        _one_line(actor, _MAX_TOKEN) or "-",
        before_count,
        after_count,
        before_text,
        after_text,
    )
