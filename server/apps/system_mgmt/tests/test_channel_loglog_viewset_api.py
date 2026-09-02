"""ChannelViewSet 与 UserLoginLogViewSet 的 API 行为测试。

只 mock 真实外部边界（发送函数 send_*、log_operation）。
"""
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient, APIRequestFactory, force_authenticate

from apps.system_mgmt.models import Channel, UserLoginLog
from apps.system_mgmt.models.channel import ChannelChoices
from apps.system_mgmt.viewset.user_login_log_viewset import UserLoginLogViewSet

pytestmark = pytest.mark.django_db

V = "/api/v1/system_mgmt"


@pytest.fixture
def super_client(db):
    from apps.base.models import User as BaseUser

    admin = BaseUser.objects.create_user(
        username="chadmin",
        password="pw",
        domain="domain.com",
        locale="en",
        email="chadmin@x.com",
    )
    admin.is_superuser = True
    admin.save()
    # test_send 读取 request.user.display_name；base.User 无该字段，补内存属性
    admin.display_name = "Admin"
    client = APIClient()
    client.force_authenticate(user=admin)
    client.cookies["current_team"] = "1"
    return client


# ---------------------------------------------------------------------------
# Channel
# ---------------------------------------------------------------------------
def test_channel_list(super_client):
    Channel.objects.create(name="c1", channel_type=ChannelChoices.EMAIL, config={}, description="d", team=[1])
    resp = super_client.get(f"{V}/channel/")
    assert resp.status_code == 200


def test_channel_create_and_retrieve(super_client):
    with patch("apps.system_mgmt.viewset.channel_viewset.log_operation"):
        create = super_client.post(
            f"{V}/channel/",
            {"name": "newchan", "channel_type": ChannelChoices.EMAIL, "config": {}, "description": "d", "team": [1]},
            format="json",
        )
    assert create.status_code in (200, 201)
    ch = Channel.objects.get(name="newchan")
    retr = super_client.get(f"{V}/channel/{ch.id}/")
    assert retr.status_code == 200
    # CustomRenderer 包裹为 {result, code, message, data}
    assert retr.json()["data"]["name"] == "newchan"


def test_channel_update_settings(super_client):
    ch = Channel.objects.create(name="ec", channel_type=ChannelChoices.EMAIL, config={"smtp_pwd": "old"}, description="d", team=[1])
    with patch("apps.system_mgmt.viewset.channel_viewset.log_operation"):
        resp = super_client.post(
            f"{V}/channel/{ch.id}/update_settings/",
            {"config": {"smtp_host": "smtp.x.com", "smtp_pwd": "newpwd"}},
            format="json",
        )
    assert resp.json()["result"] is True
    ch.refresh_from_db()
    assert ch.config["smtp_host"] == "smtp.x.com"


def test_channel_destroy(super_client):
    ch = Channel.objects.create(name="delc", channel_type=ChannelChoices.EMAIL, config={}, description="d", team=[1])
    with patch("apps.system_mgmt.viewset.channel_viewset.log_operation"):
        resp = super_client.delete(f"{V}/channel/{ch.id}/")
    assert resp.status_code in (200, 204)
    assert not Channel.objects.filter(id=ch.id).exists()


def test_channel_test_send_email_uses_login_user_email_not_base_user_pk(super_client):
    """test_send 必须按登录身份定位 system_mgmt.User，不能用 base.User.id 当业务用户主键。

    base.User 与 system_mgmt.User 是两张表，自增 id 通常不对齐。创建用户发信走 system_mgmt.User
    能收到，而测试若误用 base id 会发到别人邮箱或空收件人。
    """
    from apps.base.models import User as BaseUser
    from apps.system_mgmt.models import User as SysUser

    login_base = BaseUser.objects.get(username="chadmin")
    # 先插入若干业务用户，拉开 system_mgmt 自增，保证真实账号主键与 base 登录用户不同
    for i in range(3):
        SysUser.objects.create(
            username=f"decoy{i}",
            display_name=f"decoy{i}",
            email=f"decoy{i}@example.com",
            password="x",
            domain="domain.com",
        )
    real = SysUser.objects.create(
        username="chadmin",
        display_name="Admin",
        email="chadmin@x.com",
        password="x",
        domain="domain.com",
    )
    assert real.id != login_base.id

    with patch("apps.system_mgmt.viewset.channel_viewset.send_email", return_value={"result": True}) as m_send:
        resp = super_client.post(
            f"{V}/channel/test_send/",
            {
                "channel_type": ChannelChoices.EMAIL,
                "name": "mail",
                "config": {
                    "smtp_server": "smtp.example.com",
                    "port": 465,
                    "smtp_user": "u",
                    "smtp_pwd": "p",
                    "mail_sender": "noreply@example.com",
                },
            },
            format="json",
        )

    assert resp.status_code == 200
    assert resp.json()["result"] is True
    user_list = m_send.call_args.args[3]
    assert list(user_list.values_list("username", flat=True)) == ["chadmin"]
    assert list(user_list.values_list("email", flat=True)) == ["chadmin@x.com"]


