"""ChannelViewSet 与 UserLoginLogViewSet 的 API 行为测试。

只 mock 真实外部边界（发送函数 send_*、log_operation）。
"""
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from apps.system_mgmt.models import Channel, UserLoginLog
from apps.system_mgmt.models.channel import ChannelChoices

pytestmark = pytest.mark.django_db

V = "/api/v1/system_mgmt"


@pytest.fixture
def super_client(db):
    from apps.base.models import User as BaseUser

    admin = BaseUser.objects.create_user(
        username="chadmin", password="pw", domain="domain.com", locale="en",
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
    ch = Channel.objects.create(
        name="ec", channel_type=ChannelChoices.EMAIL, config={"smtp_pwd": "old"}, description="d", team=[1]
    )
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


def test_channel_test_send_unsupported_type(super_client):
    resp = super_client.post(
        f"{V}/channel/test_send/", {"channel_type": "totally_unknown", "config": {}}, format="json"
    )
    assert resp.status_code == 400


def test_channel_test_send_wecom_bot(super_client):
    with patch(
        "apps.system_mgmt.viewset.channel_viewset.send_by_wecom_bot", return_value={"errcode": 0}
    ) as m_send:
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


def test_channel_update_opspilot_managed_readonly(super_client):
    ch = Channel.objects.create(
        name="nats", channel_type=ChannelChoices.NATS, config={"source": "opspilot"}, description="d", team=[1]
    )
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
        username="lluser", password="x", display_name="L", email="l@x.com",
        domain="domain.com", group_list=[1],
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
