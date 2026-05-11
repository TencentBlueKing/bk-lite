import importlib.util
import json
import logging
import sys
import types
from pathlib import Path

import pytest
from django.db import connection
from django.contrib.auth.hashers import make_password
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.job_mgmt.constants import ExecutionStatus, OSType
from apps.system_mgmt import nats_api
from apps.system_mgmt.models import OperationLog, SensitiveInfoAuthorization, SystemSettings, User
from apps.system_mgmt.nats_api import get_all_users, get_authorized_groups_scoped
from apps.system_mgmt.serializers.user_serializer import UserSerializer

logger = logging.getLogger(__name__)


def _install_module(monkeypatch, name, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    monkeypatch.setitem(sys.modules, name, module)
    return module


def _load_module(module_name, file_path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_target_view(monkeypatch):
    class AuthViewSet:
        pass

    class Response:
        def __init__(self, data, status=None):
            self.data = data
            self.status_code = status

    class BaseAppException(Exception):
        pass

    def action(*args, **kwargs):
        def decorator(func):
            return func

        return decorator

    def has_permission(*args, **kwargs):
        def decorator(func):
            return func

        return decorator

    class _TargetManager:
        @staticmethod
        def all():
            return []

    class _Target:
        objects = _TargetManager()

    _install_module(monkeypatch, "rest_framework", status=types.SimpleNamespace(HTTP_400_BAD_REQUEST=400, HTTP_500_INTERNAL_SERVER_ERROR=500))
    _install_module(monkeypatch, "rest_framework.decorators", action=action)
    _install_module(monkeypatch, "rest_framework.response", Response=Response)
    _install_module(monkeypatch, "apps.core.decorators.api_permission", HasPermission=has_permission)
    _install_module(monkeypatch, "apps.core.exceptions.base_app_exception", BaseAppException=BaseAppException)
    _install_module(monkeypatch, "apps.core.logger", job_logger=types.SimpleNamespace(exception=lambda *args, **kwargs: None))
    _install_module(monkeypatch, "apps.core.utils.viewset_utils", AuthViewSet=AuthViewSet)
    _install_module(monkeypatch, "apps.job_mgmt.constants", OSType=object(), SSHCredentialType=object())
    _install_module(monkeypatch, "apps.job_mgmt.filters.target", TargetFilter=object)
    _install_module(monkeypatch, "apps.job_mgmt.models", Target=_Target)
    _install_module(
        monkeypatch,
        "apps.job_mgmt.serializers.target",
        TargetBatchDeleteSerializer=object,
        TargetSerializer=object,
        TargetTestConnectionSerializer=object,
    )
    _install_module(monkeypatch, "apps.node_mgmt.models", CloudRegion=object)
    _install_module(monkeypatch, "apps.rpc.executor", Executor=object)
    _install_module(monkeypatch, "apps.rpc.node_mgmt", NodeMgmt=object)
    _install_module(monkeypatch, "apps.rpc.system_mgmt", SystemMgmt=object)

    return _load_module(
        "job_target_view_test_module",
        Path(__file__).resolve().parents[2] / "job_mgmt" / "views" / "target.py",
    )


def create_test_users():
    """创建测试用户数据"""
    test_users = [
        {
            "username": "test_user1",
            "display_name": "测试用户1",
            "email": "test1@example.com",
            "password": make_password("password123"),
            "locale": "zh-Hans",
        },
        {
            "username": "test_user2",
            "display_name": "测试用户2",
            "email": "test2@example.com",
            "password": make_password("password123"),
            "locale": "en-US",
        },
    ]

    # 创建测试用户并返回创建的用户列表
    created_users = []
    for user_data in test_users:
        user = User.objects.create(**user_data)
        created_users.append(user)

    return created_users


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


@pytest.mark.django_db
def test_get_all_users():
    # 初始化测试用户数据
    create_test_users()

    # 调用被测函数
    result = get_all_users()
    logger.info(result)

    # 验证结果
    assert result["result"] is True
    assert len(result["data"]) >= 2  # 至少包含我们创建的两个用户

    # 验证返回的用户数据包含我们创建的用户
    usernames = [user["username"] for user in result["data"]]
    assert "test_user1" in usernames
    assert "test_user2" in usernames


@pytest.mark.django_db
def test_user_serializer_exposes_phone_but_not_password_or_otp_secret():
    user = User.objects.create(
        username="serializer_user",
        display_name="序列化用户",
        email="serializer@example.com",
        phone="13800000001",
        password=make_password("password123"),
        otp_secret="masked-secret",
        locale="zh-Hans",
    )

    data = UserSerializer(user).data

    assert data["phone"] == "13800000001"
    assert "password" not in data
    assert "otp_secret" not in data


@pytest.mark.django_db
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
def test_sensitive_info_authorization_viewset_creates_and_lists_records():
    from apps.system_mgmt.models import SensitiveInfoAuthorization
    from apps.system_mgmt.viewset.sensitive_info_authorization_viewset import SensitiveInfoAuthorizationViewSet

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
            permission={"system-manager": {"security_settings-Add", "security_settings-View"}},
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
            permission={"system-manager": {"security_settings-View"}},
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
def test_sensitive_info_authorization_viewset_allows_list_create_destroy_but_blocks_detail_mutations():
    from apps.system_mgmt.viewset.sensitive_info_authorization_viewset import SensitiveInfoAuthorizationViewSet

    factory = APIRequestFactory()
    create_view = SensitiveInfoAuthorizationViewSet.as_view({"post": "create"})
    create_request = factory.post(
        "/system_mgmt/api/sensitive_info_authorization/",
        {
            "username": "unauthorized-user",
            "sensitive_types": ["email"],
            "remark": "should fail",
        },
        format="json",
    )
    force_authenticate(
        create_request,
        user=_build_authenticated_request_user(
            username="unauthorized-user",
            is_superuser=False,
            permission={"system-manager": {"user_group-View"}},
        ),
    )

    create_response = create_view(create_request)

    assert create_response.status_code == 201
    assert SensitiveInfoAuthorization.objects.count() == 1
    assert create_response.data["username"] == "unauthorized-user"
    assert create_response.data["sensitive_types"] == ["email"]
    assert create_response.data["remark"] == "should fail"

    list_view = SensitiveInfoAuthorizationViewSet.as_view({"get": "list"})
    list_request = factory.get("/system_mgmt/api/sensitive_info_authorization/")
    force_authenticate(
        list_request,
        user=_build_authenticated_request_user(
            username="unauthorized-user",
            is_superuser=False,
            permission={"system-manager": {"user_group-View"}},
        ),
    )

    list_response = list_view(list_request)

    assert list_response.status_code == 200
    assert len(list_response.data) == 1
    assert list_response.data[0]["username"] == "unauthorized-user"

    destroy_view = SensitiveInfoAuthorizationViewSet.as_view({"delete": "destroy"})
    destroy_request = factory.delete("/system_mgmt/api/sensitive_info_authorization/1/")
    force_authenticate(
        destroy_request,
        user=_build_authenticated_request_user(
            username="unauthorized-user",
            is_superuser=False,
            permission={"system-manager": {"user_group-View"}},
        ),
    )

    destroy_response = destroy_view(destroy_request, pk=SensitiveInfoAuthorization.objects.first().id)

    assert destroy_response.status_code == 204
    assert SensitiveInfoAuthorization.objects.count() == 0

    existing = SensitiveInfoAuthorization.objects.create(
        username="detail-user",
        domain="domain.com",
        sensitive_types=["email"],
        remark="detail test",
    )

    retrieve_view = SensitiveInfoAuthorizationViewSet.as_view({"get": "retrieve"})
    retrieve_request = factory.get(f"/system_mgmt/api/sensitive_info_authorization/{existing.id}/")
    force_authenticate(
        retrieve_request,
        user=_build_authenticated_request_user(
            username="unauthorized-user",
            is_superuser=False,
            permission={"system-manager": {"user_group-View"}},
        ),
    )
    retrieve_response = retrieve_view(retrieve_request, pk=existing.id)
    assert retrieve_response.status_code == 405

    update_view = SensitiveInfoAuthorizationViewSet.as_view({"put": "update"})
    update_request = factory.put(
        f"/system_mgmt/api/sensitive_info_authorization/{existing.id}/",
        {
            "username": "detail-user",
            "domain": "domain.com",
            "sensitive_types": ["phone"],
            "remark": "detail test updated",
        },
        format="json",
    )
    force_authenticate(
        update_request,
        user=_build_authenticated_request_user(
            username="unauthorized-user",
            is_superuser=False,
            permission={"system-manager": {"user_group-View"}},
        ),
    )
    update_response = update_view(update_request, pk=existing.id)
    assert update_response.status_code == 405

    partial_update_view = SensitiveInfoAuthorizationViewSet.as_view({"patch": "partial_update"})
    partial_update_request = factory.patch(
        f"/system_mgmt/api/sensitive_info_authorization/{existing.id}/",
        {"remark": "detail test patched"},
        format="json",
    )
    force_authenticate(
        partial_update_request,
        user=_build_authenticated_request_user(
            username="unauthorized-user",
            is_superuser=False,
            permission={"system-manager": {"user_group-View"}},
        ),
    )
    partial_update_response = partial_update_view(partial_update_request, pk=existing.id)
    assert partial_update_response.status_code == 405


@pytest.mark.django_db
def test_sensitive_info_authorization_viewset_records_operation_logs_for_create_and_destroy():
    from apps.system_mgmt.viewset.sensitive_info_authorization_viewset import SensitiveInfoAuthorizationViewSet

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
            permission={"system-manager": {"security_settings-Add", "security_settings-View"}},
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
            permission={"system-manager": {"security_settings-View"}},
        ),
    )

    destroy_response = destroy_view(destroy_request, pk=authorization.id)

    assert destroy_response.status_code == 204
    delete_log = OperationLog.objects.get(action_type="delete", app="sensitive_info")
    assert delete_log.username == "log-admin"
    assert delete_log.summary == "删除敏感信息授权: log-target-user@domain.com (用户邮箱、用户手机号)"
    assert OperationLog.objects.filter(app="sensitive_info").count() == 2


