from typing import Any

from apps.core.utils.loader import LanguageLoader


def _normalize_locale(locale: str | None) -> str:
    normalized = (locale or "zh-Hans").lower().replace("_", "-")
    return "zh-Hans" if normalized.startswith("zh") else "en"


def get_workflow_loader(request: Any = None) -> LanguageLoader:
    user = getattr(request, "user", None)
    return LanguageLoader(
        app="workflow_orchestration",
        default_lang=_normalize_locale(getattr(user, "locale", None)),
    )


def workflow_message(request: Any, key: str, default: str, **values: Any) -> str:
    template = get_workflow_loader(request).get(key, default) or default
    try:
        return str(template).format(**values)
    except (KeyError, ValueError):
        return str(template)


def serializer_message(serializer: Any, key: str, default: str, **values: Any) -> str:
    return workflow_message(serializer.context.get("request"), key, default, **values)
