"""
本地用户初始密码 random / fixed / none 模式回归测试。

对齐用户同步处的 random / none 行为,并覆盖 fixed 模式邮件通知:
创建本地用户时,random 模式生成
`secrets.token_urlsafe(12)` 随机密码并通过邮件通道告知用户;fixed 模式使用
统一初始密码并通过邮件告知;none 模式则写入
不可用密码 sentinel。
"""
import json
import types
from unittest.mock import patch

import pytest
from django.contrib.auth.hashers import check_password, is_password_usable, make_password
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.system_mgmt.models import Channel, ChannelChoices, Group, Role, SystemSettings, User
from apps.system_mgmt.utils.password_vault import encrypt_for_vault
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


def _create_local_user(username, email=None):
    role = Role.objects.create(name=f"operator-{username}", app="")
    group = Group.objects.create(name=f"group-{username}")
    factory = APIRequestFactory()
    view = UserViewSet.as_view({"post": "create_user"})
    if email is None:
        email = f"{username}@example.com"
    payload = {
        "username": username,
        "lastName": "测试用户",
        "email": email,
        "phone": None,
        "locale": "zh-Hans",
        "timezone": "Asia/Shanghai",
        "groups": [group.id],
        "roles": [role.id],
        "rules": [],
    }
    request = factory.post("/system_mgmt/api/user/create_user/", payload, format="json")
    force_authenticate(request, user=_admin_user())
    return view(request)


def _set_mode(mode, email_channel_id=""):
    SystemSettings.objects.update_or_create(
        key="user_create_initial_password_mode", defaults={"value": mode}
    )
    SystemSettings.objects.update_or_create(
        key="user_create_initial_password_enabled", defaults={"value": "0"}
    )
    SystemSettings.objects.update_or_create(
        key="user_create_initial_password_hash", defaults={"value": ""}
    )
    SystemSettings.objects.update_or_create(
        key="user_create_initial_password_random_email_channel_id",
        defaults={"value": str(email_channel_id or "")},
    )


def _make_email_channel():
    return Channel.objects.create(
        name="test-email-channel",
        channel_type=ChannelChoices.EMAIL,
        config={},
        description="test",
    )


@pytest.mark.django_db
def test_create_user_mode_random_generates_password_without_returning_plaintext():
    """mode=random:随机初始密码仅通过邮件通知，不得出现在接口响应中。"""
    channel = _make_email_channel()
    _set_mode("random", email_channel_id=channel.id)
    raw = "RandP@ss-2026"

    with patch("apps.system_mgmt.viewset.user_viewset.secrets.token_urlsafe", return_value=raw), patch(
        "apps.system_mgmt.services.password_init_email.send_local_user_initial_password_email",
        return_value={"result": True, "message": "已发送"},
    ) as email_mock:
        response = _create_local_user("random-mode-user")

    assert response.status_code == 200
    payload = json.loads(response.content)
    assert payload["result"] is True
    assert payload["data"]["email_sent"] is True
    assert "raw_password" not in payload["data"]
    email_mock.assert_called_once()

    user = User.objects.get(username="random-mode-user")
    assert user.temporary_pwd is True
    assert check_password(raw, user.password)


@pytest.mark.django_db
def test_create_user_mode_random_rolls_back_when_email_delivery_fails():
    """mode=random:邮件发送失败时不得创建无法取得密码的用户。"""
    channel = _make_email_channel()
    _set_mode("random", email_channel_id=channel.id)
    raw = "RandomFail1-token"

    with patch("apps.system_mgmt.viewset.user_viewset.secrets.token_urlsafe", return_value=raw), patch(
        "apps.system_mgmt.services.password_init_email.send_local_user_initial_password_email",
        return_value={"result": False, "message": "smtp down"},
    ):
        response = _create_local_user("random-mode-fail")

    assert response.status_code == 400
    payload = json.loads(response.content)
    assert "smtp" in payload["message"]
    assert not User.objects.filter(username="random-mode-fail").exists()


@pytest.mark.django_db
def test_create_user_mode_random_without_channel_returns_400():
    """mode=random:未配置邮件通道时,create_user 必须返回 400,不能创建用户。"""
    _set_mode("random", email_channel_id="")
    response = _create_local_user("random-mode-no-channel")
    assert response.status_code == 400
    payload = json.loads(response.content)
    assert payload["result"] is False
    assert "邮件通道" in payload["message"]
    assert not User.objects.filter(username="random-mode-no-channel").exists()