@pytest.mark.django_db
def test_system_settings_viewset_blocks_default_crud_routes():
    from apps.system_mgmt.viewset.system_settings_viewset import SystemSettingsViewSet

    factory = APIRequestFactory()

    list_view = SystemSettingsViewSet.as_view({"get": "list"})
    list_request = factory.get("/system_mgmt/api/system_settings/")
    force_authenticate(
        list_request,
        user=_build_authenticated_request_user(permission={"system-manager": {"security_settings-View"}}),
    )
    list_response = list_view(list_request)
    assert list_response.status_code == 405

    create_view = SystemSettingsViewSet.as_view({"post": "create"})
    create_request = factory.post("/system_mgmt/api/system_settings/", {"key": "foo", "value": "bar"}, format="json")
    force_authenticate(
        create_request,
        user=_build_authenticated_request_user(permission={"system-manager": {"security_settings-Add"}}),
    )
    create_response = create_view(create_request)
    assert create_response.status_code == 405

    setting = SystemSettings.objects.create(key="test_key", value="test_value")

    retrieve_view = SystemSettingsViewSet.as_view({"get": "retrieve"})
    retrieve_request = factory.get(f"/system_mgmt/api/system_settings/{setting.id}/")
    force_authenticate(
        retrieve_request,
        user=_build_authenticated_request_user(permission={"system-manager": {"security_settings-View"}}),
    )
    retrieve_response = retrieve_view(retrieve_request, pk=setting.id)
    assert retrieve_response.status_code == 405

    update_view = SystemSettingsViewSet.as_view({"put": "update"})
    update_request = factory.put(
        f"/system_mgmt/api/system_settings/{setting.id}/",
        {"key": "test_key", "value": "changed"},
        format="json",
    )
    force_authenticate(
        update_request,
        user=_build_authenticated_request_user(permission={"system-manager": {"security_settings-Edit"}}),
    )
    update_response = update_view(update_request, pk=setting.id)
    assert update_response.status_code == 405

    partial_update_view = SystemSettingsViewSet.as_view({"patch": "partial_update"})
    partial_update_request = factory.patch(
        f"/system_mgmt/api/system_settings/{setting.id}/",
        {"value": "changed-again"},
        format="json",
    )
    force_authenticate(
        partial_update_request,
        user=_build_authenticated_request_user(permission={"system-manager": {"security_settings-Edit"}}),
    )
    partial_update_response = partial_update_view(partial_update_request, pk=setting.id)
    assert partial_update_response.status_code == 405

    destroy_view = SystemSettingsViewSet.as_view({"delete": "destroy"})
    destroy_request = factory.delete(f"/system_mgmt/api/system_settings/{setting.id}/")
    force_authenticate(
        destroy_request,
        user=_build_authenticated_request_user(permission={"system-manager": {"security_settings-Delete"}}),
    )
    destroy_response = destroy_view(destroy_request, pk=setting.id)
    assert destroy_response.status_code == 405


