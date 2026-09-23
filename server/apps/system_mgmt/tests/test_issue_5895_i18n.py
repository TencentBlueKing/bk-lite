"""Issue #5895：OpenAPI 文档 ICU 标签转义，以及 system_mgmt 确定硬编码接入语言包。"""

import json
import types
from pathlib import Path

import pytest
from django.core.exceptions import ValidationError
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.core.utils.loader import LanguageLoader
from apps.system_mgmt.models import CustomMenuGroup, SystemAPIToken
from apps.system_mgmt.viewset import integration_instance_viewset
from apps.system_mgmt.viewset.system_api_token_viewset import SystemAPITokenViewSet

REPO = Path(__file__).resolve().parents[4]
factory = APIRequestFactory()


@pytest.mark.parametrize("name", ["en.json", "zh.json"])
def test_openapi_auth_header_desc_quotes_icu_tags(name):
    data = json.loads((REPO / "web/src/app/system-manager/locales" / name).read_text(encoding="utf-8"))
    desc = data["system"]["settings"]["openapiDocs"]["authHeaderDesc"]
    assert "'<'API_TOKEN'>'" in desc
    assert "<API_TOKEN>" not in desc


def test_determined_error_keys_exist_in_both_locales():
    keys = (
        "error.im_channel_in_use",
        "error.integration_instance_in_use",
        "error.system_token_full_update_not_supported",
        "export.openapi_call_log_sheet",
        "export.openapi_call_log_filename",
    )
    en = LanguageLoader(app="system_mgmt", default_lang="en")
    zh = LanguageLoader(app="system_mgmt", default_lang="zh-Hans")
    for key in keys:
        en_value = en.get(key)
        zh_value = zh.get(key)
        assert en_value, key
        assert zh_value, key
        assert en_value != zh_value


def test_integration_in_use_message_follows_locale():
    en = json.loads(integration_instance_viewset.build_instance_in_use_response([], "en").content)
    zh = json.loads(integration_instance_viewset.build_instance_in_use_response([], "zh-Hans").content)
    assert en["code"] == integration_instance_viewset.INTEGRATION_INSTANCE_IN_USE_CODE
    assert "still referenced" in en["message"]
    assert "仍被其他配置引用" in zh["message"]


def _token_user(locale):
    return types.SimpleNamespace(
        username="issue-5895",
        domain="domain.com",
        locale=locale,
        is_authenticated=True,
        is_superuser=False,
        permission={"system-manager": {"system_api_secret-Edit"}},
    )


@pytest.mark.django_db
@pytest.mark.parametrize("locale", ["en", "zh-Hans"])
def test_system_token_put_uses_language_pack(locale):
    token = SystemAPIToken.objects.create(
        system_id="itsm",
        name="issue-5895",
        secret_hash=SystemAPIToken.hash_secret(SystemAPIToken.generate_secret()),
        scope={"mode": "all"},
        created_by="issue-5895",
    )
    request = factory.put(f"/system_mgmt/system_api_token/{token.pk}/", {"name": "x"}, format="json")
    force_authenticate(request, user=_token_user(locale))
    response = SystemAPITokenViewSet.as_view({"put": "update"})(request, pk=token.pk)
    body = json.loads(response.content)
    expected = LanguageLoader(app="system_mgmt", default_lang=locale).get("error.system_token_full_update_not_supported")
    assert body["result"] is False
    assert body["message"] == expected
    token.refresh_from_db()
    assert token.name == "issue-5895"


@pytest.mark.django_db
def test_custom_menu_group_clean_uses_language_pack():
    CustomMenuGroup.objects.create(app="monitor", display_name="a", is_enabled=True, created_by="issue-5895")
    other = CustomMenuGroup(app="monitor", display_name="b", is_enabled=True, created_by="issue-5895")
    with pytest.raises(ValidationError) as exc:
        other.clean()
    message = " ".join(str(item) for item in exc.value.messages)
    assert "already has an enabled menu group" in message
    assert "已有启用的菜单组" not in message
