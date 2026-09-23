"""Issue #4333：补齐 core 缺 key，团队拒绝走语言包，locale 别名能加载对应 yaml。"""

from types import SimpleNamespace

import pytest
from rest_framework.exceptions import PermissionDenied

from apps.core.utils.loader import LanguageLoader
from apps.core.utils.viewset_utils import GenericViewSetFun, team_access_denied_message


KEYS = (
    "error.username_password_empty",
    "error.invalid_current_team",
    "error.no_permission_access_team",
    "error.code_empty",
)


def test_determined_error_keys_exist_in_both_locales():
    en = LanguageLoader(app="core", default_lang="en")
    zh = LanguageLoader(app="core", default_lang="zh-Hans")
    for key in KEYS:
        en_value = en.get(key)
        zh_value = zh.get(key)
        assert en_value, key
        assert zh_value, key
        assert en_value != zh_value


def test_team_access_denied_follows_user_locale():
    request = SimpleNamespace(user=SimpleNamespace(locale="en-US"))
    assert team_access_denied_message(request) == "No permission to access this team"
    request.user.locale = "zh-CN"
    assert team_access_denied_message(request) == "无权访问该团队数据"


def test_filter_by_group_raises_locale_message():
    request = SimpleNamespace(
        COOKIES={},
        user=SimpleNamespace(locale="en", is_superuser=False, group_list=[{"id": 1}]),
    )
    request.COOKIES["current_team"] = "99"
    with pytest.raises(PermissionDenied) as exc:
        GenericViewSetFun.filter_by_group(None, request, request.user)
    assert str(exc.value) == "No permission to access this team"
    assert "无权" not in str(exc.value)
