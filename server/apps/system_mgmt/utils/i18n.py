"""system_mgmt 面向用户的文案。"""

from typing import Any

from apps.core.utils.loader import LanguageLoader


def resolve_system_mgmt_language(locale: Any = None) -> str:
    raw = str(locale or "zh-Hans").strip() or "zh-Hans"
    return "zh-Hans" if raw.lower().startswith("zh") else "en"


def system_mgmt_message(locale: Any, key: str, **values: Any) -> str:
    language = resolve_system_mgmt_language(locale)
    template = LanguageLoader(app="system_mgmt", default_lang=language).get(key) or key
    try:
        return str(template).format(**values)
    except (KeyError, ValueError):
        return str(template)


def system_mgmt_request_message(request: Any, key: str, **values: Any) -> str:
    user = getattr(request, "user", None)
    locale = getattr(user, "locale", None) or "zh-Hans"
    return system_mgmt_message(locale, key, **values)


OPSPILOT_NATS_DESCRIPTION_MARKER = "opspilot_nats_trigger"
_LEGACY_OPSPILOT_NATS_DESCRIPTIONS = {
    OPSPILOT_NATS_DESCRIPTION_MARKER,
    "OpsPilot 工作流自动创建的 NATS 触发通道",
}


def localized_channel_description(description: Any, locale: Any = None) -> str:
    """把 OpsPilot 自动通道的语言无关标记译成当前语言；其它描述原样返回。"""
    text = "" if description is None else str(description)
    if text not in _LEGACY_OPSPILOT_NATS_DESCRIPTIONS:
        return text
    return system_mgmt_message(locale, "channel.opspilot_nats_trigger_description")
