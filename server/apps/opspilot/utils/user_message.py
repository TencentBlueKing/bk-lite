"""把返回给页面的错误文案按请求语言取出。缺词条时用调用方给出的中文原句。

优先用 ViewSet 上的 loader（LanguageViewSet 已按页面语言 / 账号 locale 装好）。
没有 loader 时，只按 request.user.locale 再建一个。
"""

from apps.core.utils.loader import LanguageLoader


# 只有这个 code 才换成「知识库构建中」文案。其它队列错误走自己的词条或原句。
BUILD_CONFLICT_CODE = "knowledge_base_build_in_progress"

# 三句近义冲突文案按稳定变体选取，不看中文标点或「重试」。
BUILD_CONFLICT_RUNNING = "running"
BUILD_CONFLICT_WAIT = "wait"
BUILD_CONFLICT_RETRY = "retry"

_BUILD_CONFLICT_KEYS = {
    BUILD_CONFLICT_RUNNING: "error.knowledge_base_build_running",
    BUILD_CONFLICT_WAIT: "error.knowledge_base_build_running_wait",
    BUILD_CONFLICT_RETRY: "error.knowledge_base_build_running_retry",
}


def user_message(request, key: str, default: str, loader=None) -> str:
    active = loader
    if active is None and request is not None:
        locale = getattr(getattr(request, "user", None), "locale", None) or "en"
        active = LanguageLoader(app="opspilot", default_lang=locale)
    if active is None:
        return default
    text = active.get(key)
    return text or default


def build_conflict_message(request, message: str, loader=None, *, code: str | None = None, variant: str | None = None) -> str:
    """仅当 code 是构建冲突时按变体取词条。其它 code 原样返回。"""
    if code != BUILD_CONFLICT_CODE:
        return message
    key = _BUILD_CONFLICT_KEYS.get(variant or BUILD_CONFLICT_RUNNING) or _BUILD_CONFLICT_KEYS[BUILD_CONFLICT_RUNNING]
    return user_message(request, key, message, loader)


def queue_error_message(request, error, loader=None) -> str:
    """MaterialBuildQueueError 的页面文案。

    构建冲突按 conflict_variant 翻译。其它 code 用 error.<code>，没有词条就保留原句。
    """
    code = getattr(error, "code", None) or ""
    message = getattr(error, "message", None) or str(error)
    if code == BUILD_CONFLICT_CODE:
        return build_conflict_message(
            request,
            message,
            loader,
            code=code,
            variant=getattr(error, "conflict_variant", None),
        )
    if code:
        return user_message(request, f"error.{code}", message, loader)
    return message
