from apps.core.utils.loader import LanguageLoader
from apps.log.constants.language import LanguageConstants


def log_text(locale, key: str, **values) -> str:
    template = LanguageLoader(app=LanguageConstants.APP, default_lang=locale or "zh-Hans").get(key)
    if not isinstance(template, str) or not template:
        template = key
    return template.format(**values) if values else template


def serializer_text(serializer, key: str, **values) -> str:
    context = getattr(serializer, "context", None) or {}
    request = context.get("request")
    locale = getattr(getattr(request, "user", None), "locale", None)
    return log_text(locale, key, **values)
