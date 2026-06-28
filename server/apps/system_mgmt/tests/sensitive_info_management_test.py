import importlib
import json
import os
import types
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.contrib.auth.hashers import make_password
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.system_mgmt.models import (
    Channel,
    Group,
    IntegrationInstance,
    IntegrationInstanceStatusChoices,
    OperationLog,
    SensitiveInfoAuthorization,
    SystemSettings,
    User,
    UserRule,
    UserSyncSource,
)
from apps.system_mgmt.models.channel import ChannelChoices
from apps.system_mgmt.nats_api import get_all_users, login
from apps.system_mgmt.serializers.user_serializer import UserSerializer
from apps.system_mgmt.tasks import check_password_expiry_and_notify


def _build_authenticated_request_user(**overrides):
    defaults = {
        "username": "system-settings-admin",
        "domain": "domain.com",
        "locale": "en",
        "is_superuser": True,
        "is_authenticated": True,
        "permission": {"system-manager": {"user_group-View"}},
    }
    defaults.update(overrides)
    return types.SimpleNamespace(**defaults)


def _set_sensitive_info_settings(enabled: bool, sensitive_types: str = "email,phone"):
    SystemSettings.objects.update_or_create(
        key="sensitive_info_protection_enabled",
        defaults={"value": "1" if enabled else "0"},
    )
    SystemSettings.objects.update_or_create(
        key="sensitive_info_types",
        defaults={"value": sensitive_types},
    )


def test_system_mgmt_urls_loads_enterprise_urlpatterns_indirectly_without_hardcoded_route_name(monkeypatch):
    import apps.system_mgmt.urls as system_mgmt_urls

    original_import = __import__
    imported_modules = []

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        imported_modules.append(name)
        if name == "apps.system_mgmt.enterprise.urls":
            return types.SimpleNamespace(urlpatterns=[])
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr("builtins.__import__", fake_import)

    reloaded_urls = importlib.reload(system_mgmt_urls)

    assert "apps.system_mgmt.enterprise.urls" in imported_modules
    assert "SensitiveInfoAuthorizationViewSet" not in reloaded_urls.__dict__
    assert "enterprise_urls" in reloaded_urls.__dict__



@pytest.mark.django_db
# 验证系统设置接口会补齐并返回敏感信息保护的默认配置项。
def test_system_settings_get_sys_set_includes_sensitive_info_defaults():
    from apps.system_mgmt.viewset.system_settings_viewset import SystemSettingsViewSet

    factory = APIRequestFactory()
    view = SystemSettingsViewSet.as_view({"get": "get_sys_set"})
    request = factory.get("/system_mgmt/api/system_settings/get_sys_set/")
    force_authenticate(
        request,
        user=_build_authenticated_request_user(permission={"system-manager": {"security_settings-View"}}),
    )

    response = view(request)
    payload = json.loads(response.content)

    assert response.status_code == 200
    assert payload["result"] is True
    assert payload["data"]["sensitive_info_protection_enabled"] == "0"
    assert payload["data"]["sensitive_info_types"] == "email,phone"


