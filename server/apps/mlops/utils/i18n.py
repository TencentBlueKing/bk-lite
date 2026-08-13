"""MLOps 面向 API 用户的文案国际化工具。"""

from typing import Any

from apps.core.utils.loader import LanguageLoader


def resolve_mlops_language(locale: Any = None) -> str:
    """将用户 locale 归一为 mlops 语言包名。"""
    raw = str(locale or "zh-Hans").strip() or "zh-Hans"
    return "zh-Hans" if raw.lower().startswith("zh") else "en"


def mlops_message_for_locale(locale: Any, key: str, **values: Any) -> str:
    """按显式 locale 读取并格式化 MLOps 文案。"""
    language = resolve_mlops_language(locale)
    template = LanguageLoader(app="mlops", default_lang=language).get(key, key) or key
    try:
        return str(template).format(**values)
    except (KeyError, ValueError):
        return str(template)


def mlops_message(request: Any, key: str, *_legacy_default: str, **values: Any) -> str:
    """按请求用户语言读取并格式化 MLOps 文案。"""
    user = getattr(request, "user", None)
    locale = getattr(user, "locale", None) or "zh-Hans"
    return mlops_message_for_locale(locale, key, **values)


def serializer_message(serializer: Any, key: str, default: str = "", **values: Any) -> str:
    """在 DRF Serializer 中复用请求语言。"""
    request = getattr(serializer, "context", {}).get("request")
    return mlops_message(request, key, default, **values)
