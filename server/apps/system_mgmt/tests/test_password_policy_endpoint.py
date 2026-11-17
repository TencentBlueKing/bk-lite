"""已登录用户读取改密所需的长度和字符类型，不经过安全设置查看权限。"""

import json
import types

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.system_mgmt.models import SystemSettings
from apps.system_mgmt.viewset.system_settings_viewset import SystemSettingsViewSet

pytestmark = pytest.mark.django_db


def _ordinary_user():
    return types.SimpleNamespace(
        username="change-password-user",
        domain="domain.com",
        locale="zh-Hans",
        is_superuser=False,
        is_authenticated=True,
        permission={"system-manager": set()},
    )


def _get(action_name, path):
    factory = APIRequestFactory()
    request = factory.get(path)
    force_authenticate(request, user=_ordinary_user())
    response = SystemSettingsViewSet.as_view({"get": action_name})(request)
    return response, json.loads(response.content)


def _setting(key, value):
    SystemSettings.objects.update_or_create(key=key, defaults={"value": value})


def test_authenticated_user_reads_only_length_and_character_types():
    _setting("pwd_set_min_length", "10")
    _setting("pwd_set_max_length", "18")
    _setting("pwd_set_required_char_types", "lowercase,digit")
    _setting("pwd_set_lock_duration", "600")
    _setting("enable_otp", "1")

    response, payload = _get("password_policy", "/system_mgmt/system_settings/password_policy/")

    assert response.status_code == 200
    assert payload["result"] is True
    assert payload["data"] == {
        "pwd_set_min_length": "10",
        "pwd_set_max_length": "18",
        "pwd_set_required_char_types": "lowercase,digit",
    }


def test_missing_policy_uses_validator_defaults():
    SystemSettings.objects.filter(key__startswith="pwd_set_").delete()
    response, payload = _get("password_policy", "/system_mgmt/system_settings/password_policy/")

    assert response.status_code == 200
    assert payload["data"] == {
        "pwd_set_min_length": "8",
        "pwd_set_max_length": "20",
        "pwd_set_required_char_types": "uppercase,lowercase,digit,special",
    }


def test_same_user_still_cannot_read_system_settings():
    response, payload = _get("get_sys_set", "/system_mgmt/system_settings/get_sys_set/")

    assert response.status_code == 403
    assert payload["result"] is False