@pytest.mark.django_db
# 验证创建用户时手机号宽松校验：合法格式可保存，非法格式会被拒绝。
def test_user_viewset_create_user_accepts_valid_phone_and_rejects_invalid_phone():
    from apps.system_mgmt.models import Group, Role
    from apps.system_mgmt.viewset.user_viewset import UserViewSet

    role = Role.objects.create(name="operator", app="")
    group = Group.objects.create(name="group-for-phone-validation")

    factory = APIRequestFactory()
    view = UserViewSet.as_view({"post": "create_user"})

    valid_request = factory.post(
        "/system_mgmt/api/user/create_user/",
        {
            "username": "valid-phone-user",
            "lastName": "合法手机号用户",
            "email": "valid-phone@example.com",
            "phone": "+86 13800000000",
            "locale": "zh-Hans",
            "timezone": "Asia/Shanghai",
            "groups": [group.id],
            "roles": [role.id],
            "rules": [],
        },
        format="json",
    )
    force_authenticate(
        valid_request,
        user=_build_authenticated_request_user(
            username="creator-admin",
            permission={"system-manager": {"user_group-Add User"}},
        ),
    )

    valid_response = view(valid_request)
    valid_payload = json.loads(valid_response.content)

    assert valid_response.status_code == 200
    assert valid_payload == {"result": True}
    assert User.objects.get(username="valid-phone-user").phone == "+86 13800000000"

    invalid_request = factory.post(
        "/system_mgmt/api/user/create_user/",
        {
            "username": "invalid-phone-user",
            "lastName": "非法手机号用户",
            "email": "invalid-phone@example.com",
            "phone": "123****8222",
            "locale": "zh-Hans",
            "timezone": "Asia/Shanghai",
            "groups": [group.id],
            "roles": [role.id],
            "rules": [],
        },
        format="json",
    )
    force_authenticate(
        invalid_request,
        user=_build_authenticated_request_user(
            username="creator-admin",
            permission={"system-manager": {"user_group-Add User"}},
        ),
    )

    invalid_response = view(invalid_request)
    invalid_payload = json.loads(invalid_response.content)

    assert invalid_response.status_code == 200
    assert invalid_payload == {"result": False, "message": "手机号格式不正确"}
    assert not User.objects.filter(username="invalid-phone-user").exists()


@pytest.mark.django_db
# 验证编辑用户时非法手机号不会覆盖已有手机号值。
def test_user_viewset_update_user_rejects_invalid_phone():
    from apps.system_mgmt.models import Group, Role
    from apps.system_mgmt.viewset.user_viewset import UserViewSet

    Role.objects.create(name="admin", app="")
    role = Role.objects.create(name="editor", app="")
    group = Group.objects.create(name="group-for-phone-update")
    user = User.objects.create(
        username="update-phone-user",
        display_name="更新手机号用户",
        email="update-phone@example.com",
        phone="13800000000",
        password=make_password("password123"),
        locale="zh-Hans",
        timezone="Asia/Shanghai",
        group_list=[group.id],
        role_list=[role.id],
    )

    factory = APIRequestFactory()
    view = UserViewSet.as_view({"post": "update_user"})
    request = factory.post(
        "/system_mgmt/api/user/update_user/",
        {
            "user_id": user.id,
            "username": user.username,
            "lastName": "更新手机号用户",
            "email": user.email,
            "phone": "123****8222",
            "locale": user.locale,
            "timezone": user.timezone,
            "groups": [group.id],
            "roles": [role.id],
            "rules": [],
            "is_superuser": False,
        },
        format="json",
    )
    force_authenticate(
        request,
        user=_build_authenticated_request_user(
            username="editor-admin",
            permission={"system-manager": {"user_group-Edit User"}},
        ),
    )

    response = view(request)
    payload = json.loads(response.content)
    user.refresh_from_db()

    assert response.status_code == 200
    assert payload == {"result": False, "message": "手机号格式不正确"}
    assert user.phone == "13800000000"


