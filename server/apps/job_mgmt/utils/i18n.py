"""作业平台展示字段的国际化工具。"""

from typing import Any

from apps.core.utils.loader import LanguageLoader


def _normalize_locale(locale: str | None) -> str:
    normalized = (locale or "zh-Hans").lower().replace("_", "-")
    return "zh-Hans" if normalized.startswith("zh") else "en"


def get_job_loader(request: Any = None) -> LanguageLoader:
    user = getattr(request, "user", None)
    locale = _normalize_locale(getattr(user, "locale", None))
    return LanguageLoader(app="job_mgmt", default_lang=locale)


def job_message(request: Any, key: str, default: str, **values: Any) -> str:
    template = get_job_loader(request).get(key, default) or default
    try:
        return str(template).format(**values)
    except (KeyError, ValueError):
        return str(template)


def serializer_message(serializer: Any, key: str, default: str, **values: Any) -> str:
    request = getattr(serializer, "context", {}).get("request")
    return job_message(request, key, default, **values)


def choice_message(serializer: Any, category: str, value: str, default: str) -> str:
    return serializer_message(serializer, f"choice.{category}.{value}", default)


def localize_execution_name(request: Any, name: str) -> str:
    """仅翻译系统生成的执行名称，用户输入和落库值保持不变。"""
    prefix = "[手动触发] "
    if isinstance(name, str) and name.startswith(prefix):
        return job_message(request, "message.manual_trigger_name", name, name=name[len(prefix) :])
    return name