@pytest.mark.django_db
def test_sensitive_info_authorization_viewset_current_user_returns_authorized_types():
    from apps.system_mgmt.viewset.sensitive_info_authorization_viewset import SensitiveInfoAuthorizationViewSet

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
            permission={"system-manager": {"user_group-View"}},
        ),
    )

    response = view(request)

    assert response.status_code == 200
    assert response.data == {"result": True, "data": {"authorized_types": ["email", "phone"]}}


@pytest.mark.django_db
def test_sensitive_info_authorization_viewset_current_user_returns_empty_when_missing():
    from apps.system_mgmt.viewset.sensitive_info_authorization_viewset import SensitiveInfoAuthorizationViewSet

    factory = APIRequestFactory()
    view = SensitiveInfoAuthorizationViewSet.as_view({"get": "current_user"})
    request = factory.get("/system_mgmt/api/sensitive_info_authorization/current_user/")
    force_authenticate(
        request,
        user=_build_authenticated_request_user(
            username="no-sensitive-access-user",
            is_superuser=False,
            permission={"system-manager": {"user_group-View"}},
        ),
    )

    response = view(request)

    assert response.status_code == 200
    assert response.data == {"result": True, "data": {"authorized_types": []}}


@pytest.mark.django_db
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
def test_user_viewset_update_user_rejects_invalid_phone():
    from apps.system_mgmt.models import Group, Role
    from apps.system_mgmt.viewset.user_viewset import UserViewSet

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
def test_user_viewset_update_user_keeps_existing_sensitive_fields_when_omitted():
    from apps.system_mgmt.models import Group, Role
    from apps.system_mgmt.viewset.user_viewset import UserViewSet

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
def test_user_viewset_update_user_allows_sensitive_change_when_protection_enabled_without_view_authorization():
    from apps.system_mgmt.models import Group, Role
    from apps.system_mgmt.viewset.user_viewset import UserViewSet

    _set_sensitive_info_settings(enabled=True)
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
def test_user_viewset_get_user_detail_only_reveals_authorized_sensitive_type():
    from apps.system_mgmt.viewset.user_viewset import UserViewSet

    _set_sensitive_info_settings(enabled=True)
    target_user = User.objects.create(
        username="partial_auth_user",
        display_name="部分授权用户",
        email="partial@example.com",
        phone="13800003333",
        password=make_password("password123"),
        locale="zh-Hans",
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
            permission={"system-manager": {"user_group-View"}},
        ),
    )

    response = view(request)
    payload = json.loads(response.content)

    assert response.status_code == 200
    assert payload["data"]["email"] == "partial@example.com"
    assert payload["data"]["phone"] == "138****3333"


