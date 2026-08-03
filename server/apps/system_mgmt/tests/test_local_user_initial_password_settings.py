import json
import types

import pytest
from django.contrib.auth.hashers import check_password
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.system_mgmt.models import SystemSettings
from apps.system_mgmt.viewset.system_settings_viewset import SystemSettingsViewSet


def _security_admin(permission):
    return types.SimpleNamespace(
        username="initial-password-admin",
        domain="domain.com",
        locale="zh-Hans",
        is_superuser=True,
        is_authenticated=True,
        permission={"system-manager": {permission}},
    )


def _update(data):
    factory = APIRequestFactory()
    request = factory.post("/system_mgmt/system_settings/update_sys_set/", data, format="json")
    force_authenticate(request, user=_security_admin("security_settings-Edit"))
    response = SystemSettingsViewSet.as_view({"post": "update_sys_set"})(request)
    return response, json.loads(response.content)


def _get():
    factory = APIRequestFactory()
    request = factory.get("/system_mgmt/system_settings/get_sys_set/")
    force_authenticate(request, user=_security_admin("security_settings-View"))
    response = SystemSettingsViewSet.as_view({"get": "get_sys_set"})(request)
    return response, json.loads(response.content)


def _enable_initial_password():
    response, payload = _update(
        {
            "user_create_initial_password_enabled": "1",
            "user_create_initial_password": "InitialPwd1!",
            "pwd_set_min_length": "8",
            "pwd_set_max_length": "20",
            "pwd_set_required_char_types": "uppercase,lowercase,digit,special",
        }
    )
    assert response.status_code == 200, payload


@pytest.mark.django_db
def test_enable_initial_password_stores_only_hash_and_get_masks_it():
    _enable_initial_password()

    password_hash = SystemSettings.objects.get(key="user_create_initial_password_hash").value
    assert password_hash != "InitialPwd1!"
    assert check_password("InitialPwd1!", password_hash)

    response, payload = _get()

    assert response.status_code == 200
    assert payload["data"]["user_create_initial_password_enabled"] == "1"
    assert payload["data"]["user_create_initial_password_configured"] == "1"
    assert "user_create_initial_password_hash" not in payload["data"]
    assert "InitialPwd1!" not in json.dumps(payload)


@pytest.mark.django_db
def test_disabling_initial_password_clears_the_hash():
    _enable_initial_password()

    response, payload = _update({"user_create_initial_password_enabled": "0"})

    assert response.status_code == 200, payload
    assert SystemSettings.objects.get(key="user_create_initial_password_hash").value == ""


@pytest.mark.django_db
def test_policy_change_requires_replacing_enabled_initial_password():
    _enable_initial_password()

    response, payload = _update({"pwd_set_min_length": "12"})

    assert response.status_code == 400
    assert payload["result"] is False
    assert "初始密码" in payload["message"]
    assert SystemSettings.objects.get(key="pwd_set_min_length").value == "8"


@pytest.mark.django_db
def test_policy_change_with_compliant_initial_password_saves_atomically():
    _enable_initial_password()

    response, payload = _update(
        {
            "pwd_set_min_length": "12",
            "user_create_initial_password_enabled": "1",
            "user_create_initial_password": "LongInitial1!",
        }
    )

    assert response.status_code == 200, payload
    assert SystemSettings.objects.get(key="pwd_set_min_length").value == "12"
    password_hash = SystemSettings.objects.get(key="user_create_initial_password_hash").value
    assert check_password("LongInitial1!", password_hash)
