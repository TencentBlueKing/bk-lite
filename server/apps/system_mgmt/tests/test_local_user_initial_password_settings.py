import json
import types

import pytest
from django.contrib.auth.hashers import check_password
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.system_mgmt.models import Channel, ChannelChoices, SystemSettings
from apps.system_mgmt.utils.password_vault import decrypt_from_vault
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
    channel = Channel.objects.create(
        name="initial-password-email",
        channel_type=ChannelChoices.EMAIL,
        config={},
        description="email",
    )
    response, payload = _update(
        {
            "user_create_initial_password_mode": "fixed",
            "user_create_initial_password": "InitialPwd1!",
            "user_create_initial_password_random_email_channel_id": str(channel.id),
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
    encrypted_password = SystemSettings.objects.get(key="user_create_initial_password_encrypted").value
    assert password_hash != "InitialPwd1!"
    assert check_password("InitialPwd1!", password_hash)
    assert encrypted_password != "InitialPwd1!"
    assert decrypt_from_vault(encrypted_password) == "InitialPwd1!"

    response, payload = _get()

    assert response.status_code == 200
    assert payload["data"]["user_create_initial_password_configured"] == "1"
    assert "user_create_initial_password_hash" not in payload["data"]
    assert "user_create_initial_password_encrypted" not in payload["data"]
    assert "InitialPwd1!" not in json.dumps(payload)


@pytest.mark.django_db
def test_switching_to_none_clears_the_hash():
    _enable_initial_password()

    response, payload = _update({"user_create_initial_password_mode": "none"})

    assert response.status_code == 200, payload
    assert SystemSettings.objects.get(key="user_create_initial_password_hash").value == ""
    assert SystemSettings.objects.get(key="user_create_initial_password_encrypted").value == ""


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
            "user_create_initial_password": "LongInitial1!",
        }
    )

    assert response.status_code == 200, payload
    assert SystemSettings.objects.get(key="pwd_set_min_length").value == "12"
    password_hash = SystemSettings.objects.get(key="user_create_initial_password_hash").value
    encrypted_password = SystemSettings.objects.get(key="user_create_initial_password_encrypted").value
    assert check_password("LongInitial1!", password_hash)
    assert decrypt_from_vault(encrypted_password) == "LongInitial1!"


@pytest.mark.django_db
def test_get_sys_set_exposes_mode_default_none():
    """get_sys_set 默认不启用初始密码。"""
    response, payload = _get()
    assert response.status_code == 200
    assert payload["data"]["user_create_initial_password_mode"] == "none"


@pytest.mark.django_db
def test_update_sys_set_rejects_invalid_mode():
    """非法 mode 必须返回 400,不得持久化。"""
    response, payload = _update({"user_create_initial_password_mode": "biometric"})
    assert response.status_code == 400
    assert "模式" in payload["message"]
    assert not SystemSettings.objects.filter(key="user_create_initial_password_mode").exists()


@pytest.mark.django_db
def test_update_sys_set_random_mode_requires_email_channel():
    """mode=random 但未传 email_channel_id 必须返回 400。"""
    response, payload = _update({"user_create_initial_password_mode": "random"})
    assert response.status_code == 400
    assert "邮件通道" in payload["message"]


@pytest.mark.django_db
def test_update_sys_set_fixed_mode_requires_email_channel():
    """统一初始密码模式必须配置邮件通道。"""
    response, payload = _update(
        {
            "user_create_initial_password_mode": "fixed",
            "user_create_initial_password": "InitialPwd1!",
        }
    )

    assert response.status_code == 400
    assert "邮件通道" in payload["message"]


@pytest.mark.django_db
def test_update_sys_set_random_mode_rejects_nonexistent_channel():
    """mode=random 配不存在的 channel id 必须返回 400。"""
    response, payload = _update(
        {
            "user_create_initial_password_mode": "random",
            "user_create_initial_password_random_email_channel_id": "9999",
        }
    )
    assert response.status_code == 400
    assert "不存在" in payload["message"]


@pytest.mark.django_db
def test_update_sys_set_random_mode_rejects_non_email_channel():
    """mode=random 配非 email 通道必须返回 400。"""
    channel = Channel.objects.create(
        name="wecom",
        channel_type=ChannelChoices.ENTERPRISE_WECHAT,
        config={},
        description="wecom",
    )
    response, payload = _update(
        {
            "user_create_initial_password_mode": "random",
            "user_create_initial_password_random_email_channel_id": str(channel.id),
        }
    )
    assert response.status_code == 400
    assert "email" in payload["message"]


@pytest.mark.django_db
def test_update_sys_set_random_mode_persists_and_clears_legacy_hash():
    """mode=random 持久化 email_channel_id,同时清空历史 enabled/hash,避免旧 hash 被误读。"""
    _enable_initial_password()

    channel = Channel.objects.create(
        name="test-email",
        channel_type=ChannelChoices.EMAIL,
        config={},
        description="email",
    )
    response, payload = _update(
        {
            "user_create_initial_password_mode": "random",
            "user_create_initial_password_random_email_channel_id": str(channel.id),
        }
    )

    assert response.status_code == 200, payload
    assert SystemSettings.objects.get(key="user_create_initial_password_mode").value == "random"
    assert SystemSettings.objects.get(key="user_create_initial_password_random_email_channel_id").value == str(channel.id)
    assert SystemSettings.objects.get(key="user_create_initial_password_hash").value == ""


@pytest.mark.django_db
def test_update_sys_set_none_mode_persists_and_clears_legacy_hash():
    """mode=none 持久化,且清空 enabled/hash。"""
    _enable_initial_password()

    response, payload = _update({"user_create_initial_password_mode": "none"})

    assert response.status_code == 200, payload
    assert SystemSettings.objects.get(key="user_create_initial_password_mode").value == "none"
    assert SystemSettings.objects.get(key="user_create_initial_password_hash").value == ""
