"""控制台用户可见文案。"""

from typing import Any

from apps.core.utils.loader import LanguageLoader


def console_message(request: Any, key: str, default: str, **values: Any) -> str:
    user = getattr(request, "user", None)
    locale = getattr(user, "locale", None) or "zh-Hans"
    template = LanguageLoader(app="console_mgmt", default_lang=locale).get(key, default) or default
    try:
        return str(template).format(**values)
    except (KeyError, ValueError):
        return str(template)
