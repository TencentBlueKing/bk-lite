import importlib
import json
import types
from datetime import timedelta

import pytest
from django.contrib.auth.hashers import make_password
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.system_mgmt.models import Channel, OperationLog, SensitiveInfoAuthorization, SystemSettings, User
from apps.system_mgmt.models.channel import ChannelChoices
from apps.system_mgmt.nats_api import get_all_users
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
# 验证敏感信息授权记录可以创建成功，并能在列表接口中按预期返回展示信息。
def test_sensitive_info_authorization_viewset_creates_and_lists_records():
    from apps.system_mgmt.enterprise.viewset.sensitive_info_authorization_viewset import SensitiveInfoAuthorizationViewSet

    User.objects.create(
        username="authorized_user",
        display_name="授权用户",
        email="authorized@example.com",
        password=make_password("password123"),
        locale="zh-Hans",
    )

    factory = APIRequestFactory()
    create_view = SensitiveInfoAuthorizationViewSet.as_view({"post": "create"})
    create_request = factory.post(
        "/system_mgmt/api/sensitive_info_authorization/",
        {
            "username": "authorized_user",
            "domain": "domain.com",
            "sensitive_types": ["email", "phone"],
            "remark": "Need plaintext contact access",
        },
        format="json",
    )
    force_authenticate(
        create_request,
        user=_build_authenticated_request_user(
            username="creator-admin",
            permission={"system-manager": {"sensitive_info-Add", "sensitive_info-View"}},
        ),
    )

    create_response = create_view(create_request)

    assert create_response.status_code == 201
    authorization = SensitiveInfoAuthorization.objects.get(username="authorized_user", domain="domain.com")
    assert authorization.sensitive_types == ["email", "phone"]
    assert create_response.data["sensitive_types"] == ["email", "phone"]
    assert create_response.data["display_name"] == "授权用户"
    assert create_response.data["authorized_types_text"] == "用户邮箱、用户手机号"
    assert create_response.data["authorized_at"]

    list_view = SensitiveInfoAuthorizationViewSet.as_view({"get": "list"})
    list_request = factory.get("/system_mgmt/api/sensitive_info_authorization/")
    force_authenticate(
        list_request,
        user=_build_authenticated_request_user(
            username="viewer-admin",
            permission={"system-manager": {"sensitive_info-View"}},
        ),
    )

    list_response = list_view(list_request)

    assert list_response.status_code == 200
    assert len(list_response.data) == 1
    assert list_response.data[0]["username"] == "authorized_user"
    assert list_response.data[0]["display_name"] == "授权用户"
    assert list_response.data[0]["sensitive_types"] == ["email", "phone"]
    assert list_response.data[0]["authorized_types_text"] == "用户邮箱、用户手机号"
    assert list_response.data[0]["authorized_at"]
    assert list_response.data[0]["remark"] == "Need plaintext contact access"



@pytest.mark.django_db
# 验证新增和删除敏感信息授权记录时都会写入对应的操作日志。
def test_sensitive_info_authorization_viewset_records_operation_logs_for_create_and_destroy():
    from apps.system_mgmt.enterprise.viewset.sensitive_info_authorization_viewset import SensitiveInfoAuthorizationViewSet

    User.objects.create(
        username="log-target-user",
        display_name="日志目标用户",
        email="log-target@example.com",
        password=make_password("password123"),
        locale="zh-Hans",
    )

    factory = APIRequestFactory()
    create_view = SensitiveInfoAuthorizationViewSet.as_view({"post": "create"})
    create_request = factory.post(
        "/system_mgmt/api/sensitive_info_authorization/",
        {
            "username": "log-target-user",
            "domain": "domain.com",
            "sensitive_types": ["email", "phone"],
            "remark": "record operation log",
        },
        format="json",
    )
    force_authenticate(
        create_request,
        user=_build_authenticated_request_user(
            username="log-admin",
            permission={"system-manager": {"sensitive_info-Add", "sensitive_info-View"}},
        ),
    )

    create_response = create_view(create_request)

    assert create_response.status_code == 201
    create_log = OperationLog.objects.get(action_type="create", app="sensitive_info")
    assert create_log.username == "log-admin"
    assert create_log.summary == "新增敏感信息授权: log-target-user@domain.com (用户邮箱、用户手机号)"

    authorization = SensitiveInfoAuthorization.objects.get(username="log-target-user", domain="domain.com")
    destroy_view = SensitiveInfoAuthorizationViewSet.as_view({"delete": "destroy"})
    destroy_request = factory.delete(f"/system_mgmt/api/sensitive_info_authorization/{authorization.id}/")
    force_authenticate(
        destroy_request,
        user=_build_authenticated_request_user(
            username="log-admin",
            permission={"system-manager": {"sensitive_info-Delete"}},
        ),
    )

    destroy_response = destroy_view(destroy_request, pk=authorization.id)

    assert destroy_response.status_code == 204
    delete_log = OperationLog.objects.get(action_type="delete", app="sensitive_info")
    assert delete_log.username == "log-admin"
    assert delete_log.summary == "删除敏感信息授权: log-target-user@domain.com (用户邮箱、用户手机号)"
    assert OperationLog.objects.filter(app="sensitive_info").count() == 2