@pytest.mark.django_db
def test_create_user_mode_random_without_email_returns_400():
    """mode=random:没有收件人邮箱时不得创建无法投递初始密码的用户。"""
    channel = _make_email_channel()
    _set_mode("random", email_channel_id=channel.id)
    raw = "NoEmail1@ss"

    with patch("apps.system_mgmt.viewset.user_viewset.secrets.token_urlsafe", return_value=raw), patch(
        "apps.system_mgmt.services.password_init_email.send_local_user_initial_password_email"
    ) as email_mock:
        response = _create_local_user("random-no-email", email="")

    assert response.status_code == 400
    payload = json.loads(response.content)
    assert "邮箱" in payload["message"]
    assert not User.objects.filter(username="random-no-email").exists()
    email_mock.assert_not_called()


@pytest.mark.django_db
def test_create_user_mode_random_retries_until_password_matches_current_policy():
    """mode=random 必须丢弃不符合当前密码策略的候选密码。"""
    channel = _make_email_channel()
    _set_mode("random", email_channel_id=channel.id)
    SystemSettings.objects.update_or_create(key="pwd_set_min_length", defaults={"value": "18"})
    SystemSettings.objects.update_or_create(key="pwd_set_max_length", defaults={"value": "20"})
    SystemSettings.objects.update_or_create(
        key="pwd_set_required_char_types", defaults={"value": "uppercase,lowercase,digit,special"}
    )
    valid_password = "StrongInitialPwd1!XY"

    with patch(
        "apps.system_mgmt.viewset.user_viewset.secrets.token_urlsafe",
        side_effect=["short", valid_password],
    ), patch(
        "apps.system_mgmt.services.password_init_email.send_local_user_initial_password_email",
        return_value={"result": True, "message": "已发送"},
    ):
        response = _create_local_user("random-policy-user")

    assert response.status_code == 200
    user = User.objects.get(username="random-policy-user")
    assert check_password(valid_password, user.password)


@pytest.mark.django_db
def test_create_user_mode_none_keeps_unusable_password():
    """mode=none:create_user 必须走 sentinel 路径,password 不可用。"""
    _set_mode("none")
    response = _create_local_user("none-mode-user")
    assert response.status_code == 200
    payload = json.loads(response.content)
    assert payload == {"result": True}
    user = User.objects.get(username="none-mode-user")
    assert not is_password_usable(user.password)
    assert user.temporary_pwd is False


@pytest.mark.django_db
def test_create_user_mode_fixed_default_still_uses_initial_hash():
    """mode=fixed(默认) + enabled=1:create_user 必须继续使用 user_create_initial_password_hash,与历史行为一致。"""
    channel = _make_email_channel()
    SystemSettings.objects.update_or_create(
        key="user_create_initial_password_mode", defaults={"value": "fixed"}
    )
    SystemSettings.objects.update_or_create(
        key="user_create_initial_password_enabled", defaults={"value": "1"}
    )
    SystemSettings.objects.update_or_create(
        key="user_create_initial_password_hash",
        defaults={"value": make_password("InitialPwd1!")},
    )
    SystemSettings.objects.update_or_create(
        key="user_create_initial_password_encrypted",
        defaults={"value": encrypt_for_vault("InitialPwd1!")},
    )
    SystemSettings.objects.update_or_create(
        key="user_create_initial_password_random_email_channel_id",
        defaults={"value": str(channel.id)},
    )

    with patch(
        "apps.system_mgmt.services.password_init_email.send_local_user_initial_password_email",
        return_value={"result": True, "message": "已发送"},
    ):
        response = _create_local_user("fixed-mode-user")
    assert response.status_code == 200
    user = User.objects.get(username="fixed-mode-user")
    assert check_password("InitialPwd1!", user.password)
    assert user.temporary_pwd is True


