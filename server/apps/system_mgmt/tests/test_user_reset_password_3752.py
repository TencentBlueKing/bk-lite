"""
Issue #3752: 修改用户密码时密码强度不够,接口返回 500 + 英文兜底
("System error, please contact administrator") 而不是 400 + 中文校验消息。

修复验证：reset_password 接口在密码不满足策略时,必须返回 HTTP 400 + DRF `detail` 字段携带
PasswordValidator 的中文错误消息（"密码不能为空" / "密码长度不能少于 X 个字符" 等）,
而不是 ValueError 冒到全局 500 兜底。

测试风格：参考 test_create_user_password_3466.py 的裸模式
(APIRequestFactory + force_authenticate + as_view({"post": "reset_password"})),
避开 app_exception_middleware, 直接断言 DRF 层的 status_code 与 detail 文本。
"""

import json
import types
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth.hashers import check_password, make_password
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.system_mgmt.models import Group, User
from apps.system_mgmt.nats.login import reset_pwd
from apps.system_mgmt.services.password_init_service import PASSWORD_INIT_SENTINEL_MARK
from apps.system_mgmt.viewset.user_viewset import UserViewSet


def _admin_user(**overrides):
    defaults = {
        "username": "test-admin-3752",
        "domain": "domain.com",
        "locale": "en",
        "is_superuser": True,
        "is_authenticated": True,
        # reset_password 要求 "user_group-Edit User" 权限
        "permission": {"system-manager": {"user_group-Edit User"}},
    }
    defaults.update(overrides)
    return types.SimpleNamespace(**defaults)


def _make_target_user(username: str = "victim-3752") -> User:
    """构造一个非空密码的目标用户, 用于 reset_password 修改。"""
    from django.contrib.auth.hashers import make_password

    return User.objects.create(
        username=username,
        display_name="Victim",
        email=f"{username}@example.com",
        phone=None,
        locale="en",
        timezone="Asia/Shanghai",
        group_list=[],
        role_list=[],
        password=make_password("Oldpass1!"),
    )


def _post_reset_password(password, user_id):
    """裸模式调 reset_password action, 返回 (response, payload_dict)。

    成功/失败路径均返回 Django JsonResponse({result, message}), 直接 .content 读 body。
    """
    factory = APIRequestFactory()
    view = UserViewSet.as_view({"post": "reset_password"})

    request = factory.post(
        "/system_mgmt/api/user/reset_password/",
        {"id": user_id, "password": password, "temporary": False},
        format="json",
    )
    force_authenticate(request, user=_admin_user())

    response = view(request)
    payload = json.loads(response.content.decode("utf-8"))
    return response, payload


@pytest.mark.django_db
def test_reset_password_weak_password_returns_400_with_chinese_message():
    """
    Issue #3752 主场景：密码过短(弱密码)时, 必须返回 400 + 中文消息,
    而不是 500 + "System error, please contact administrator"。
    """
    target = _make_target_user()

    response, payload = _post_reset_password(password="123", user_id=target.id)

    assert response.status_code == 400, (
        f"弱密码应返回 400, 实际 {response.status_code}: {payload}"
    )
    assert payload.get("result") is False, f"响应 result 应为 False: {payload}"
    assert "密码长度不能少于" in payload.get("message", ""), (
        f"message 应含中文长度提示, 实际: {payload.get('message')!r}"
    )


@pytest.mark.django_db
def test_reset_password_missing_special_char_returns_400():
    """密码缺少必需字符类型(默认策略要求大写+小写+数字+特殊符号), 返回 400 + 中文。"""
    target = _make_target_user("victim-missing-special")

    response, payload = _post_reset_password(password="Abcd1234", user_id=target.id)

    assert response.status_code == 400, (
        f"缺特殊符号应返回 400, 实际 {response.status_code}: {payload}"
    )
    assert payload.get("result") is False
    assert "密码必须包含" in payload.get("message", ""), (
        f"message 应含\"密码必须包含\"提示, 实际: {payload.get('message')!r}"
    )
    assert "特殊符号" in payload.get("message", ""), (
        f"message 应点出缺失的字符类型, 实际: {payload.get('message')!r}"
    )


