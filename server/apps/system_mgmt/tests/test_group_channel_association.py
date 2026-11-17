import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.test import RequestFactory
from rest_framework.test import APIClient

from apps.system_mgmt.models import (
    Channel,
    ChannelChoices,
    IMAccountAssociation,
    IMNotificationSyncRun,
    IMNotificationUserMapping,
    IntegrationInstance,
    User,
)
from apps.system_mgmt.nats import channels as nats_api
from apps.system_mgmt.serializers import ChannelSerializer

pytestmark = pytest.mark.django_db


@pytest.fixture
def super_client(db):
    from apps.base.models import User as BaseUser

    admin = BaseUser.objects.create_user(
        username="group-channel-admin",
        password="pw",
        domain="domain.com",
        locale="en",
        email="group-channel-admin@example.com",
    )
    admin.is_superuser = True
    admin.save()
    client = APIClient()
    client.force_authenticate(user=admin)
    client.cookies["current_team"] = "1"
    return client


def _request(locale="en"):
    request = RequestFactory().post("/system_mgmt/channel/")
    request.user = SimpleNamespace(locale=locale)
    return request


def _instance(name, provider_key):
    return IntegrationInstance.objects.create(
        name=name,
        provider_key=provider_key,
        enabled=True,
        status="ready",
        capability_status={"im_notification": "ready"},
        config={},
    )


def _association(name, instance, *, status="ready", receive_field="user_id"):
    return IMAccountAssociation.objects.create(
        name=name,
        integration_instance=instance,
        platform_match_field="email",
        external_match_field="email",
        external_receive_field=receive_field,
        status=status,
    )


def _user(**kwargs):
    defaults = dict(
        user_id=str(uuid.uuid4()),
        username=f"user-{uuid.uuid4().hex[:8]}",
        display_name="小明",
        email="user@example.com",
        password="",
        domain="domain.com",
        disabled=False,
    )
    defaults.update(kwargs)
    return User.objects.create(**defaults)


def _mapping(association, user, receive_value):
    return IMNotificationUserMapping.objects.create(
        account_association=association,
        user=user,
        external_identity_key="user_id",
        external_identity_value=receive_value,
        external_receive_key=association.external_receive_field,
        external_snapshot={association.external_receive_field: receive_value},
    )


def _channel(channel_type, association=None):
    return Channel.objects.create(
        name=f"channel-{uuid.uuid4().hex[:8]}",
        channel_type=channel_type,
        account_association=association,
        config={"webhook_url": "https://example.com/hook"},
        description="group",
        team=[1],
    )


def _payload(channel_type, association_id=None):
    return {
        "name": f"saved-{uuid.uuid4().hex[:8]}",
        "channel_type": channel_type,
        "description": "group channel",
        "team": [1],
        "config": {"webhook_url": "https://example.com/hook"},
        "account_association": association_id,
    }


def test_serializer_accepts_association_from_the_same_platform():
    association = _association("wecom-task", _instance("wecom-inst", "wecom"))
    serializer = ChannelSerializer(data=_payload(ChannelChoices.ENTERPRISE_WECHAT_BOT, association.id), context={"request": _request()})
    assert serializer.is_valid(), serializer.errors
    saved = serializer.save()
    assert saved.account_association_id == association.id


def test_serializer_rejects_association_from_another_platform():
    association = _association("wecom-task", _instance("wecom-inst", "wecom"))
    serializer = ChannelSerializer(data=_payload(ChannelChoices.FEISHU_BOT, association.id), context={"request": _request("zh-Hans")})
    assert not serializer.is_valid()
    assert "平台不一致" in str(serializer.errors["account_association"])


def test_serializer_clears_association_for_custom_webhook():
    association = _association("wecom-task", _instance("wecom-inst", "wecom"))
    channel = _channel(ChannelChoices.ENTERPRISE_WECHAT_BOT, association)
    serializer = ChannelSerializer(
        channel,
        data=_payload(ChannelChoices.CUSTOM_WEBHOOK, association.id),
        context={"request": _request()},
    )
    assert serializer.is_valid(), serializer.errors
    saved = serializer.save()
    assert saved.account_association_id is None


def test_wecom_group_mentions_receive_id_and_skips_unusable_users():
    association = _association("wecom-task", _instance("wecom-inst", "wecom"))
    channel = _channel(ChannelChoices.ENTERPRISE_WECHAT_BOT, association)
    matched = _user(username="matched", display_name="已关联")
    disabled = _user(username="disabled-user", display_name="已禁用", disabled=True)
    conflicted = _user(username="conflicted", display_name="冲突")
    missing = _user(username="missing", display_name="未关联")
    _mapping(association, matched, "zhangsan")
    _mapping(association, disabled, "disabled-id")
    _mapping(association, conflicted, "conflict-id")
    IMNotificationSyncRun.objects.create(
        account_association=association,
        status="success",
        summary="done",
        payload={"conflict_user_ids": [conflicted.id]},
    )

    with patch("apps.system_mgmt.nats.channels.send_by_wecom_bot", return_value={"result": True}) as send:
        result = nats_api.send_msg_with_channel(channel.id, "", "hello", [matched.id, disabled.id, conflicted.id, missing.id])

    assert result == {"result": True}
    assert send.call_args.args[1] == "hello\n<@zhangsan>"
    assert "已关联" not in send.call_args.args[1]
    assert send.call_args.args[2] == []