@pytest.mark.django_db
# 验证编辑用户时若 payload 省略敏感字段，后端会保留原有邮箱和手机号。
def test_user_viewset_update_user_keeps_existing_sensitive_fields_when_omitted():
    from apps.system_mgmt.models import Group, Role
    from apps.system_mgmt.viewset.user_viewset import UserViewSet

    Role.objects.create(name="admin", app="")
    role = Role.objects.create(name="editor-preserve-sensitive", app="")
    group = Group.objects.create(name="group-for-sensitive-preserve")
    user = User.objects.create(
        username="preserve-sensitive-user",
        display_name="原始姓名",
        email="preserve-sensitive@example.com",
        phone="13800009999",
        password=make_password("password123"),
        locale="zh-Hans",
        timezone="Asia/Shanghai",
        group_list=[group.id],
        role_list=[role.id],
    )

    factory = APIRequestFactory()
    view = UserViewSet.as_view({"post": "update_user"})
    request = factory.post(
        "/system_mgmt/api/user/update_user/",
        {
            "user_id": user.id,
            "username": user.username,
            "lastName": "只改姓名",
            "locale": user.locale,
            "timezone": user.timezone,
            "groups": [group.id],
            "roles": [role.id],
            "rules": [],
            "is_superuser": False,
        },
        format="json",
    )
    force_authenticate(
        request,
        user=_build_authenticated_request_user(
            username="editor-admin",
            permission={"system-manager": {"user_group-Edit User"}},
        ),
    )

    response = view(request)
    payload = json.loads(response.content)
    user.refresh_from_db()

    assert response.status_code == 200
    assert payload == {"result": True}
    assert user.display_name == "只改姓名"
    assert user.email == "preserve-sensitive@example.com"
    assert user.phone == "13800009999"


@pytest.mark.django_db
def test_user_viewset_delete_user_allows_manual_user():
    from apps.system_mgmt.viewset.user_viewset import UserViewSet

    group = Group.objects.create(name="group-for-delete-manual")
    user = User.objects.create(
        username="manual-delete-user",
        display_name="手工用户",
        email="manual-delete@example.com",
        password=make_password("password123"),
        group_list=[group.id],
    )
    UserRule.objects.create(username=user.username, domain=user.domain, group_rule_id=1)

    factory = APIRequestFactory()
    view = UserViewSet.as_view({"post": "delete_user"})
    request = factory.post(
        "/system_mgmt/api/user/delete_user/",
        {"user_ids": [user.id]},
        format="json",
    )
    force_authenticate(
        request,
        user=_build_authenticated_request_user(
            username="delete-admin",
            permission={"system-manager": {"user_group-Delete User"}},
            group_list=[{"id": group.id, "name": group.name}],
            is_superuser=False,
        ),
    )

    response = view(request)
    payload = json.loads(response.content)

    assert response.status_code == 200
    assert payload == {"result": True}
    assert User.objects.filter(id=user.id).exists() is False


@pytest.mark.django_db
def test_user_viewset_delete_user_rejects_synced_user():
    from apps.system_mgmt.viewset.user_viewset import UserViewSet

    group = Group.objects.create(name="group-for-delete-synced")
    instance = IntegrationInstance.objects.create(
        name="feishu-sync",
        provider_key="feishu",
        enabled=True,
        status=IntegrationInstanceStatusChoices.READY,
        capability_status={"user_sync": IntegrationInstanceStatusChoices.READY},
        capability_enabled={"user_sync": True},
        config={},
    )
    source = UserSyncSource.objects.create(
        name="sync-source-a",
        integration_instance=instance,
        enabled=True,
        root_group_name="Root A",
        business_config={},
        field_mapping={},
        schedule_config={},
    )
    user = User.objects.create(
        username="synced-delete-user",
        display_name="同步用户",
        email="synced-delete@example.com",
        password=make_password("password123"),
        group_list=[group.id],
        sync_source=source,
    )

    factory = APIRequestFactory()
    view = UserViewSet.as_view({"post": "delete_user"})
    request = factory.post(
        "/system_mgmt/api/user/delete_user/",
        {"user_ids": [user.id]},
        format="json",
    )
    force_authenticate(
        request,
        user=_build_authenticated_request_user(
            username="delete-admin",
            permission={"system-manager": {"user_group-Delete User"}},
            group_list=[{"id": group.id, "name": group.name}],
            is_superuser=False,
        ),
    )

    response = view(request)
    payload = json.loads(response.content)

    assert response.status_code == 200
    assert payload == {
        "result": False,
        "message": "Synced users cannot be deleted directly. Please delete them from the user sync source.",
    }
    assert User.objects.filter(id=user.id).exists() is True