@pytest.mark.django_db
def test_reset_password_empty_password_returns_400():
    """空密码应返回 400 + "密码不能为空"。"""
    target = _make_target_user("victim-empty")

    response, payload = _post_reset_password(password="", user_id=target.id)

    assert response.status_code == 400, (
        f"空密码应返回 400, 实际 {response.status_code}: {payload}"
    )
    assert payload.get("result") is False
    assert payload.get("message") == "密码不能为空", (
        f"message 应严格等于\"密码不能为空\", 实际: {payload.get('message')!r}"
    )


@pytest.mark.django_db
def test_reset_password_non_ascii_password_returns_400():
    """非 ASCII 字符的密码应返回 400 + "非法字符" 提示。

    密码必须满足长度 + 字符类型要求, 只在"含非 ASCII"这一关触发, 否则会被前面的
    字符类型校验先拦下, 测不到目标分支。
    """
    target = _make_target_user("victim-nonascii")

    # 长度 10, 含大写/小写/数字/特殊/非 ASCII —— 字符类型全齐, 只被非 ASCII 校验拦下
    response, payload = _post_reset_password(password="ABcd1234!密码", user_id=target.id)

    assert response.status_code == 400, (
        f"非 ASCII 密码应返回 400, 实际 {response.status_code}: {payload}"
    )
    assert payload.get("result") is False
    assert "非法字符" in payload.get("message", "") or "ASCII" in payload.get("message", ""), (
        f"message 应点出非法字符/ASCII 限制, 实际: {payload.get('message')!r}"
    )


@pytest.mark.django_db
def test_reset_password_strong_password_succeeds():
    """
    回归保护：合法密码必须 200 + {"result": True}, 避免 fix 误伤正常路径。
    并验证 user.password 已被 make_password 重哈希(不等于明文)。
    """
    target = _make_target_user("victim-ok")
    new_password = "StrongPwd1!"

    response, payload = _post_reset_password(password=new_password, user_id=target.id)

    assert response.status_code == 200, (
        f"合法密码应返回 200, 实际 {response.status_code}: {payload}"
    )
    assert payload == {"result": True}, (
        f"合法密码响应体应为 {{'result': True}}, 实际: {payload}"
    )

    target.refresh_from_db()
    assert target.password != new_password, "password 字段应被 make_password 哈希, 不得明文存储"
    assert check_password(new_password, target.password), "新密码哈希应通过 check_password 验证"


@pytest.fixture
def sentinel_group(db):
    return Group.objects.create(name="sentinel-root", parent_id=0)


def _make_reset_caller(username: str):
    caller = MagicMock()
    caller.username = username
    caller.domain = "domain.com"
    return caller


@pytest.mark.django_db
@pytest.mark.parametrize(
    "stored_password",
    [PASSWORD_INIT_SENTINEL_MARK, "!UNSET_PASSWORD:some-other-value"],
)
def test_nats_reset_password_rejects_sentinel_password(sentinel_group, stored_password):
    user = User.objects.create(
        username=f"sentinel-{stored_password[-1]}",
        display_name="Sentinel",
        email="sentinel@example.com",
        password=stored_password,
        domain="domain.com",
        disabled=False,
        group_list=[sentinel_group.id],
    )

    with patch("apps.system_mgmt.nats.login._verify_token", return_value=_make_reset_caller(user.username)):
        result = reset_pwd(user.username, user.domain, "NewP@ssw0rd!", caller_token="any-token")

    assert result["result"] is False
    assert "未设置本地密码" in result["message"]
    user.refresh_from_db()
    assert user.password == stored_password


@pytest.mark.django_db
def test_nats_reset_password_allows_normal_password(sentinel_group):
    user = User.objects.create(
        username="normal-user",
        display_name="Normal",
        email="normal@example.com",
        password=make_password("OldP@ssw0rd!"),
        domain="domain.com",
        disabled=False,
        group_list=[sentinel_group.id],
    )

    with patch("apps.system_mgmt.nats.login._verify_token", return_value=_make_reset_caller(user.username)):
        result = reset_pwd(user.username, user.domain, "NewP@ssw0rd!", caller_token="any-token")

    assert result["result"] is True
    user.refresh_from_db()
    assert check_password("NewP@ssw0rd!", user.password)
    assert user.temporary_pwd is False
