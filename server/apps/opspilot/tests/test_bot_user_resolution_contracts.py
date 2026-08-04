"""Bot 渠道用户解析的公共契约：外部通讯录被替换，本地映射逻辑真实执行。"""

from types import SimpleNamespace

import pytest

from apps.opspilot.enum import ChannelChoices
from apps.opspilot.utils import bot_utils


pytestmark = pytest.mark.unit


@pytest.fixture
def local_models(mocker):
    user = SimpleNamespace(id=31)
    channel_user = mocker.patch.object(bot_utils.ChannelUser.objects, "get_or_create")
    update_user = mocker.patch.object(
        bot_utils.ChannelUser.objects, "update_or_create"
    )
    channel_user.return_value = (user, True)
    update_user.return_value = (user, False)
    delete = mocker.Mock()
    mocker.patch.object(
        bot_utils.UserGroup.objects,
        "filter",
        return_value=SimpleNamespace(delete=delete),
    )
    bulk_create = mocker.patch.object(bot_utils.UserGroup.objects, "bulk_create")
    group = SimpleNamespace(id=41)
    update_group = mocker.patch.object(
        bot_utils.ChannelGroup.objects, "update_or_create", return_value=(group, True)
    )
    return SimpleNamespace(
        user=user,
        get_or_create=channel_user,
        update_or_create=update_user,
        delete=delete,
        bulk_create=bulk_create,
        update_group=update_group,
    )


def test_web_sender_uses_stable_id_without_external_lookup(local_models):
    user, groups = bot_utils.get_user_info(7, "web", "sender-1")

    assert user is local_models.user
    assert groups == []
    local_models.get_or_create.assert_called_once_with(
        user_id="sender-1",
        channel_type=ChannelChoices.WEB,
        defaults={"name": "sender-1"},
    )
    local_models.delete.assert_called_once()
    local_models.bulk_create.assert_called_once_with([], batch_size=100)


def test_enterprise_wechat_resolves_name_and_persists_unique_groups(
    mocker, local_models
):
    config = {
        "channels.enterprise_wechat_channel.EnterpriseWechatChannel": {
            "corp_id": "corp",
            "secret": "secret",
        }
    }
    mocker.patch.object(
        bot_utils.BotChannel.objects,
        "get",
        return_value=SimpleNamespace(decrypted_channel_config=config),
    )
    client = SimpleNamespace(
        user=SimpleNamespace(
            get=lambda sender: {
                "name": f"name-{sender}",
                "department": [10, 20],
            }
        )
    )
    wechat_client = mocker.patch.object(
        bot_utils, "WeChatClient", return_value=client
    )
    mocker.patch.object(
        bot_utils,
        "get_enterprise_wechat_user_groups",
        return_value=[
            {"id": 10, "name": "Platform"},
            {"id": 20, "name": "SRE"},
        ],
    )

    user, groups = bot_utils.get_user_info(
        7, "enterprise_wechat", "sender-1"
    )

    assert user is local_models.user
    assert groups == [
        {"id": 10, "name": "Platform"},
        {"id": 20, "name": "SRE"},
    ]
    wechat_client.assert_called_once_with("corp", "secret")
    local_models.update_or_create.assert_called_once_with(
        user_id="sender-1",
        channel_type=ChannelChoices.ENTERPRISE_WECHAT,
        defaults={"name": "name-sender-1"},
    )
    assert local_models.update_group.call_count == 2
    created = local_models.bulk_create.call_args.args[0]
    assert [(item.user_id, item.group_id) for item in created] == [
        (31, 41),
        (31, 41),
    ]


def test_dingtalk_directory_failure_falls_back_to_sender_and_closes_client(
    mocker, local_models
):
    config = {
        "channels.dingtalk_channel.DingTalkChannel": {
            "client_id": "client",
            "client_secret": "secret",
        }
    }
    mocker.patch.object(
        bot_utils.BotChannel.objects,
        "get",
        return_value=SimpleNamespace(decrypted_channel_config=config),
    )
    client = mocker.Mock()
    client.get_user_info.side_effect = RuntimeError("directory offline")
    dingtalk = mocker.patch.object(
        bot_utils, "DingTalkClient", return_value=client
    )

    user, groups = bot_utils.get_user_info(7, "dingtalk", "sender-1")

    assert user is local_models.user
    assert groups == []
    dingtalk.assert_called_once_with("client", "secret")
    client.close.assert_called_once()
    local_models.get_or_create.assert_called_once_with(
        user_id="sender-1",
        channel_type=ChannelChoices.DING_TALK,
        defaults={"name": "sender-1"},
    )


def test_official_account_prefers_nickname_then_updates_local_user(
    mocker, local_models
):
    config = {
        "channels.wechat_official_account_channel.WechatOfficialAccountChannel": {
            "appid": "app",
            "secret": "secret",
        }
    }
    mocker.patch.object(
        bot_utils.BotChannel.objects,
        "get",
        return_value=SimpleNamespace(decrypted_channel_config=config),
    )
    client = SimpleNamespace(
        user=SimpleNamespace(
            get=lambda _sender: {"nickname": "Alice", "remark": "On call"}
        )
    )
    account_client = mocker.patch.object(
        bot_utils, "WeChatAccountClient", return_value=client
    )

    user, groups = bot_utils.get_user_info(
        7, "wechat_official_account", "openid-1"
    )

    assert user is local_models.user
    assert groups == []
    account_client.assert_called_once_with("app", "secret")
    local_models.update_or_create.assert_called_once_with(
        user_id="openid-1",
        channel_type=ChannelChoices.WECHAT_OFFICIAL_ACCOUNT,
        defaults={"name": "Alice"},
    )