@pytest.mark.django_db
def test_user_viewset_delete_user_rejects_mixed_batch_when_any_user_is_synced():
    from apps.system_mgmt.viewset.user_viewset import UserViewSet

    group = Group.objects.create(name="group-for-delete-mixed")
    instance = IntegrationInstance.objects.create(
        name="feishu-sync-mixed",
        provider_key="feishu",
        enabled=True,
        status=IntegrationInstanceStatusChoices.READY,
        capability_status={"user_sync": IntegrationInstanceStatusChoices.READY},
        capability_enabled={"user_sync": True},
        config={},
    )
    source = UserSyncSource.objects.create(
        name="sync-source-b",
        integration_instance=instance,
        enabled=True,
        root_group_name="Root B",
        business_config={},
        field_mapping={},
        schedule_config={},
    )
    manual_user = User.objects.create(
        username="manual-batch-user",
        display_name="手工用户",
        email="manual-batch@example.com",
        password=make_password("password123"),
        group_list=[group.id],
    )
    synced_user = User.objects.create(
        username="synced-batch-user",
        display_name="同步用户",
        email="synced-batch@example.com",
        password=make_password("password123"),
        group_list=[group.id],
        sync_source=source,
    )

    factory = APIRequestFactory()
    view = UserViewSet.as_view({"post": "delete_user"})
    request = factory.post(
        "/system_mgmt/api/user/delete_user/",
        {"user_ids": [manual_user.id, synced_user.id]},
        format="json",
    )
    force_authenticate(
        request,
        user=_build_authenticated_request_user(
            username="delete-admin",
            permission={"system-manager": {"user_group-Delete User"}},
            group_list=[{"id": group.id, "name": group.name}],
            is_superuser=False,
        ),
    )

    response = view(request)
    payload = json.loads(response.content)

    assert response.status_code == 200
    assert payload == {
        "result": False,
        "message": "Synced users cannot be deleted directly. Please delete them from the user sync source.",
    }
    assert User.objects.filter(id=manual_user.id).exists() is True
    assert User.objects.filter(id=synced_user.id).exists() is True


@pytest.mark.django_db
# 验证保护开启且无明文查看授权时，显式提交的新敏感字段值仍允许更新保存。
def test_user_viewset_update_user_allows_sensitive_change_when_protection_enabled_without_view_authorization():
    from apps.system_mgmt.models import Group, Role
    from apps.system_mgmt.viewset.user_viewset import UserViewSet

    _set_sensitive_info_settings(enabled=True)
    Role.objects.create(name="admin", app="")
    role = Role.objects.create(name="editor-protection-enabled", app="")
    group = Group.objects.create(name="group-for-protection-enabled")
    user = User.objects.create(
        username="protection-enabled-user",
        display_name="开启保护用户",
        email="enabled-before@example.com",
        phone="13800007777",
        password=make_password("password123"),
        locale="zh-Hans",
        timezone="Asia/Shanghai",
        group_list=[group.id],
        role_list=[role.id],
    )

    factory = APIRequestFactory()
    view = UserViewSet.as_view({"post": "update_user"})
    request = factory.post(
        "/system_mgmt/api/user/update_user/",
        {
            "user_id": user.id,
            "username": user.username,
            "lastName": "开启保护用户",
            "email": "enabled-after@example.com",
            "phone": "13800008888",
            "locale": user.locale,
            "timezone": user.timezone,
            "groups": [group.id],
            "roles": [role.id],
            "rules": [],
            "is_superuser": False,
        },
        format="json",
    )
    force_authenticate(
        request,
        user=_build_authenticated_request_user(
            username="unauthorized-editor",
            is_superuser=False,
            group_list=[{"id": group.id, "name": group.name}],
            permission={"system-manager": {"user_group-Edit User"}},
        ),
    )

    response = view(request)
    payload = json.loads(response.content)
    user.refresh_from_db()

    assert response.status_code == 200
    assert payload == {"result": True}
    assert user.email == "enabled-after@example.com"
    assert user.phone == "13800008888"


