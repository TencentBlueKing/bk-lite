"""MLOps 面向 API 用户的文案国际化工具。"""

from typing import Any

from apps.core.utils.loader import LanguageLoader


def mlops_message(request: Any, key: str, *_legacy_default: str, **values: Any) -> str:
    """按请求用户语言读取并格式化 MLOps 文案。"""
    user = getattr(request, "user", None)
    locale = getattr(user, "locale", None) or "zh-Hans"
    language = "zh-Hans" if locale.lower().startswith("zh") else "en"
    template = LanguageLoader(app="mlops", default_lang=language).get(key, key) or key
    try:
        return str(template).format(**values)
    except (KeyError, ValueError):
        return str(template)


def serializer_message(serializer: Any, key: str, default: str = "", **values: Any) -> str:
    """在 DRF Serializer 中复用请求语言。"""
    request = getattr(serializer, "context", {}).get("request")
    return mlops_message(request, key, default, **values)