@pytest.mark.django_db
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


def test_get_authorized_groups_scoped_rejects_forged_current_team(monkeypatch):
    user = types.SimpleNamespace(username="scope-user", domain="domain.com", group_list=[1])

    class _UserQuerySet:
        @staticmethod
        def first():
            return user

    class _UserManager:
        @staticmethod
        def filter(**kwargs):
            return _UserQuerySet()

    monkeypatch.setattr(nats_api.User, "objects", _UserManager())

    result = get_authorized_groups_scoped(
        {
            "username": "scope-user",
            "domain": "domain.com",
            "current_team": 2,
            "is_superuser": False,
        },
        include_children=True,
    )

    assert result == {"result": True, "data": []}


def test_get_authorized_groups_scoped_keeps_include_children(monkeypatch):
    user = types.SimpleNamespace(username="scope-children-user", domain="domain.com", group_list=[1])

    class _UserQuerySet:
        @staticmethod
        def first():
            return user

    class _UserManager:
        @staticmethod
        def filter(**kwargs):
            return _UserQuerySet()

    monkeypatch.setattr(nats_api.User, "objects", _UserManager())

    captured = {}

    def fake_get_user_authorized_child_groups(user_group_list, target_group_id, include_children=False):
        captured["user_group_list"] = user_group_list
        captured["target_group_id"] = target_group_id
        captured["include_children"] = include_children
        return [1, 11]

    monkeypatch.setattr(nats_api.GroupUtils, "get_user_authorized_child_groups", fake_get_user_authorized_child_groups)

    result = get_authorized_groups_scoped(
        {
            "username": "scope-children-user",
            "domain": "domain.com",
            "current_team": 1,
            "is_superuser": False,
        },
        include_children=True,
    )

    assert result == {"result": True, "data": [1, 11]}
    assert captured == {
        "user_group_list": [1],
        "target_group_id": 1,
        "include_children": True,
    }


def test_get_authorized_groups_scoped_rejects_invalid_current_team(monkeypatch):
    user = types.SimpleNamespace(username="scope-invalid-user", domain="domain.com", group_list=[1])

    class _UserQuerySet:
        @staticmethod
        def first():
            return user

    class _UserManager:
        @staticmethod
        def filter(**kwargs):
            return _UserQuerySet()

    monkeypatch.setattr(nats_api.User, "objects", _UserManager())

    result = get_authorized_groups_scoped(
        {
            "username": "scope-invalid-user",
            "domain": "domain.com",
            "current_team": "abc",
            "is_superuser": False,
        },
        include_children=False,
    )

    assert result == {"result": True, "data": []}


def test_target_query_nodes_propagates_authorized_scope_and_include_children(monkeypatch):
    captured = {}

    class NodeMgmt:
        def node_list(self, payload):
            captured["payload"] = payload
            return {"count": 0, "nodes": []}

    class SystemMgmt:
        def get_authorized_groups_scoped(self, actor_context, include_children=False):
            captured["actor_context"] = actor_context
            captured["include_children"] = include_children
            return {"result": True, "data": [3, 5]}

    class CloudRegionQuerySetStub:
        def values(self, *args):
            return []

    class CloudRegionManagerStub:
        def all(self):
            return CloudRegionQuerySetStub()

    class CloudRegionStub:
        objects = CloudRegionManagerStub()

    module = _load_target_view(monkeypatch)
    module.NodeMgmt = NodeMgmt
    module.SystemMgmt = SystemMgmt
    module.CloudRegion = CloudRegionStub

    request = types.SimpleNamespace(
        query_params={"page": "1", "page_size": "20"},
        COOKIES={"current_team": "3", "include_children": "1"},
        user=types.SimpleNamespace(
            username="job-user",
            domain="domain.com",
            is_superuser=False,
        ),
    )

    response = module.TargetViewSet().query_nodes(request)

    assert response.data["result"] is True
    assert captured["actor_context"] == {
        "username": "job-user",
        "domain": "domain.com",
        "current_team": 3,
        "include_children": True,
        "is_superuser": False,
    }
    assert captured["include_children"] is True
    assert captured["payload"]["organization_ids"] == [3, 5]
    assert captured["payload"]["permission_data"] == {
        "username": "job-user",
        "domain": "domain.com",
        "current_team": 3,
        "include_children": True,
    }


def test_target_query_nodes_rejects_invalid_current_team_cookie(monkeypatch):
    module = _load_target_view(monkeypatch)

    request = types.SimpleNamespace(
        query_params={"page": "1", "page_size": "20"},
        COOKIES={"current_team": "abc"},
        user=types.SimpleNamespace(
            username="job-user",
            domain="domain.com",
            is_superuser=False,
        ),
    )

    response = module.TargetViewSet().query_nodes(request)

    assert response.status_code == 400
    assert response.data == {"result": False, "message": "current_team 参数非法"}