@pytest.mark.django_db
# 验证保护关闭时，用户列表查询保持邮箱和手机号明文返回。
def test_user_viewset_search_user_list_keeps_plaintext_when_sensitive_info_protection_disabled():
    from apps.system_mgmt.viewset.user_viewset import UserViewSet

    _set_sensitive_info_settings(enabled=False)
    target_user = User.objects.create(
        username="plain_user",
        display_name="明文用户",
        email="plain@example.com",
        phone="13800001111",
        password=make_password("password123"),
        locale="zh-Hans",
    )

    factory = APIRequestFactory()
    view = UserViewSet.as_view({"get": "search_user_list"})
    request = factory.get("/system_mgmt/api/user/search_user_list/", {"search": target_user.username})
    force_authenticate(
        request,
        user=_build_authenticated_request_user(
            username="viewer-plain",
            is_superuser=False,
            permission={"system-manager": {"user_group-View"}},
        ),
    )

    response = view(request)
    payload = json.loads(response.content)

    assert response.status_code == 200
    returned_user = payload["data"]["users"][0]
    assert returned_user["email"] == "plain@example.com"
    assert returned_user["phone"] == "13800001111"


@pytest.mark.django_db
# 验证保护开启时，未获授权的超级管理员在用户列表中仍只能看到脱敏后的敏感字段。
def test_user_viewset_search_user_list_masks_sensitive_fields_for_unauthorized_superuser_when_enabled():
    from apps.system_mgmt.viewset.user_viewset import UserViewSet

    _set_sensitive_info_settings(enabled=True)
    target_user = User.objects.create(
        username="masked_user",
        display_name="脱敏用户",
        email="masked@example.com",
        phone="13800002222",
        password=make_password("password123"),
        locale="zh-Hans",
    )

    factory = APIRequestFactory()
    view = UserViewSet.as_view({"get": "search_user_list"})
    request = factory.get("/system_mgmt/api/user/search_user_list/", {"search": target_user.username})
    force_authenticate(request, user=_build_authenticated_request_user(username="super-viewer", is_superuser=True))

    response = view(request)
    payload = json.loads(response.content)

    assert response.status_code == 200
    returned_user = payload["data"]["users"][0]
    assert returned_user["email"] == "ma***@example.com"
    assert returned_user["phone"] == "138****2222"


@pytest.mark.django_db
# 验证用户列表查询会返回用户所属同步源标识，供前端删除控制使用。
def test_user_viewset_search_user_list_includes_sync_source_identifier():
    from apps.system_mgmt.viewset.user_viewset import UserViewSet

    _set_sensitive_info_settings(enabled=False)
    instance = IntegrationInstance.objects.create(
        name="sync-source-instance",
        provider_key="feishu",
        status=IntegrationInstanceStatusChoices.READY,
        capability_status={"user_sync": IntegrationInstanceStatusChoices.READY},
        config={"host": "ldap.example.com"},
    )
    source = UserSyncSource.objects.create(
        name="sync-source-a",
        integration_instance=instance,
        root_group_name="Root A",
        field_mapping={"username": "uid"},
        business_config={},
        schedule_config={},
    )
    synced_user = User.objects.create(
        username="sync-source-user",
        display_name="同步源用户",
        email="sync-user@example.com",
        phone="13800001234",
        password=make_password("password123"),
        locale="zh-Hans",
        sync_source=source,
    )

    factory = APIRequestFactory()
    view = UserViewSet.as_view({"get": "search_user_list"})
    request = factory.get("/system_mgmt/api/user/search_user_list/", {"search": synced_user.username})
    force_authenticate(
        request,
        user=_build_authenticated_request_user(
            username="viewer-sync-source",
            is_superuser=False,
            permission={"system-manager": {"user_group-View"}},
        ),
    )

    response = view(request)
    payload = json.loads(response.content)

    assert response.status_code == 200
    returned_user = payload["data"]["users"][0]
    assert returned_user["sync_source"] == source.id


