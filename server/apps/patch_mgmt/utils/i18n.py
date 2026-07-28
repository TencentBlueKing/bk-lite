"""补丁管理用户可见文案的国际化工具。"""

from typing import Any

from apps.core.utils.loader import LanguageLoader
from apps.patch_mgmt.exceptions import PatchBusinessError


def get_patch_loader(request: Any = None) -> LanguageLoader:
    """按当前用户语言创建加载器；无请求上下文时使用英文兜底。"""
    user = getattr(request, "user", None)
    locale = getattr(user, "locale", None) or "en"
    return LanguageLoader(app="patch_mgmt", default_lang=locale)


def patch_message(
    request: Any,
    key: str,
    default: str,
    **values: Any,
) -> str:
    """获取并格式化用户可见文案。"""
    template = get_patch_loader(request).get(key, default) or default
    try:
        return str(template).format(**values)
    except (KeyError, ValueError):
        return str(template)


def serializer_message(
    serializer: Any,
    key: str,
    default: str,
    **values: Any,
) -> str:
    """在 DRF Serializer 中复用请求语言。"""
    request = getattr(serializer, "context", {}).get("request")
    return patch_message(request, key, default, **values)


def render_business_error(request: Any, error: PatchBusinessError) -> str:
    """在 API 边界翻译业务错误，并保留底层原始诊断。"""
    message = patch_message(
        request,
        f"error.{error.code}",
        error.default_message,
        **error.params,
    )
    return f"{message}: {error.raw_detail}" if error.raw_detail else message