def parse_data(data):
    items = data["data"].get("items", [])
    processed_items = []  # 用于暂存所有处理后的原始数据与计数，便于排序

    for item in items:
        bk_biz_name = item.get("bk_biz_name", "未知业务")
        active_status = item.get("active_status_count", {})

        # 告警相关数量
        warning_count = active_status.get("warning", 0)
        fatal_count = active_status.get("fatal", 0)
        remain_count = active_status.get("remain", 0)

        # 活动告警总数量 = warning + fatal
        active_alert_count = warning_count + fatal_count
        # 决定状态
        if fatal_count > 0:
            status = "danger"
        elif warning_count > 0 or remain_count > 0:
            status = "warned"
        else:
            status = "normal"

        brief = str(active_alert_count)

        # 暂时保存所有必要信息，用于后续排序
        processed_items.append(
            {
                "bk_biz_name": bk_biz_name,
                "fatal_count": fatal_count,
                "warning_count": warning_count,
                "remain_count": remain_count,
                "status": status,
                "brief": brief,
            }
        )

    # 排序：首先按 fatal_count 降序，然后 warning_count 降序，然后 remain_count 降序
    processed_items_sorted = sorted(processed_items, key=lambda x: (-x["fatal_count"], -x["warning_count"], -x["remain_count"]))

    # 构造最终返回的列表
    return_data = []
    for pitem in processed_items_sorted:
        transformed_item = {
            "status": pitem["status"],
            "name": pitem["bk_biz_name"],
            "brief": pitem["brief"],
            "other_url": False,
        }
        return_data.append(transformed_item)

    return True, return_data


@pytest.mark.django_db
def test_ansible_task_callback_records_ansible_failure_payload():
    from apps.job_mgmt.nats_api import ansible_task_callback
    from apps.job_mgmt.models.execution import JobExecution

    execution = JobExecution.objects.create(
        name="ansible failure callback",
        job_type="script",
        status=ExecutionStatus.RUNNING,
        target_list=[{"target_id": 1, "name": "host-1", "ip": "10.10.41.149"}],
        started_at=timezone.now(),
    )
    payload = {
        "task_id": str(execution.id),
        "task_type": "adhoc",
        "status": "failed",
        "success": False,
        "result": [
            {
                "host": "10.10.41.149",
                "status": "failed",
                "raw_status": "FAILED",
                "stdout": "",
                "stderr": "to use the 'ssh' connection type with passwords or pkcs11_provider, you must install the sshpass program",
                "exit_code": 2,
                "error_message": "to use the 'ssh' connection type with passwords or pkcs11_provider, you must install the sshpass program",
            }
        ],
        "error": "ansible adhoc failed with exit code 2",
        "started_at": "2026-03-27T09:50:10.546905+00:00",
        "finished_at": "2026-03-27T09:50:11.536357+00:00",
    }

    result = ansible_task_callback(payload)

    execution.refresh_from_db()

    assert result == {"success": True, "message": "回调处理成功"}
    assert execution.status == ExecutionStatus.FAILED
    assert execution.success_count == 0
    assert execution.failed_count == 1
    assert len(execution.execution_results) == 1
    assert execution.execution_results[0]["status"] == ExecutionStatus.FAILED
    assert execution.execution_results[0]["stdout"] == ""
    assert execution.execution_results[0]["stderr"] == payload["result"][0]["stderr"]
    assert execution.execution_results[0]["error_message"] == payload["result"][0]["error_message"]
    assert execution.execution_results[0]["exit_code"] == 2


@pytest.mark.django_db
def test_ansible_task_callback_consumes_per_host_result_array():
    from apps.job_mgmt.nats_api import ansible_task_callback
    from apps.job_mgmt.models.execution import JobExecution

    execution = JobExecution.objects.create(
        name="ansible host array callback",
        job_type="script",
        status=ExecutionStatus.RUNNING,
        target_list=[
            {"target_id": 1, "name": "host-1", "ip": "10.10.41.149"},
            {"target_id": 2, "name": "host-2", "ip": "10.10.41.150"},
        ],
        started_at=timezone.now(),
    )
    payload = {
        "task_id": str(execution.id),
        "task_type": "adhoc",
        "status": "failed",
        "success": False,
        "result": [
            {
                "host": "10.10.41.149",
                "status": "success",
                "raw_status": "CHANGED",
                "stdout": "ok-149",
                "stderr": "",
                "exit_code": 0,
                "error_message": "",
            },
            {
                "host": "10.10.41.150",
                "status": "failed",
                "raw_status": "FAILED",
                "stdout": "",
                "stderr": "boom-150",
                "exit_code": 2,
                "error_message": "boom-150",
            },
        ],
        "error": "ansible adhoc failed with exit code 2",
        "started_at": "2026-03-27T09:50:10.546905+00:00",
        "finished_at": "2026-03-27T09:50:11.536357+00:00",
    }

    result = ansible_task_callback(payload)

    execution.refresh_from_db()

    assert result == {"success": True, "message": "回调处理成功"}
    assert execution.status == ExecutionStatus.FAILED
    assert execution.success_count == 1
    assert execution.failed_count == 1
    assert len(execution.execution_results) == 2
    assert execution.execution_results[0]["ip"] == "10.10.41.149"
    assert execution.execution_results[0]["status"] == ExecutionStatus.SUCCESS
    assert execution.execution_results[0]["stdout"] == "ok-149"
    assert execution.execution_results[0]["stderr"] == ""
    assert execution.execution_results[0]["exit_code"] == 0
    assert execution.execution_results[1]["ip"] == "10.10.41.150"
    assert execution.execution_results[1]["status"] == ExecutionStatus.FAILED
    assert execution.execution_results[1]["stdout"] == ""
    assert execution.execution_results[1]["stderr"] == "boom-150"
    assert execution.execution_results[1]["error_message"] == "boom-150"
    assert execution.execution_results[1]["exit_code"] == 2