@pytest.mark.django_db
# 验证用户详情查询会按授权粒度只放行对应敏感类型的明文，其他类型继续脱敏。
def test_user_viewset_get_user_detail_only_reveals_authorized_sensitive_type():
    from apps.system_mgmt.models import Group
    from apps.system_mgmt.viewset.user_viewset import UserViewSet

    _set_sensitive_info_settings(enabled=True)
    group = Group.objects.create(name="group-for-partial-auth-detail")
    target_user = User.objects.create(
        username="partial_auth_user",
        display_name="部分授权用户",
        email="partial@example.com",
        phone="13800003333",
        password=make_password("password123"),
        locale="zh-Hans",
        group_list=[group.id],
    )
    SensitiveInfoAuthorization.objects.create(
        username="email-viewer",
        domain="domain.com",
        sensitive_types=["email"],
        remark="Need email only",
    )

    factory = APIRequestFactory()
    view = UserViewSet.as_view({"post": "get_user_detail"})
    request = factory.post(
        "/system_mgmt/api/user/get_user_detail/",
        {"user_id": target_user.id},
        format="json",
    )
    force_authenticate(
        request,
        user=_build_authenticated_request_user(
            username="email-viewer",
            is_superuser=False,
            group_list=[{"id": group.id, "name": group.name}],
            permission={"system-manager": {"user_group-View"}},
        ),
    )

    response = view(request)
    payload = json.loads(response.content)

    assert response.status_code == 200
    assert payload["data"]["email"] == "partial@example.com"
    assert payload["data"]["phone"] == "138****3333"


@pytest.mark.django_db
# 验证 get_all_users 这类机器消费路径在保护开启后仍返回原始邮箱和手机号。
def test_nats_get_all_users_keeps_raw_sensitive_fields_when_protection_enabled():
    _set_sensitive_info_settings(enabled=True)
    target_user = User.objects.create(
        username="nats_raw_user",
        display_name="NATS 原值用户",
        email="natsraw@example.com",
        phone="13800004444",
        password=make_password("password123"),
        locale="zh-Hans",
    )

    result = get_all_users()

    assert result["result"] is True
    returned_user = next(item for item in result["data"] if item["username"] == target_user.username)
    assert returned_user["email"] == "natsraw@example.com"
    assert returned_user["phone"] == "13800004444"


@pytest.mark.django_db
# 验证密码过期提醒任务在保护开启时仍使用原始邮箱地址作为发送收件人。
def test_check_password_expiry_and_notify_keeps_raw_email_recipients_when_protection_enabled(mocker):
    _set_sensitive_info_settings(enabled=True)
    Channel.objects.create(
        name="Test Email Channel",
        channel_type=ChannelChoices.EMAIL,
        config={"smtp_pwd": "plain-password", "mail_sender": "noreply@example.com"},
        description="test email channel",
        team=[],
    )
    expired_user = User.objects.create(
        username="expired-password-user",
        display_name="过期密码用户",
        email="expired-user@example.com",
        phone="13800005555",
        password=make_password("password123"),
        locale="zh-Hans",
        password_last_modified=timezone.now() - timedelta(days=181),
        disabled=False,
    )
    User.objects.create(
        username="fresh-password-user",
        display_name="未过期密码用户",
        email="fresh-user@example.com",
        phone="13800006666",
        password=make_password("password123"),
        locale="zh-Hans",
        password_last_modified=timezone.now() - timedelta(days=10),
        disabled=False,
    )
    send_email_mock = mocker.patch(
        "apps.system_mgmt.tasks.send_email_to_user",
        return_value={"result": True},
    )

    result = check_password_expiry_and_notify()

    assert result == {"result": True, "notified": 1, "failed": 0}
    send_email_mock.assert_called_once()
    args = send_email_mock.call_args.args
    assert args[2] == [expired_user.email]
    assert args[3] == "密码已过期提醒"


