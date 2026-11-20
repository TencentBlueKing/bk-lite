from typing import Any

from apps.core.utils.loader import LanguageLoader

DEFAULT_EXECUTION_LOCALE = "zh-Hans"


def normalize_execution_locale(locale: str | None) -> str:
    primary = (locale or "").strip().lower().replace("_", "-").partition("-")[0]
    return "en" if primary == "en" else DEFAULT_EXECUTION_LOCALE


def request_execution_locale(request) -> str | None:
    return request.headers.get("X-BK-Locale") or getattr(request.user, "locale", None)


def _normalize_locale(locale: str | None) -> str:
    normalized = (locale or "zh-Hans").lower().replace("_", "-")
    return "zh-Hans" if normalized.startswith("zh") else "en"


def get_workflow_loader(request: Any = None) -> LanguageLoader:
    user = getattr(request, "user", None)
    return LanguageLoader(
        app="workflow",
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
