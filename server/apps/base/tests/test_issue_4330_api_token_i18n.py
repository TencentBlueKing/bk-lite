"""Issue #4330：拒绝全量修改个人 API 令牌时按 locale 返回语言包文案。

审计动词「创建/更新/删除」、默认名「未命名」和「个人令牌:」写操作日志，不进 API 响应，保留原文。
"""

import json
import types

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.base.user_api_secret_mgmt.views import UserAPISecretViewSet
from apps.core.utils.loader import LanguageLoader

factory = APIRequestFactory()


def _user(locale):
    return types.SimpleNamespace(
        username="issue-4330",
        domain="domain.com",
        locale=locale,
        is_authenticated=True,
        is_superuser=False,
        permission={"system-manager": {"api_secret_key-Add"}},
    )


def _put(locale):
    request = factory.put("/base/user_api_secret/1/", {"name": "x"}, format="json")
    force_authenticate(request, user=_user(locale))
    return UserAPISecretViewSet.as_view({"put": "update"})(request, pk=1)


@pytest.mark.django_db
@pytest.mark.parametrize("locale", ["en", "zh-Hans"])
def test_put_rejects_full_update_with_locale_message(locale):
    expected = LanguageLoader(app="core", default_lang=locale).get("error.api_token_update_not_supported")
    assert expected
    response = _put(locale)
    body = json.loads(response.content)
    assert body["result"] is False
    assert body["message"] == expected


@pytest.mark.django_db
def test_english_put_does_not_leak_chinese_message():
    body = json.loads(_put("en").content)
    assert body["message"] == "API tokens cannot be fully replaced"
    assert "令牌" not in body["message"]