@pytest.mark.django_db
# 验证 current_user 接口会返回当前用户已授权的敏感信息类型集合。
def test_sensitive_info_authorization_viewset_current_user_returns_authorized_types():
    from apps.system_mgmt.enterprise.viewset.sensitive_info_authorization_viewset import SensitiveInfoAuthorizationViewSet

    SensitiveInfoAuthorization.objects.create(
        username="current-user",
        domain="domain.com",
        sensitive_types=["email", "phone"],
        remark="Need raw contact fields",
    )

    factory = APIRequestFactory()
    view = SensitiveInfoAuthorizationViewSet.as_view({"get": "current_user"})
    request = factory.get("/system_mgmt/api/sensitive_info_authorization/current_user/")
    force_authenticate(
        request,
        user=_build_authenticated_request_user(
            username="current-user",
            is_superuser=False,
            permission={"system-manager": {"sensitive_info-View"}},
        ),
    )

    response = view(request)

    assert response.status_code == 200
    assert response.data == {"result": True, "data": {"authorized_types": ["email", "phone"]}}


@pytest.mark.django_db
# 验证 current_user 接口在没有授权记录时返回空的敏感信息类型集合。
def test_sensitive_info_authorization_viewset_current_user_returns_empty_when_missing():
    from apps.system_mgmt.enterprise.viewset.sensitive_info_authorization_viewset import SensitiveInfoAuthorizationViewSet

    factory = APIRequestFactory()
    view = SensitiveInfoAuthorizationViewSet.as_view({"get": "current_user"})
    request = factory.get("/system_mgmt/api/sensitive_info_authorization/current_user/")
    force_authenticate(
        request,
        user=_build_authenticated_request_user(
            username="no-sensitive-access-user",
            is_superuser=False,
            permission={"system-manager": {"sensitive_info-View"}},
        ),
    )

    response = view(request)

    assert response.status_code == 200
    assert response.data == {"result": True, "data": {"authorized_types": []}}


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
# 验证批量脱敏逻辑会复用全局设置与授权查询，避免对列表中每个用户产生重复查询。
def test_apply_sensitive_info_mask_to_list_reuses_settings_and_authorization_queries():
    from apps.system_mgmt.enterprise.sensitive_info import apply_sensitive_info_mask_to_list

    _set_sensitive_info_settings(enabled=True)
    SensitiveInfoAuthorization.objects.create(
        username="authorized-viewer",
        domain="domain.com",
        sensitive_types=["email"],
        remark="Need email only",
    )
    request_user = _build_authenticated_request_user(
        username="authorized-viewer",
        is_superuser=False,
        permission={"system-manager": {"user_group-View"}},
    )
    user_list = [
        {"username": "u1", "email": "one@example.com", "phone": "13800001111"},
        {"username": "u2", "email": "two@example.com", "phone": "13800002222"},
        {"username": "u3", "email": "three@example.com", "phone": "13800003333"},
    ]

    with CaptureQueriesContext(connection) as captured_queries:
        masked = apply_sensitive_info_mask_to_list(user_list, request_user)

    assert len(captured_queries) <= 2
    assert masked[0]["email"] == "one@example.com"
    assert masked[0]["phone"] == "138****1111"


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
