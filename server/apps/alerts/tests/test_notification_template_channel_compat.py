from unittest.mock import Mock

import pytest


def test_alert_notify_disables_receiver_suffix_for_custom_template(monkeypatch):
    from apps.alerts.common.notify.notify import Notify

    monkeypatch.setattr(
        "apps.alerts.common.notify.notify.SystemMgmtUtils.get_user_all",
        lambda: [{"id": 9, "username": "zhangsan", "email": "z@example.com"}],
    )
    send = Mock(return_value={"result": True})
    monkeypatch.setattr("apps.alerts.common.notify.notify.SystemMgmtUtils.send_msg_with_channel", send)

    Notify(["zhangsan"], 3, "标题", "正文", append_receivers=False).notify()

    assert send.call_args.kwargs["receivers"] == [9]
    assert send.call_args.kwargs["append_receivers"] is False


@pytest.mark.django_db
def test_system_channel_keeps_receivers_but_omits_automatic_bot_suffix(monkeypatch):
    from apps.system_mgmt.models import User
    from apps.system_mgmt.models.channel import Channel, ChannelChoices
    from apps.system_mgmt.nats.channels import send_msg_with_channel

    user = User.objects.create(username="zhangsan", display_name="张三", email="z@example.com", password="x")
    channel = Channel.objects.create(
        name="生产企微群",
        channel_type=ChannelChoices.ENTERPRISE_WECHAT_BOT,
        config={},
        description="test",
        team=[1],
    )
    send = Mock(return_value={"result": True})
    monkeypatch.setattr("apps.system_mgmt.nats.channels.send_by_wecom_bot", send)

    result = send_msg_with_channel(channel.id, "", "用户自定义正文", [user.id], append_receivers=False)

    assert result == {"result": True}
    assert send.call_args.args[1:] == ("用户自定义正文", [])