def test_channel_test_send_unsupported_type(super_client):
    resp = super_client.post(f"{V}/channel/test_send/", {"channel_type": "totally_unknown", "config": {}}, format="json")
    assert resp.status_code == 400


def test_channel_test_send_wecom_bot(super_client):
    with patch("apps.system_mgmt.viewset.channel_viewset.send_by_wecom_bot", return_value={"errcode": 0}) as m_send:
        resp = super_client.post(
            f"{V}/channel/test_send/",
            {"channel_type": ChannelChoices.ENTERPRISE_WECHAT_BOT, "config": {"webhook_url": "http://x"}, "name": "bot"},
            format="json",
        )
    assert resp.status_code == 200
    assert resp.json()["result"] is True
    m_send.assert_called_once()


def test_channel_test_send_wecom_bot_failure(super_client):
    with patch(
        "apps.system_mgmt.viewset.channel_viewset.send_by_wecom_bot",
        return_value={"errcode": 1, "errmsg": "boom"},
    ):
        resp = super_client.post(
            f"{V}/channel/test_send/",
            {"channel_type": ChannelChoices.ENTERPRISE_WECHAT_BOT, "config": {}, "name": "bot"},
            format="json",
        )
    assert resp.status_code == 400
    assert resp.json()["result"] is False


def test_channel_test_send_whitelist_failure_has_action_contract(super_client):
    with patch(
        "apps.system_mgmt.viewset.channel_viewset.send_by_wecom_bot",
        return_value={"result": False, "message": "webhook domain or IP not in whitelist"},
    ):
        resp = super_client.post(
            f"{V}/channel/test_send/",
            {"channel_type": ChannelChoices.ENTERPRISE_WECHAT_BOT, "config": {}, "name": "bot"},
            format="json",
        )

    body = resp.json()
    assert resp.status_code == 400
    assert body["code"] == "NETWORK_WHITELIST_REQUIRED"
    assert body["message"] == ("The target IP is not in the allowlist. Add it in System Management > Network Allowlist.")
    assert body["data"]["network_whitelist_url"] == "/system-manager/settings/network-whitelist"
    assert body["data"]["action_label"] == "Open Network Allowlist"


def test_channel_update_opspilot_managed_readonly(super_client):
    ch = Channel.objects.create(name="nats", channel_type=ChannelChoices.NATS, config={"source": "opspilot"}, description="d", team=[1])
    resp = super_client.put(
        f"{V}/channel/{ch.id}/",
        {"name": "nats", "channel_type": ChannelChoices.NATS, "config": {"source": "opspilot"}, "description": "d", "team": [1]},
        format="json",
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# UserLoginLog
# ---------------------------------------------------------------------------
def test_user_login_log_list(super_client):
    resp = super_client.get(f"{V}/user_login_log/")
    assert resp.status_code == 200


def test_user_login_log_statistics(super_client):
    # 当前组 team=1 内的用户日志会被 GroupFilterMixin 过滤；这里用户在组1
    from apps.system_mgmt.models import User as SmUser

    SmUser.objects.create(
        username="lluser",
        password="x",
        display_name="L",
        email="l@x.com",
        domain="domain.com",
        group_list=[1],
    )
    UserLoginLog.objects.create(username="lluser", domain="domain.com", source_ip="1.1.1.1", status=UserLoginLog.STATUS_SUCCESS)
    UserLoginLog.objects.create(username="lluser", domain="domain.com", source_ip="1.1.1.1", status=UserLoginLog.STATUS_FAILED)
    resp = super_client.get(f"{V}/user_login_log/statistics/")
    assert resp.status_code == 200
    data = resp.json()["data"]  # CustomRenderer 包裹
    assert data["total"] == 2
    assert data["success_count"] == 1
    assert data["failed_count"] == 1
    assert data["success_rate"] == 50.0


def test_user_login_log_export_excel(super_client):
    resp = super_client.post(f"{V}/user_login_log/export_excel/", {"selected_ids": []}, format="json")
    assert resp.status_code == 200
    assert "spreadsheetml" in resp["Content-Type"]


def test_user_login_log_export_excel_rejects_invalid_filters(super_client):
    from apps.base.models import User as BaseUser

    request = APIRequestFactory().post(
        "/user_login_log/export_excel/",
        {"login_time_start": "not-a-datetime"},
        format="json",
    )
    request.COOKIES["current_team"] = "1"
    force_authenticate(request, user=BaseUser.objects.get(username="chadmin"))

    response = UserLoginLogViewSet.as_view({"post": "export_excel"})(request)

    assert response.status_code == 400
    assert response.data["message"] == "Invalid filter parameters"
    assert list(response.data["errors"]) == ["login_time_start"]
    assert [str(error) for error in response.data["errors"]["login_time_start"]] == ["Enter a valid date/time."]