def test_file_distribution_normalizes_windows_target_path_before_remote_download(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        FileDistributionRunner,
        "get_ssh_credentials",
        classmethod(
            lambda cls, target_id: {
                "host": "10.10.41.149",
                "username": "Administrator",
                "password": "secret",
                "private_key": None,
                "port": 22,
                "node_id": "node-1",
            }
        ),
    )
    monkeypatch.setattr(
        "apps.job_mgmt.services.file_distribution_runner.Target.objects.filter",
        lambda **kwargs: type(
            "QuerySet",
            (),
            {
                "first": staticmethod(
                    lambda: type(
                        "TargetObj",
                        (),
                        {
                            "driver": "executor",
                            "cloud_region_id": None,
                            "os_type": OSType.WINDOWS,
                            "ip": "10.10.41.149",
                            "winrm_user": "Administrator",
                            "winrm_password": "encrypted-winrm-password",
                            "winrm_port": 5986,
                            "node_id": "node-1",
                        },
                    )()
                )
            },
        )(),
    )
    monkeypatch.setattr(
        FileDistributionRunner,
        "decrypt_password",
        staticmethod(lambda value: f"decrypted::{value}" if value else ""),
    )
    monkeypatch.setattr(
        FileDistributionRunner,
        "download_to_remote",
        staticmethod(
            lambda instance_id, file_item, target_path, ssh_creds, timeout, overwrite: captured.update(
                {
                    "instance_id": instance_id,
                    "file_item": file_item,
                    "target_path": target_path,
                    "ssh_creds": ssh_creds,
                    "timeout": timeout,
                    "overwrite": overwrite,
                }
            )
            or {"success": True}
        ),
    )

    runner = FileDistributionRunner(execution_id=1)
    file_item = {"name": "config.ini", "file_key": "abc"}

    runner.download_to_manual_target(
        file_item=file_item,
        target_id=1,
        target_path=r"C:\temp\nested\config.ini",
        timeout=60,
        overwrite=True,
    )

    assert captured["target_path"] == "C:/temp/nested/config.ini"
    assert captured["ssh_creds"]["username"] == "Administrator"
    assert captured["ssh_creds"]["password"] == "decrypted::encrypted-winrm-password"
    assert captured["ssh_creds"]["port"] == 5986


def test_file_distribution_uses_winrm_password_for_windows_manual_target(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        FileDistributionRunner,
        "get_ssh_credentials",
        classmethod(
            lambda cls, target_id: {
                "host": "10.10.41.149",
                "username": "",
                "password": "",
                "private_key": None,
                "port": 22,
                "node_id": "node-1",
            }
        ),
    )
    monkeypatch.setattr(
        FileDistributionRunner,
        "decrypt_password",
        staticmethod(lambda value: f"decrypted::{value}" if value else ""),
    )
    monkeypatch.setattr(
        "apps.job_mgmt.services.file_distribution_runner.Target.objects.filter",
        lambda **kwargs: type(
            "QuerySet",
            (),
            {
                "first": staticmethod(
                    lambda: type(
                        "TargetObj",
                        (),
                        {
                            "driver": "executor",
                            "cloud_region_id": None,
                            "os_type": OSType.WINDOWS,
                            "ip": "10.10.41.149",
                            "winrm_user": "Administrator",
                            "winrm_password": "encrypted-winrm-password",
                            "winrm_port": 5986,
                            "node_id": "node-1",
                        },
                    )()
                )
            },
        )(),
    )
    monkeypatch.setattr(
        FileDistributionRunner,
        "download_to_remote",
        staticmethod(
            lambda instance_id, file_item, target_path, ssh_creds, timeout, overwrite: captured.update(
                {
                    "instance_id": instance_id,
                    "file_item": file_item,
                    "target_path": target_path,
                    "ssh_creds": ssh_creds,
                    "timeout": timeout,
                    "overwrite": overwrite,
                }
            )
            or {"success": True}
        ),
    )

    runner = FileDistributionRunner(execution_id=1)
    file_item = {"name": "vc密码.txt", "file_key": "abc"}

    runner.download_to_manual_target(
        file_item=file_item,
        target_id=1,
        target_path=r"C:\temp\vc密码.txt",
        timeout=60,
        overwrite=True,
    )

    assert captured["ssh_creds"]["host"] == "10.10.41.149"
    assert captured["ssh_creds"]["username"] == "Administrator"
    assert captured["ssh_creds"]["password"] == "decrypted::encrypted-winrm-password"
    assert captured["ssh_creds"]["private_key"] is None
    assert captured["ssh_creds"]["port"] == 5986


