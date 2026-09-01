"""system_mgmt.nats_api：登录成功/OTP/改密/通道发送/规则删除。

对照鉴权契约：密码正确签发 JWT；OTP 开启时只发 challenge；禁用账号拒绝；
caller_token 必须匹配目标用户；未知通道拒绝发送。
"""
from datetime import timedelta
from unittest.mock import patch

import jwt
import pyotp
import pytest
from django.contrib.auth.hashers import make_password
from django.utils import timezone

from apps.system_mgmt import nats_api
from apps.system_mgmt.models import Channel, Group, GroupDataRule, Role, SystemSettings, User, UserRule
from apps.system_mgmt.models.channel import ChannelChoices

pytestmark = pytest.mark.django_db


def _user(**kwargs):
    defaults = dict(
        username="login-user",
        display_name="登录用户",
        email="login-user@example.com",
        password=make_password("secret-pass"),
        domain="domain.com",
        group_list=[1],
        disabled=False,
        otp_secret="",
    )
    defaults.update(kwargs)
    return User.objects.create(**defaults)


def test_login_success_issues_jwt(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("JWT_ALGORITHM", "HS256")
    user = _user(username="ok-user", password_last_modified=timezone.now())
    monkeypatch.setattr(
        nats_api,
        "_get_pwd_policy_settings",
        lambda: {
            "pwd_set_validity_period": 0,
            "pwd_set_expiry_reminder_days": 7,
            "pwd_set_max_retry_count": 5,
            "pwd_set_lock_duration": 60,
        },
    )
    result = nats_api.login("ok-user", "secret-pass")
    assert result["result"] is True
    token = result["data"]["token"]
    payload = jwt.decode(token, "test-secret", algorithms=["HS256"])
    assert payload["user_id"] == user.id
    assert result["data"]["username"] == "ok-user"
    assert result["data"]["password_expiry_reminder"] == ""
    user.refresh_from_db()
    assert user.password_error_count == 0
    assert user.last_login is not None


def test_login_rejects_disabled_user(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    _user(username="off-user", disabled=True)
    result = nats_api.login("off-user", "secret-pass")
    assert result == {"result": False, "message": "User is disabled"}


def test_login_expired_password_blocks_non_admin(monkeypatch):
    _user(username="expired-user", password_last_modified=timezone.now() - timedelta(days=400))
    monkeypatch.setattr(
        nats_api,
        "_get_pwd_policy_settings",
        lambda: {
            "pwd_set_validity_period": 90,
            "pwd_set_expiry_reminder_days": 7,
            "pwd_set_max_retry_count": 5,
            "pwd_set_lock_duration": 60,
        },
    )
    result = nats_api.login("expired-user", "secret-pass")
    assert result == {
        "result": False,
        "message": "您的密码已过期,请联系管理员重置密码。",
    }


def test_login_otp_enabled_returns_challenge_not_token(monkeypatch):
    user = _user(username="otp-user", otp_secret=pyotp.random_base32())
    SystemSettings.objects.update_or_create(key="enable_otp", defaults={"value": "1"})
    monkeypatch.setattr(
        nats_api,
        "_get_pwd_policy_settings",
        lambda: {
            "pwd_set_validity_period": 0,
            "pwd_set_expiry_reminder_days": 7,
            "pwd_set_max_retry_count": 5,
            "pwd_set_lock_duration": 60,
        },
    )
    result = nats_api.login("otp-user", "secret-pass")
    assert result["result"] is True
    assert result["data"]["require_otp"] is True
    assert result["data"]["challenge_id"]
    assert "token" not in result["data"]
    user.refresh_from_db()
    assert user.otp_secret


def test_verify_otp_code_success_and_invalid():
    secret = pyotp.random_base32()
    _user(username="otp-check", otp_secret=secret)
    with patch("apps.system_mgmt.nats_api.check_rate_limit", return_value=(False, 5)):
        ok = nats_api.verify_otp_code("otp-check", pyotp.TOTP(secret).now(), client_ip="1.1.1.1")
        bad = nats_api.verify_otp_code("otp-check", "000000", client_ip="1.1.1.1")
    assert ok == {"result": True, "message": "Verification successful"}
    assert bad["result"] is False
    assert "Invalid OTP" in bad["message"]

    missing = nats_api.verify_otp_code_by_user_id(999999, "123456")
    assert missing["result"] is False


def test_verify_otp_login_expired_challenge():
    with patch("apps.system_mgmt.nats_api.verify_challenge", return_value=None):
        result = nats_api.verify_otp_login("gone", "123456")
    assert result["result"] is False
    assert "challenge" in result["message"].lower()


def test_get_user_login_token_first_bind_includes_qr(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    user = _user(username="bind-user", otp_secret="")
    SystemSettings.objects.update_or_create(key="enable_otp", defaults={"value": "1"})
    result = nats_api.get_user_login_token(user, "bind-user", skip_token_for_otp=True)
    assert result["result"] is True
    assert result["data"]["need_binding"] is True
    assert result["data"]["qr_code"]
    user.refresh_from_db()
    assert user.otp_secret


def test_reset_pwd_requires_matching_caller(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("JWT_ALGORITHM", "HS256")
    user = _user(username="self-user")
    missing = nats_api.reset_pwd("self-user", "domain.com", "Newpass1!")
    assert missing["result"] is False
    assert "caller_token" in missing["message"]

    other = _user(username="other-user")
    token = jwt.encode({"user_id": other.id, "login_time": timezone.now().timestamp()}, "test-secret", algorithm="HS256")
    mismatch = nats_api.reset_pwd("self-user", "domain.com", "Newpass1!", caller_token=token)
    assert mismatch["result"] is False
    assert "Unauthorized" in mismatch["message"]

    self_token = jwt.encode(
        {"user_id": user.id, "user_id_str": str(user.id), "login_time": timezone.now().timestamp()},
        "test-secret",
        algorithm="HS256",
    )
    with (
        patch.object(nats_api, "_verify_token", return_value=user),
        patch("apps.system_mgmt.nats_api.PasswordValidator.validate_password", return_value=(True, "")),
    ):
        ok = nats_api.reset_pwd("self-user", "domain.com", "Newpass1!", caller_token=self_token)
    assert ok == {"result": True}


def test_send_msg_with_channel_missing_and_unsupported():
    missing = nats_api.send_msg_with_channel(999999, "t", "c", [1])
    assert missing == {"result": False, "message": "Channel not found"}

    channel = Channel.objects.create(
        name="wechat",
        channel_type=ChannelChoices.ENTERPRISE_WECHAT,
        config={},
        description="",
        team=[1],
    )
    unsupported = nats_api.send_msg_with_channel(channel.id, "t", "c", [1])
    assert unsupported == {"result": False, "message": "Unsupported channel type"}


def test_send_msg_email_requires_recipients_and_delegates():
    channel = Channel.objects.create(
        name="mail",
        channel_type=ChannelChoices.EMAIL,
        config={"host": "smtp"},
        description="",
        team=[1],
    )
    empty = nats_api.send_msg_with_channel(channel.id, "t", "c", [])
    assert empty["result"] is False
    assert "recipient" in empty["message"].lower()

    user = _user(username="mail-user")
    with patch("apps.system_mgmt.nats.channels.send_email", return_value={"result": True}) as send:
        ok = nats_api.send_msg_with_channel(channel.id, "Hello", "body", [user.id])
    assert ok == {"result": True}
    send.assert_called_once()


def test_send_msg_wecom_bot_uses_display_names():
    channel = Channel.objects.create(
        name="bot",
        channel_type=ChannelChoices.ENTERPRISE_WECHAT_BOT,
        config={"webhook": "http://x"},
        description="",
        team=[1],
    )
    user = _user(username="bot-user", display_name="小明")
    with patch("apps.system_mgmt.nats.channels.send_by_wecom_bot", return_value={"result": True}) as send:
        ok = nats_api.send_msg_with_channel(channel.id, "", "hi", [user.id])
    assert ok == {"result": True}
    assert "小明" in send.call_args.args[2]


def test_delete_rules_removes_instance_and_skips_missing_module():
    group = Group.objects.create(name="rule-g", parent_id=0)
    rule = GroupDataRule.objects.create(
        name="r1",
        app="opspilot",
        group_id=group.id,
        group_name=group.name,
        rules={"bot": [{"id": 11}, {"id": 22}], "skill": [{"id": 3}]},
    )
    skipped = GroupDataRule.objects.create(
        name="r2",
        app="opspilot",
        group_id=group.id,
        group_name=group.name,
        rules={"other": [{"id": 11}]},
    )
    result = nats_api.delete_rules([group.id], 11, "opspilot", "bot", "")
    assert result["result"] is True
    rule.refresh_from_db()
    assert [item["id"] for item in rule.rules["bot"]] == [22]
    skipped.refresh_from_db()
    assert skipped.rules["other"] == [{"id": 11}]


def test_get_user_rules_by_app_admin_and_instance_scope():
    group = Group.objects.create(name="team-a", parent_id=0)
    admin_role, _ = Role.objects.get_or_create(name="admin", app="")
    admin = _user(username="rules-admin", role_list=[admin_role.id], group_list=[group.id])
    admin_result = nats_api.get_user_rules_by_app(group.id, admin.username, "domain.com", "opspilot", "bot")
    assert admin_result["instance"] == []
    assert group.id in admin_result["team"]

    normal = _user(username="rules-user", group_list=[group.id], role_list=[])
    gdr = GroupDataRule.objects.create(
        name="bot-rule",
        app="opspilot",
        group_id=group.id,
        group_name=group.name,
        rules={"bot": [{"id": 88, "permission": ["View"]}]},
    )
    UserRule.objects.create(username=normal.username, domain="domain.com", group_rule=gdr)
    scoped = nats_api.get_user_rules_by_app(group.id, normal.username, "domain.com", "opspilot", "bot")
    assert [item["id"] for item in scoped["instance"]] == [88]


def test_get_login_module_domain_list_always_includes_default():
    result = nats_api.get_login_module_domain_list()
    assert result["result"] is True
    assert result["data"][0] == "domain.com"


def test_wechat_user_register_issues_token_and_guest_group(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("JWT_ALGORITHM", "HS256")
    guest = Group.objects.create(name="OpsPilotGuest", parent_id=0)
    with patch("apps.system_mgmt.nats_api.set_opspilot_guest_group_default_rule"):
        first = nats_api.wechat_user_register("wx-user-1", "微信用户")
    assert first["result"] is True
    assert first["data"]["is_first_login"] is True
    assert first["data"]["username"] == "wx-user-1"
    assert first["data"]["token"]
    user = User.objects.get(username="wx-user-1")
    assert guest.id in user.group_list
    assert user.last_login is not None

    with patch("apps.system_mgmt.nats_api.set_opspilot_guest_group_default_rule"):
        again = nats_api.wechat_user_register("wx-user-1", "新昵称忽略")
    assert again["data"]["is_first_login"] is False
    assert again["data"]["id"] == first["data"]["id"]


def test_get_user_rules_by_module_user_not_found():
    result = nats_api.get_user_rules_by_module(1, "ghost", "domain.com", "opspilot", "bot")
    assert result == {"result": False, "message": "User not found"}


def test_get_user_rules_by_module_admin_gets_all_permission():
    group = Group.objects.create(name="mod-admin-g", parent_id=0)
    admin_role, _ = Role.objects.get_or_create(name="admin", app="")
    admin = _user(username="mod-admin", role_list=[admin_role.id], group_list=[group.id])
    result = nats_api.get_user_rules_by_module(group.id, admin.username, "domain.com", "opspilot", "bot")
    assert result["result"] is True
    assert result["data"] == {"all": {"instance": [], "team": [group.id]}}
    assert group.id in result["team"]


def test_get_user_rules_by_module_nested_and_flat_rules():
    group = Group.objects.create(name="mod-user-g", parent_id=0)
    user = _user(username="mod-user", group_list=[group.id], role_list=[])
    gdr = GroupDataRule.objects.create(
        name="mod-rule",
        app="opspilot",
        group_id=group.id,
        group_name=group.name,
        rules={
            "provider": {"llm_model": [{"id": 7, "permission": ["View"]}]},
            "bot": [{"id": 88, "permission": ["View"]}],
        },
    )
    UserRule.objects.create(username=user.username, domain="domain.com", group_rule=gdr)
    nested = nats_api.get_user_rules_by_module(group.id, user.username, "domain.com", "opspilot", "provider")
    assert nested["result"] is True
    assert 7 in [item["id"] if isinstance(item, dict) else item for item in nested["data"]["llm_model"]["instance"]]


def test_get_user_rules_by_module_empty_rules_returns_empty_data():
    group = Group.objects.create(name="mod-empty-g", parent_id=0)
    user = _user(username="mod-empty", group_list=[group.id], role_list=[])
    result = nats_api.get_user_rules_by_module(group.id, user.username, "domain.com", "opspilot", "bot")
    assert result["result"] is True
    assert result["data"] == {}


def test_send_msg_unknown_channel_and_unsupported_type():
    assert nats_api.send_msg_with_channel(999999, "t", "c", [1]) == {"result": False, "message": "Channel not found"}
    channel = Channel.objects.create(name="weird", channel_type="unknown-type", config={}, description="", team=[1])
    out = nats_api.send_msg_with_channel(channel.id, "t", "c", [1])
    assert out == {"result": False, "message": "Unsupported channel type"}


def test_send_msg_email_requires_recipients():
    channel = Channel.objects.create(
        name="mail",
        channel_type=ChannelChoices.EMAIL,
        config={"smtp_host": "localhost"},
        description="",
        team=[1],
    )
    out = nats_api.send_msg_with_channel(channel.id, "t", "c", [999999])
    assert out["result"] is False
    assert "No valid recipients" in out["message"]


def test_search_opspilot_nats_channels_filters_source():
    Channel.objects.create(
        name="owned",
        channel_type=ChannelChoices.NATS,
        config={"source": nats_api.OPSPILOT_CHANNEL_SOURCE, "bot_id": "11", "node_id": "n1"},
        description="d",
        team=[1],
    )
    Channel.objects.create(
        name="other",
        channel_type=ChannelChoices.NATS,
        config={"source": "manual", "bot_id": "11"},
        description="",
        team=[1],
    )
    result = nats_api.search_opspilot_nats_channels(bot_id=11)
    assert result["result"] is True
    names = [item["name"] for item in result["data"]]
    assert names == ["owned"]
    assert result["data"][0]["node_id"] == "n1"