@pytest.mark.django_db
def test_user_serializer_exposes_derived_status_with_priority_order():
    SystemSettings.objects.update_or_create(
        key="pwd_set_validity_period",
        defaults={"value": "180"},
    )

    now = timezone.now()
    users = [
        User(
            username="disabled-user",
            display_name="禁用用户",
            email="disabled@example.com",
            phone="13800010001",
            password="hashed-password",
            locale="zh-Hans",
            disabled=True,
            account_locked_until=now + timedelta(minutes=30),
            password_last_modified=now - timedelta(days=400),
        ),
        User(
            username="locked-user",
            display_name="锁定用户",
            email="locked@example.com",
            phone="13800010002",
            password="hashed-password",
            locale="zh-Hans",
            disabled=False,
            account_locked_until=now + timedelta(minutes=30),
            password_last_modified=now - timedelta(days=400),
        ),
        User(
            username="expired-user",
            display_name="过期用户",
            email="expired@example.com",
            phone="13800010003",
            password="hashed-password",
            locale="zh-Hans",
            disabled=False,
            account_locked_until=None,
            password_last_modified=now - timedelta(days=400),
        ),
        User(
            username="normal-user",
            display_name="正常用户",
            email="normal@example.com",
            phone="13800010004",
            password="hashed-password",
            locale="zh-Hans",
            disabled=False,
            account_locked_until=None,
            password_last_modified=now - timedelta(days=10),
        ),
    ]

    serializer = UserSerializer(users, many=True)
    statuses = {item["username"]: item["status"] for item in serializer.data}

    assert statuses == {
        "disabled-user": "disabled",
        "locked-user": "locked",
        "expired-user": "password_expired",
        "normal-user": "normal",
    }


@pytest.mark.django_db
def test_user_serializer_treats_missing_password_time_and_non_positive_validity_as_not_expired():
    SystemSettings.objects.update_or_create(
        key="pwd_set_validity_period",
        defaults={"value": "0"},
    )

    now = timezone.now()
    users = [
        User(
            username="permanent-user",
            display_name="永久有效用户",
            email="permanent@example.com",
            phone="13800010005",
            password="hashed-password",
            locale="zh-Hans",
            disabled=False,
            account_locked_until=None,
            password_last_modified=now - timedelta(days=400),
        ),
        User(
            username="missing-password-time-user",
            display_name="缺少密码时间用户",
            email="missing@example.com",
            phone="13800010006",
            password="hashed-password",
            locale="zh-Hans",
            disabled=False,
            account_locked_until=None,
            password_last_modified=None,
        ),
    ]

    serializer = UserSerializer(users, many=True)
    statuses = {item["username"]: item["status"] for item in serializer.data}

    assert statuses == {
        "permanent-user": "normal",
        "missing-password-time-user": "normal",
    }


