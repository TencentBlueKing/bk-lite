"""
Issue #3466: create_user 未设密码初始值，新用户 password 为空字符串可能绕过 check_password

修复验证：create_user 接口创建的用户 password 字段必须为 Django 不可用密码标记（!开头），
而非空字符串；且 check_password(任意值, 该密码) 必须返回 False，禁止以任何密码登录。
"""

import json
import types

import pytest
from django.contrib.auth.hashers import check_password, is_password_usable, make_password
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.system_mgmt.models import Group, Role, SystemSettings, User
from apps.system_mgmt.viewset.user_viewset import UserViewSet


def _admin_user(**overrides):
    defaults = {
        "username": "test-admin",
        "domain": "domain.com",
        "locale": "en",
        "is_superuser": True,
        "is_authenticated": True,
        "permission": {"system-manager": {"user_group-Add User"}},
    }
    defaults.update(overrides)
    return types.SimpleNamespace(**defaults)


def _create_local_user(username: str):
    role = Role.objects.create(name=f"operator-{username}", app="")
    group = Group.objects.create(name=f"group-{username}")
    factory = APIRequestFactory()
    view = UserViewSet.as_view({"post": "create_user"})
    request = factory.post(
        "/system_mgmt/api/user/create_user/",
        {
            "username": username,
            "lastName": "测试用户",
            "email": f"{username}@example.com",
            "phone": None,
            "locale": "zh-Hans",
            "timezone": "Asia/Shanghai",
            "groups": [group.id],
            "roles": [role.id],
            "rules": [],
        },
        format="json",
    )
    force_authenticate(request, user=_admin_user())
    return view(request)


@pytest.mark.django_db
def test_create_user_password_is_not_empty_string():
    """
    修复验证：create_user 后新用户 password 字段不得为空字符串。
    若将 password=make_password(None) 的修复 revert，新用户 password 将为 ""，本测试失败。
    """
    role = Role.objects.create(name="operator-3466", app="")
    group = Group.objects.create(name="group-3466")

    factory = APIRequestFactory()
    view = UserViewSet.as_view({"post": "create_user"})

    request = factory.post(
        "/system_mgmt/api/user/create_user/",
        {
            "username": "newuser-3466",
            "lastName": "测试用户3466",
            "email": "newuser3466@example.com",
            "phone": None,
            "locale": "zh-Hans",
            "timezone": "Asia/Shanghai",
            "groups": [group.id],
            "roles": [role.id],
            "rules": [],
        },
        format="json",
    )
    force_authenticate(request, user=_admin_user())

    response = view(request)
    payload = json.loads(response.content)

    assert response.status_code == 200
    assert payload == {"result": True}

    user = User.objects.get(username="newuser-3466")

    # 核心断言：password 不得为空字符串
    assert user.password != "", "create_user 创建的用户 password 不得为空字符串（安全缺陷 #3466）"

    # password 字段必须是不可用密码标记（! 开头），禁止任何字符串通过 check_password 验证
    assert not is_password_usable(user.password), (
        "create_user 创建的用户密码应标记为不可用（make_password(None)），"
        "而非存储明文或空字符串（安全缺陷 #3466）"
    )

    # 空字符串不得通过密码验证
    assert not check_password("", user.password), (
        "以空字符串作为密码不得通过 check_password 验证（安全缺陷 #3466）"
    )

    # 任意字符串均不得通过密码验证（不可用密码标记保证）
    assert not check_password("anypassword", user.password), (
        "新创建用户的密码标记为不可用，check_password 对任意输入均应返回 False（安全缺陷 #3466）"
    )


@pytest.mark.django_db
def test_create_local_user_uses_enabled_initial_password_and_forces_change():
    SystemSettings.objects.update_or_create(
        key="user_create_initial_password_enabled", defaults={"value": "1"}
    )
    SystemSettings.objects.update_or_create(
        key="user_create_initial_password_hash", defaults={"value": make_password("InitialPwd1!")}
    )

    response = _create_local_user("initial-password-user")

    assert response.status_code == 200
    user = User.objects.get(username="initial-password-user")
    assert check_password("InitialPwd1!", user.password)
    assert user.temporary_pwd is True


@pytest.mark.django_db
def test_create_local_user_without_enabled_initial_password_keeps_unusable_password():
    SystemSettings.objects.update_or_create(
        key="user_create_initial_password_enabled", defaults={"value": "0"}
    )

    response = _create_local_user("no-initial-password-user")

    assert response.status_code == 200
    user = User.objects.get(username="no-initial-password-user")
    assert not is_password_usable(user.password)
    assert user.temporary_pwd is False
