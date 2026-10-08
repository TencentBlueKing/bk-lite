"""告警模块面向用户的文案。日志、种子数据和已落库内容不走这里。"""

from typing import Any

from apps.core.utils.loader import LanguageLoader


def resolve_alerts_language(locale: Any = None) -> str:
    raw = str(locale or "zh-Hans").strip() or "zh-Hans"
    return "zh-Hans" if raw.lower().startswith("zh") else "en"


def _locale_from(source: Any) -> Any:
    if source is None or isinstance(source, str):
        return source
    user = getattr(source, "user", source)
    return getattr(user, "locale", None)


def alerts_message(source: Any, key: str, **values: Any) -> str:
    language = resolve_alerts_language(_locale_from(source))
    template = LanguageLoader(app="alerts", default_lang=language).get(key) or key
    try:
        return str(template).format(**values)
    except (KeyError, ValueError):
        return str(template)


def serializer_message(serializer: Any, key: str, **values: Any) -> str:
    request = getattr(serializer, "context", {}).get("request")
    return alerts_message(request, key, **values)