def test_group_message_still_sends_when_association_is_not_ready():
    association = _association("wecom-task", _instance("wecom-inst", "wecom"), status="needs_resync")
    channel = _channel(ChannelChoices.ENTERPRISE_WECHAT_BOT, association)
    user = _user()
    _mapping(association, user, "zhangsan")

    with patch("apps.system_mgmt.nats.channels.send_by_wecom_bot", return_value={"result": True}) as send:
        result = nats_api.send_msg_with_channel(channel.id, "", "hello", [user.id])

    assert result == {"result": True}
    assert send.call_args.args[1] == "hello"
    assert send.call_args.args[2] == []


def test_feishu_group_uses_at_tag():
    association = _association("feishu-task", _instance("feishu-inst", "feishu"), receive_field="open_id")
    channel = _channel(ChannelChoices.FEISHU_BOT, association)
    user = _user()
    _mapping(association, user, "ou_abc")

    with patch("apps.system_mgmt.nats.channels.send_by_feishu_bot", return_value={"result": True}) as send:
        nats_api.send_msg_with_channel(channel.id, "title", "hello", [user.id])

    assert send.call_args.args[2] == 'hello\n<at id="ou_abc"></at>'
    assert send.call_args.args[3] == []


def test_dingtalk_group_passes_at_user_ids():
    association = _association("ding-task", _instance("ding-inst", "dingtalk"))
    channel = _channel(ChannelChoices.DINGTALK_BOT, association)
    user = _user()
    _mapping(association, user, "staff-1")

    with patch("apps.system_mgmt.nats.channels.send_by_dingtalk_bot", return_value={"result": True}) as send:
        nats_api.send_msg_with_channel(channel.id, "title", "hello", [user.id])

    assert send.call_args.args[2] == "hello"
    assert send.call_args.args[3] == []
    assert send.call_args.kwargs["at_user_ids"] == ["staff-1"]
    assert send.call_args.kwargs["at_mobiles"] == []


def test_account_association_options_filter_by_platform(super_client):
    wecom = _association("wecom-task", _instance("wecom-inst", "wecom"))
    _association("feishu-task", _instance("feishu-inst", "feishu"))

    response = super_client.get("/api/v1/system_mgmt/channel/account_association_options/", {"channel_type": "enterprise_wechat_bot"})

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["data"]] == [wecom.id]


def test_account_association_options_hide_non_group_channels(super_client):
    _association("wecom-task", _instance("wecom-inst", "wecom"))
    response = super_client.get("/api/v1/system_mgmt/channel/account_association_options/", {"channel_type": "custom_webhook"})
    assert response.status_code == 200
    assert response.json()["data"] == []


def _login_user():
    return _user(username="group-channel-admin", display_name="蓝羽", domain="domain.com")


def _test_send(super_client, channel_type, association_id):
    return super_client.post(
        "/api/v1/system_mgmt/channel/test_send/",
        {
            "channel_type": channel_type,
            "name": "飞书",
            "config": {"webhook_url": "https://example.com/hook"},
            "account_association": association_id,
        },
        format="json",
    )


def test_group_test_send_mentions_current_user_from_association(super_client):
    user = _login_user()
    association = _association("feishu-task", _instance("feishu-inst", "feishu"), receive_field="open_id")
    _mapping(association, user, "ou_lanyu")

    with patch("apps.system_mgmt.viewset.channel_viewset.send_by_feishu_bot", return_value={"code": 0}) as send:
        response = _test_send(super_client, ChannelChoices.FEISHU_BOT, association.id)

    assert response.status_code == 200
    content = send.call_args.args[2]
    assert '<at id="ou_lanyu"></at>' in content
    assert "To:" not in content
    assert send.call_args.args[3] == []


def test_group_test_send_passes_dingtalk_at_ids(super_client):
    user = _login_user()
    association = _association("ding-task", _instance("ding-inst", "dingtalk"))
    _mapping(association, user, "staff-1")

    with patch("apps.system_mgmt.viewset.channel_viewset.send_by_dingtalk_bot", return_value={"errcode": 0}) as send:
        response = _test_send(super_client, ChannelChoices.DINGTALK_BOT, association.id)

    assert response.status_code == 200
    assert send.call_args.args[3] == []
    assert send.call_args.kwargs["at_user_ids"] == ["staff-1"]
    assert send.call_args.kwargs["at_mobiles"] == []


def test_group_test_send_rejects_current_user_without_receive_id(super_client):
    _login_user()
    association = _association("feishu-task", _instance("feishu-inst", "feishu"), receive_field="open_id")

    with patch("apps.system_mgmt.viewset.channel_viewset.send_by_feishu_bot") as send:
        response = _test_send(super_client, ChannelChoices.FEISHU_BOT, association.id)

    assert response.status_code == 400
    assert "no usable receive identifier" in response.json()["message"]
    send.assert_not_called()


def test_group_test_send_rejects_association_that_is_not_ready(super_client):
    user = _login_user()
    association = _association("feishu-task", _instance("feishu-inst", "feishu"), status="needs_resync", receive_field="open_id")
    _mapping(association, user, "ou_lanyu")

    with patch("apps.system_mgmt.viewset.channel_viewset.send_by_feishu_bot") as send:
        response = _test_send(super_client, ChannelChoices.FEISHU_BOT, association.id)

    assert response.status_code == 400
    assert "cannot be used" in response.json()["message"]
    send.assert_not_called()


def test_group_test_send_rejects_association_from_another_platform(super_client):
    _login_user()
    association = _association("wecom-task", _instance("wecom-inst", "wecom"))

    response = _test_send(super_client, ChannelChoices.FEISHU_BOT, association.id)

    assert response.status_code == 400
    assert "does not belong" in response.json()["message"]