@pytest.mark.django_db
def test_create_user_mode_fixed_ignores_legacy_enabled_flag():
    """fixed 模式本身启用统一初始密码，不再依赖旧 enabled 字段。"""
    channel = _make_email_channel()
    _set_mode("fixed", email_channel_id=channel.id)
    SystemSettings.objects.update_or_create(
        key="user_create_initial_password_hash", defaults={"value": make_password("InitialPwd1!")}
    )
    SystemSettings.objects.update_or_create(
        key="user_create_initial_password_encrypted", defaults={"value": encrypt_for_vault("InitialPwd1!")}
    )

    with patch(
        "apps.system_mgmt.services.password_init_email.send_local_user_initial_password_email",
        return_value={"result": True, "message": "已发送"},
    ):
        response = _create_local_user("fixed-ignores-enabled")

    assert response.status_code == 200
    assert User.objects.get(username="fixed-ignores-enabled").temporary_pwd is True


@pytest.mark.django_db
def test_create_user_mode_fixed_sends_email_when_channel_is_configured():
    """mode=fixed + email_channel_id:create_user 使用统一初始密码并发送邮件。"""
    channel = _make_email_channel()
    SystemSettings.objects.update_or_create(
        key="user_create_initial_password_mode", defaults={"value": "fixed"}
    )
    SystemSettings.objects.update_or_create(
        key="user_create_initial_password_enabled", defaults={"value": "1"}
    )
    SystemSettings.objects.update_or_create(
        key="user_create_initial_password_hash",
        defaults={"value": make_password("InitialPwd1!")},
    )
    SystemSettings.objects.update_or_create(
        key="user_create_initial_password_encrypted",
        defaults={"value": encrypt_for_vault("InitialPwd1!")},
    )
    SystemSettings.objects.update_or_create(
        key="user_create_initial_password_random_email_channel_id",
        defaults={"value": str(channel.id)},
    )

    with patch(
        "apps.system_mgmt.services.password_init_email.send_local_user_initial_password_email",
        return_value={"result": True, "message": "已发送"},
    ) as email_mock:
        response = _create_local_user("fixed-mode-email-user")

    assert response.status_code == 200
    payload = json.loads(response.content)
    assert payload["result"] is True
    assert payload["data"]["email_sent"] is True
    assert "raw_password" not in payload["data"]
    email_mock.assert_called_once()

    user = User.objects.get(username="fixed-mode-email-user")
    assert check_password("InitialPwd1!", user.password)
    assert user.temporary_pwd is True


@pytest.mark.django_db
def test_create_user_mode_fixed_without_channel_returns_400():
    """启用统一初始密码但未配置邮件通道时不能创建用户。"""
    SystemSettings.objects.update_or_create(
        key="user_create_initial_password_mode", defaults={"value": "fixed"}
    )
    SystemSettings.objects.update_or_create(
        key="user_create_initial_password_enabled", defaults={"value": "1"}
    )
    SystemSettings.objects.update_or_create(
        key="user_create_initial_password_hash",
        defaults={"value": make_password("InitialPwd1!")},
    )
    SystemSettings.objects.update_or_create(
        key="user_create_initial_password_encrypted",
        defaults={"value": encrypt_for_vault("InitialPwd1!")},
    )

    response = _create_local_user("fixed-mode-no-channel-user")

    assert response.status_code == 400
    payload = json.loads(response.content)
    assert payload["result"] is False
    assert "邮件通道" in payload["message"]
    assert not User.objects.filter(username="fixed-mode-no-channel-user").exists()


@pytest.mark.django_db
@pytest.mark.parametrize("mode", ["fixed", "random"])
def test_create_user_blocks_when_configured_email_channel_was_deleted(mode):
    """初始化密码启用后，配置的邮件通道被删除时不能创建用户。"""
    channel = _make_email_channel()
    _set_mode(mode, email_channel_id=channel.id)
    if mode == "fixed":
        SystemSettings.objects.update_or_create(
            key="user_create_initial_password_enabled", defaults={"value": "1"}
        )
        SystemSettings.objects.update_or_create(
            key="user_create_initial_password_hash",
            defaults={"value": make_password("InitialPwd1!")},
        )
        SystemSettings.objects.update_or_create(
            key="user_create_initial_password_encrypted",
            defaults={"value": encrypt_for_vault("InitialPwd1!")},
        )
    channel.delete()

    username = f"{mode}-deleted-channel-user"
    response = _create_local_user(username)

    assert response.status_code == 400
    payload = json.loads(response.content)
    assert payload["result"] is False
    assert "邮件通道" in payload["message"]
    assert not User.objects.filter(username=username).exists()