@pytest.mark.django_db
def test_user_viewset_change_status_returns_partial_success_for_mixed_targets():
    from apps.system_mgmt.viewset.user_viewset import UserViewSet

    editable_group = Group.objects.create(name="group-for-change-status")
    enabled_user = User.objects.create(
        username="enabled-user",
        display_name="启用用户",
        email="enabled-status@example.com",
        phone="13800010007",
        password=make_password("password123"),
        locale="zh-Hans",
        group_list=[editable_group.id],
        disabled=False,
    )
    disabled_user = User.objects.create(
        username="disabled-target-user",
        display_name="禁用目标用户",
        email="disabled-target@example.com",
        phone="13800010008",
        password=make_password("password123"),
        locale="zh-Hans",
        group_list=[editable_group.id],
        disabled=True,
    )

    factory = APIRequestFactory()
    view = UserViewSet.as_view({"post": "change_status"})
    save_calls = []
    original_save = User.save

    def traced_save(self, *args, **kwargs):
        save_calls.append({"id": self.id, "update_fields": kwargs.get("update_fields")})
        return original_save(self, *args, **kwargs)

    request = factory.post(
        "/system_mgmt/api/user/change_status/",
        {"user_ids": [enabled_user.id, disabled_user.id], "action": "enable"},
        format="json",
    )
    force_authenticate(
        request,
        user=_build_authenticated_request_user(
            username="status-editor",
            permission={"system-manager": {"user_group-Edit User"}},
            group_list=[{"id": editable_group.id, "name": editable_group.name}],
            is_superuser=False,
        ),
    )

    with patch.object(User, "save", new=traced_save):
        response = view(request)
    payload = json.loads(response.content)
    enabled_user.refresh_from_db()
    disabled_user.refresh_from_db()

    assert response.status_code == 200
    assert payload["result"] is True
    assert payload["data"]["action"] == "enable"
    assert payload["data"]["total"] == 2
    assert payload["data"]["success_ids"] == [disabled_user.id]
    assert payload["data"]["skipped"] == [{"id": enabled_user.id, "reason": "user_not_disabled"}]
    assert enabled_user.disabled is False
    assert disabled_user.disabled is False
    assert save_calls == [{"id": disabled_user.id, "update_fields": ["disabled"]}]


@pytest.mark.django_db
def test_user_viewset_change_status_unlock_clears_lock_state_only_for_locked_users():
    from apps.system_mgmt.viewset.user_viewset import UserViewSet

    editable_group = Group.objects.create(name="group-for-unlock-status")
    now = timezone.now()
    locked_user = User.objects.create(
        username="locked-target-user",
        display_name="锁定目标用户",
        email="locked-target@example.com",
        phone="13800010009",
        password=make_password("password123"),
        locale="zh-Hans",
        group_list=[editable_group.id],
        account_locked_until=now + timedelta(minutes=30),
        password_error_count=3,
    )
    normal_user = User.objects.create(
        username="normal-target-user",
        display_name="正常目标用户",
        email="normal-target@example.com",
        phone="13800010010",
        password=make_password("password123"),
        locale="zh-Hans",
        group_list=[editable_group.id],
        account_locked_until=None,
        password_error_count=1,
    )

    factory = APIRequestFactory()
    view = UserViewSet.as_view({"post": "change_status"})
    save_calls = []
    original_save = User.save

    def traced_save(self, *args, **kwargs):
        save_calls.append({"id": self.id, "update_fields": kwargs.get("update_fields")})
        return original_save(self, *args, **kwargs)

    request = factory.post(
        "/system_mgmt/api/user/change_status/",
        {"user_ids": [locked_user.id, normal_user.id], "action": "unlock"},
        format="json",
    )
    force_authenticate(
        request,
        user=_build_authenticated_request_user(
            username="status-unlocker",
            permission={"system-manager": {"user_group-Edit User"}},
            group_list=[{"id": editable_group.id, "name": editable_group.name}],
            is_superuser=False,
        ),
    )

    with patch.object(User, "save", new=traced_save):
        response = view(request)
    payload = json.loads(response.content)
    locked_user.refresh_from_db()
    normal_user.refresh_from_db()

    assert response.status_code == 200
    assert payload["result"] is True
    assert payload["data"]["action"] == "unlock"
    assert payload["data"]["success_ids"] == [locked_user.id]
    assert payload["data"]["skipped"] == [{"id": normal_user.id, "reason": "user_not_locked"}]
    assert locked_user.account_locked_until is None
    assert locked_user.password_error_count == 0
    assert normal_user.account_locked_until is None
    assert normal_user.password_error_count == 1
    assert save_calls == [
        {
            "id": locked_user.id,
            "update_fields": ["account_locked_until", "password_error_count"],
        }
    ]