@pytest.mark.django_db
def test_manual_windows_script_execution_routes_to_ansible(monkeypatch):
    from apps.job_mgmt.models.execution import JobExecution

    captured = {}

    monkeypatch.setattr(
        ScriptExecutionRunner,
        "_should_use_ansible",
        staticmethod(lambda target_source, target_list: True),
    )
    monkeypatch.setattr(
        ScriptExecutionRunner,
        "_execute_script_via_ansible",
        classmethod(
            lambda cls, execution, target_list, script_content, script_type: captured.update(
                {
                    "called": True,
                    "target_list": target_list,
                    "script_content": script_content,
                    "script_type": script_type,
                }
            )
        ),
    )
    monkeypatch.setattr(
        ScriptExecutionRunner,
        "_run_via_sidecar",
        lambda self, execution, target_list, script_content: (_ for _ in ()).throw(AssertionError("sidecar should not be used")),
    )
    monkeypatch.setattr(
        ScriptExecutionRunner,
        "_handle_dangerous_command",
        lambda self, execution, target_list: False,
    )

    execution = JobExecution.objects.create(
        name="windows script ansible route",
        job_type="script",
        status=ExecutionStatus.PENDING,
        target_source="manual",
        target_list=[{"target_id": 1, "name": "win-host", "ip": "10.10.41.149"}],
        script_type="powershell",
        script_content="Write-Host 'hello'",
        timeout=120,
    )

    runner = ScriptExecutionRunner(execution.id)
    runner.run()

    assert captured["called"] is True
    assert captured["target_list"] == execution.target_list
    assert captured["script_type"] == "powershell"
    assert captured["script_content"] == "Write-Host 'hello'"


def test_file_distribution_routes_manual_windows_ansible_target_to_ansible_executor(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        "apps.job_mgmt.services.file_distribution_runner.Target.objects.filter",
        lambda **kwargs: type(
            "QuerySet",
            (),
            {
                "first": staticmethod(
                    lambda: type(
                        "TargetObj",
                        (),
                        {
                            "id": 1,
                            "ip": "10.10.41.149",
                            "os_type": OSType.WINDOWS,
                            "driver": "ansible",
                            "cloud_region_id": 11,
                            "winrm_user": "Administrator",
                            "winrm_password": "encrypted-winrm-password",
                            "winrm_port": 5986,
                            "winrm_scheme": "https",
                            "winrm_transport": "ntlm",
                            "winrm_cert_validation": False,
                        },
                    )()
                )
            },
        )(),
    )
    monkeypatch.setattr(
        FileDistributionRunner,
        "decrypt_password",
        staticmethod(lambda value: f"decrypted::{value}" if value else ""),
    )
    monkeypatch.setattr(
        FileDistributionRunner,
        "_get_ansible_node",
        staticmethod(lambda cloud_region_id: "ansible-node-1"),
    )
    monkeypatch.setattr(
        AnsibleExecutor,
        "playbook",
        lambda self, **kwargs: captured.update({"playbook_kwargs": kwargs})
        or {"accepted": True, "status": "queued", "task_id": "task-123", "duplicate": False},
    )
    monkeypatch.setattr(
        AnsibleExecutor,
        "task_query",
        lambda self, task_id, timeout=10: {
            "task_id": task_id,
            "status": "success",
            "payload": {},
            "callback": {},
            "result": {
                "task_id": task_id,
                "task_type": "playbook",
                "status": "success",
                "success": True,
                "result": [
                    {
                        "host": "10.10.41.149",
                        "status": "success",
                        "raw_status": "CHANGED",
                        "stdout": "copied",
                        "stderr": "",
                        "exit_code": 0,
                        "error_message": "",
                    }
                ],
                "error": "",
            },
            "created_at": "2026-04-03T07:35:53.859291+00:00",
            "updated_at": "2026-04-03T07:35:53.880230+00:00",
        },
    )
    monkeypatch.setattr(
        FileDistributionRunner,
        "download_to_remote",
        staticmethod(lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("scp path should not be used"))),
    )

    runner = FileDistributionRunner(execution_id=42)
    result = runner.download_to_manual_target(
        file_item={"name": "config.ini", "file_key": "abc"},
        target_id=1,
        target_path=r"C:\deploy",
        timeout=60,
        overwrite=True,
    )

    assert captured["playbook_kwargs"]["files"] == [{"name": "config.ini", "file_key": "abc"}]
    assert captured["playbook_kwargs"]["file_distribution"]["target_path"] == "C:/deploy"
    assert captured["playbook_kwargs"]["host_credentials"][0]["connection"] == "winrm"
    assert result["success"] is True
    assert result["error"] == ""
    assert result["result"][0]["host"] == "10.10.41.149"


def test_ansible_playbook_allows_file_distribution_without_playbook():
    captured = {}

    class DummyClient:
        def run(self, instance_id, request_data, _timeout=None):
            captured["instance_id"] = instance_id
            captured["request_data"] = request_data
            captured["timeout"] = _timeout
            return {"success": True, "result": {"accepted": True}}

    executor = AnsibleExecutor("ansible-node-1")
    executor.playbook_client = DummyClient()

    result = executor.playbook(
        host_credentials=[{"host": "10.0.0.1", "user": "Administrator", "password": "secret", "connection": "winrm"}],
        files=[{"name": "channel_add.txt", "file_key": "file-key-1"}],
        file_distribution={"bucket_name": "test-bucket", "target_path": "C:/deploy", "overwrite": True},
        task_id="task-1",
        timeout=30,
    )

    assert result == {"success": True, "result": {"accepted": True}}
    assert captured["instance_id"] == "ansible-node-1"
    assert captured["timeout"] == 30
    assert captured["request_data"]["playbook_path"] == ""
    assert captured["request_data"]["playbook_content"] is None
    assert captured["request_data"]["files"] == [{"name": "channel_add.txt", "file_key": "file-key-1"}]
    assert captured["request_data"]["file_distribution"] == {"bucket_name": "test-bucket", "target_path": "C:/deploy", "overwrite": True}


