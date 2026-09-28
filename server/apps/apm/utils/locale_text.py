from apps.core.utils.loader import LanguageLoader

APP = "apm"
FALLBACK_LOCALE = "zh-Hans"


def apm_text(locale, key: str, **values) -> str:
    template = LanguageLoader(app=APP, default_lang=locale or FALLBACK_LOCALE).get(key)
    if not isinstance(template, str) or not template:
        # 未收录的语言没有语言包；退回中文，不把 key 交给用户。
        template = LanguageLoader(app=APP, default_lang=FALLBACK_LOCALE).get(key)
    if not isinstance(template, str) or not template:
        template = key
    return template.format(**values) if values else template


def _request_locale(request) -> str | None:
    return getattr(getattr(request, "user", None), "locale", None)


def serializer_text(serializer, key: str, **values) -> str:
    context = getattr(serializer, "context", None) or {}
    return apm_text(_request_locale(context.get("request")), key, **values)


def request_text(request, key: str, **values) -> str:
    return apm_text(_request_locale(request), key, **values)


def public_detail(exc, request) -> str:
    key = getattr(exc, "message_key", None)
    if not key:
        return str(getattr(exc, "detail", exc))
    return apm_text(_request_locale(request), key, **(getattr(exc, "message_values", None) or {}))
