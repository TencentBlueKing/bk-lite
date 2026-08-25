"""MLOps 面向 API 用户的文案国际化工具。"""

from typing import Any

from apps.core.utils.loader import LanguageLoader

WEBHOOK_SERVER_URL_NOT_CONFIGURED = "error.webhook_server_url_not_configured"
WEBHOOK_TIMEOUT = "error.webhook_timeout"
WEBHOOK_CONNECTION_FAILED = "error.webhook_connection_failed"
WEBHOOK_REQUEST_FAILED = "error.webhook_request_failed"
REQUEST_FAILED = "error.request_failed"
MLFLOW_TRACKER_URL_NOT_CONFIGURED = "error.mlflow_tracker_url_not_configured"
MODEL_NOT_AVAILABLE = "error.model_not_available"


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


def mlops_exception_message(request: Any, exc: BaseException) -> str:
    """把异常映射为可本地化的 API 文案，不透传 str(e)。"""
    from apps.mlops.utils.webhook_client import WebhookConnectionError, WebhookError, WebhookTimeoutError

    if isinstance(exc, WebhookTimeoutError):
        return mlops_message(request, WEBHOOK_TIMEOUT)
    if isinstance(exc, WebhookConnectionError):
        return mlops_message(request, WEBHOOK_CONNECTION_FAILED)

    text = str(exc)
    if text.startswith("error."):
        return mlops_message(request, text)
    if isinstance(exc, WebhookError):
        return mlops_message(request, WEBHOOK_REQUEST_FAILED)
    return mlops_message(request, REQUEST_FAILED)


def serializer_message(serializer: Any, key: str, default: str = "", **values: Any) -> str:
    """在 DRF Serializer 中复用请求语言。"""
    request = getattr(serializer, "context", {}).get("request")
    return mlops_message(request, key, default, **values)
