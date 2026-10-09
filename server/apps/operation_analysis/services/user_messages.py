"""当前请求语言下的运营分析用户文案。

缺词条时回退调用方给出的中文原文，保证未切换语言时的响应不变。
"""

from __future__ import annotations

from contextlib import contextmanager

from django.utils import translation

from apps.core.utils.loader import LanguageLoader
from apps.operation_analysis.services.builtin_i18n import normalize_oa_language


def oa_message(message_key: str, default: str, /, **params: object) -> str:
    language = normalize_oa_language(translation.get_language())
    catalog = LanguageLoader("operation_analysis", language).translations or {}
    node: object = catalog
    for part in message_key.split("."):
        if not isinstance(node, dict) or part not in node:
            node = None
            break
        node = node[part]
    template = node if isinstance(node, str) and node else default
    if not params:
        return template
    return template.format(**params)


def _account_locale(username: str, domain: str) -> str:
    """界面与 token 用的是 system_mgmt 账号 locale。

    ``base.User.locale`` 只在建号时写入，登录不会回写。个人设置
    ``update_user_base_info`` 改的是 system_mgmt 用户，并写进 token。
    """
    from apps.base.models import User as AuthUser
    from apps.system_mgmt.models import User as AccountUser

    account = AccountUser.objects.filter(username=username, domain=domain).only("locale").first()
    locale = (getattr(account, "locale", None) or "").strip()
    if locale:
        return locale
    auth_user = AuthUser.objects.filter(username=username, domain=domain).only("locale").first()
    return (getattr(auth_user, "locale", None) or "").strip()


@contextmanager
def override_for_creator(username: str | None, domain: str | None):
    """邮件等无请求上下文时，沿用创建者当前界面语言。"""
    locale = _account_locale(username, domain or "") if username else ""
    language = locale or translation.get_language() or "zh-Hans"
    with translation.override(language):
        yield