def test_file_distribution_polls_until_ansible_task_finishes(monkeypatch):
    monkeypatch.setattr(
        "apps.job_mgmt.services.file_distribution_runner.Target.objects.filter",
        lambda **kwargs: type(
            "QuerySet",
            (),
            {
                "first": staticmethod(
                    lambda: type(
                        "TargetObj",
                        (),
                        {
                            "id": 1,
                            "ip": "10.10.41.149",
                            "os_type": OSType.WINDOWS,
                            "driver": "ansible",
                            "cloud_region_id": 11,
                            "winrm_user": "Administrator",
                            "winrm_password": "encrypted-winrm-password",
                            "winrm_port": 5986,
                            "winrm_scheme": "https",
                            "winrm_transport": "ntlm",
                            "winrm_cert_validation": False,
                        },
                    )()
                )
            },
        )(),
    )
    monkeypatch.setattr(
        FileDistributionRunner,
        "decrypt_password",
        staticmethod(lambda value: f"decrypted::{value}" if value else ""),
    )
    monkeypatch.setattr(
        FileDistributionRunner,
        "_get_ansible_node",
        staticmethod(lambda cloud_region_id: "ansible-node-1"),
    )
    monkeypatch.setattr(
        AnsibleExecutor,
        "playbook",
        lambda self, **kwargs: {"accepted": True, "status": "queued", "task_id": "task-running", "duplicate": False},
    )
    query_results = iter(
        [
            {
                "task_id": "task-running",
                "status": "running",
                "payload": {},
                "callback": {},
                "result": {"started_at": "2026-04-07T10:44:08.910000+00:00"},
            },
            {
                "task_id": "task-running",
                "status": "success",
                "payload": {},
                "callback": {},
                "result": {
                    "task_id": "task-running",
                    "task_type": "playbook",
                    "status": "success",
                    "success": True,
                    "result": [
                        {
                            "host": "10.10.41.149",
                            "status": "success",
                            "raw_status": "CHANGED",
                            "stdout": "copied",
                            "stderr": "",
                            "exit_code": 0,
                            "error_message": "",
                        }
                    ],
                    "error": "",
                },
            },
        ]
    )
    monkeypatch.setattr(
        AnsibleExecutor,
        "task_query",
        lambda self, task_id, timeout=10: next(query_results),
    )
    monkeypatch.setattr("apps.job_mgmt.services.file_distribution_runner.time.sleep", lambda _: None)

    runner = FileDistributionRunner(execution_id=42)
    result = runner.download_to_manual_target(
        file_item={"name": "config.ini", "file_key": "abc"},
        target_id=1,
        target_path=r"C:\deploy",
        timeout=60,
        overwrite=True,
    )

    assert result["success"] is True
    assert result["error"] == ""
    assert result["result"][0]["host"] == "10.10.41.149"


def test_file_distribution_raises_when_ansible_task_query_stays_running(monkeypatch):
    monkeypatch.setattr(
        "apps.job_mgmt.services.file_distribution_runner.Target.objects.filter",
        lambda **kwargs: type(
            "QuerySet",
            (),
            {
                "first": staticmethod(
                    lambda: type(
                        "TargetObj",
                        (),
                        {
                            "id": 1,
                            "ip": "10.10.41.149",
                            "os_type": OSType.WINDOWS,
                            "driver": "ansible",
                            "cloud_region_id": 11,
                            "winrm_user": "Administrator",
                            "winrm_password": "encrypted-winrm-password",
                            "winrm_port": 5986,
                            "winrm_scheme": "https",
                            "winrm_transport": "ntlm",
                            "winrm_cert_validation": False,
                        },
                    )()
                )
            },
        )(),
    )
    monkeypatch.setattr(
        FileDistributionRunner,
        "decrypt_password",
        staticmethod(lambda value: f"decrypted::{value}" if value else ""),
    )
    monkeypatch.setattr(
        FileDistributionRunner,
        "_get_ansible_node",
        staticmethod(lambda cloud_region_id: "ansible-node-1"),
    )
    monkeypatch.setattr(
        AnsibleExecutor,
        "playbook",
        lambda self, **kwargs: {"accepted": True, "status": "queued", "task_id": "task-running", "duplicate": False},
    )
    monkeypatch.setattr(
        AnsibleExecutor,
        "task_query",
        lambda self, task_id, timeout=10: {
            "task_id": task_id,
            "status": "running",
            "payload": {},
            "callback": {},
            "result": {"started_at": "2026-04-07T10:44:08.910000+00:00"},
        },
    )
    monkeypatch.setattr("apps.job_mgmt.services.file_distribution_runner.time.sleep", lambda _: None)

    runner = FileDistributionRunner(execution_id=42)

    with pytest.raises(ValueError, match="Ansible 文件分发任务未完成: status=running"):
        runner.download_to_manual_target(
            file_item={"name": "config.ini", "file_key": "abc"},
            target_id=1,
            target_path=r"C:\deploy",
            timeout=2,
            overwrite=True,
        )
