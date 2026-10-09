"""把返回给页面的错误文案按请求语言取出。缺词条时用调用方给出的中文原句。

优先用 ViewSet 上的 loader（LanguageViewSet 已按页面语言 / 账号 locale 装好）。
没有 loader 时，只按 request.user.locale 再建一个。
"""

from apps.core.utils.loader import LanguageLoader


def user_message(request, key: str, default: str, loader=None) -> str:
    active = loader
    if active is None and request is not None:
        locale = getattr(getattr(request, "user", None), "locale", None) or "en"
        active = LanguageLoader(app="opspilot", default_lang=locale)
    if active is None:
        return default
    text = active.get(key)
    return text or default


def build_conflict_message(request, message: str, loader=None) -> str:
    """构建冲突有三句中文，按原句选词条，避免英文界面仍弹出中文。"""
    if "重试" in message:
        key = "error.knowledge_base_build_running_retry"
    elif "，" in message:
        key = "error.knowledge_base_build_running_wait"
    else:
        key = "error.knowledge_base_build_running"
    return user_message(request, key, message, loader)
