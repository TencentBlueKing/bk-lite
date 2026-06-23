"""opspilot-biz 切片: models/bot_mgmt 真实 DB 行为测试。

覆盖：
- Bot.save 自动生成 instance_id；get_api_token 生成 64 位 hex
- BotChannel 加解密 / format_channel_config 掩码
- ChannelUser.to_dict（含 display）
- ChatApplication._extract_app_params / to_dict / sync_applications_from_workflow
  （真实 update_or_create / 删除副作用）
- WorkFlowConversationHistory.display_fields
"""

import pytest

from apps.opspilot.enum import BotTypeChoice, ChannelChoices
from apps.opspilot.models.bot_mgmt import (
    Bot,
    BotChannel,
    BotWorkFlow,
    ChannelUser,
    ChatApplication,
    WorkFlowConversationHistory,
    generate_workflow_attachment_download_token,
)

pytestmark = pytest.mark.django_db

DING_KEY = "channels.dingtalk_channel.DingTalkChannel"


def _make_bot(**kwargs):
    defaults = dict(name="bot", team=[1], usage_team=[1], online=True)
    defaults.update(kwargs)
    return Bot.objects.create(**defaults)


class TestBot:
    def test_save_自动生成instance_id(self):
        bot = _make_bot(instance_id=None)
        assert bot.instance_id
        assert len(bot.instance_id) == 36  # uuid4 字符串

    def test_save_保留已有instance_id(self):
        bot = _make_bot(instance_id="fixed-id-123")
        bot.refresh_from_db()
        assert bot.instance_id == "fixed-id-123"

    def test_get_api_token_64位hex(self):
        token = Bot.get_api_token()
        assert len(token) == 64
        int(token, 16)  # 必须是合法 hex，否则抛错
        # 两次生成不同
        assert token != Bot.get_api_token()

    def test_str返回name(self):
        assert str(_make_bot(name="my-bot")) == "my-bot"


class TestBotChannelEncryption:
    def test_保存加密并可解密(self):
        bot = _make_bot()
        bc = BotChannel.objects.create(
            bot=bot,
            name="ding",
            channel_type=ChannelChoices.DING_TALK,
            channel_config={DING_KEY: {"client_id": "c", "client_secret": "sekret"}},
        )
        bc.refresh_from_db()
        assert bc.channel_config[DING_KEY]["client_secret"] != "sekret"
        assert bc.decrypted_channel_config[DING_KEY]["client_secret"] == "sekret"

    def test_空配置直接保存(self):
        bot = _make_bot()
        bc = BotChannel.objects.create(
            bot=bot, name="x", channel_type=ChannelChoices.DING_TALK, channel_config=None
        )
        bc.refresh_from_db()
        assert bc.channel_config is None
        assert bc.decrypted_channel_config is None

    def test_format_channel_config掩码(self):
        bot = _make_bot()
        bc = BotChannel(
            bot=bot,
            name="x",
            channel_type=ChannelChoices.DING_TALK,
            channel_config={"sec": {"client_secret": "v", "client_id": "keep"}},
        )
        out = bc.format_channel_config()
        assert out["sec"]["client_secret"] == "******"
        assert out["sec"]["client_id"] == "keep"


class TestChannelUser:
    def test_to_dict_含display(self):
        u = ChannelUser.objects.create(
            user_id="u1", name="张三", channel_type=ChannelChoices.DING_TALK
        )
        d = u.to_dict()
        assert d["user_id"] == "u1"
        assert d["name"] == "张三"
        assert d["channel_type"] == "ding_talk"
        # display 取自 choices 的中文标签
        assert d["channel_type_display"] == "Ding Talk"


class TestChatApplicationExtractParams:
    def test_mobile_提取参数(self):
        cfg = {"appName": "移动应用", "appDescription": "desc", "appTags": ["a", "b"]}
        out = ChatApplication._extract_app_params(ChatApplication.APP_TYPE_MOBILE, cfg)
        assert out == {
            "app_name": "移动应用",
            "app_description": "desc",
            "app_tags": ["a", "b"],
            "app_icon": "",
        }

    def test_mobile_缺appName返回None(self):
        assert ChatApplication._extract_app_params(ChatApplication.APP_TYPE_MOBILE, {}) is None

    def test_web_chat_提取参数(self):
        cfg = {"appName": "网页", "appDescription": "d", "appIcon": "icon.png"}
        out = ChatApplication._extract_app_params(ChatApplication.APP_TYPE_WEB_CHAT, cfg)
        assert out == {
            "app_name": "网页",
            "app_description": "d",
            "app_tags": [],
            "app_icon": "icon.png",
        }

    def test_web_chat_缺appName返回None(self):
        assert ChatApplication._extract_app_params(ChatApplication.APP_TYPE_WEB_CHAT, {}) is None

    def test_未知类型返回None(self):
        assert ChatApplication._extract_app_params("unknown", {"appName": "x"}) is None


class TestChatApplicationToDict:
    def test_mobile_含tags不含icon(self):
        bot = _make_bot()
        app = ChatApplication.objects.create(
            bot=bot,
            node_id="n1",
            app_type=ChatApplication.APP_TYPE_MOBILE,
            app_name="m",
            app_tags=["t1"],
            app_icon="should-not-appear",
        )
        d = app.to_dict()
        assert d["app_type"] == "mobile"
        assert d["app_type_display"] == "移动端应用"
        assert d["app_tags"] == ["t1"]
        assert "app_icon" not in d

    def test_web_chat_含icon不含tags(self):
        bot = _make_bot()
        app = ChatApplication.objects.create(
            bot=bot,
            node_id="n2",
            app_type=ChatApplication.APP_TYPE_WEB_CHAT,
            app_name="w",
            app_icon="ico",
        )
        d = app.to_dict()
        assert d["app_icon"] == "ico"
        assert "app_tags" not in d


class TestSyncApplicationsFromWorkflow:
    def test_bot未上线删除所有应用(self):
        bot = _make_bot(online=False)
        ChatApplication.objects.create(
            bot=bot, node_id="old", app_type=ChatApplication.APP_TYPE_MOBILE, app_name="o"
        )
        wf = BotWorkFlow(bot=bot, flow_json={"nodes": []})
        # 绕过 save 的自动同步，直接调用类方法验证未上线分支
        created, updated, deleted = ChatApplication.sync_applications_from_workflow(wf)
        assert (created, updated) == (0, 0)
        assert deleted == 1
        assert ChatApplication.objects.filter(bot=bot).count() == 0

    def test_flow_json非法返回零(self):
        bot = _make_bot(online=True)
        wf = BotWorkFlow(bot=bot, flow_json=[])  # 非 dict
        assert ChatApplication.sync_applications_from_workflow(wf) == (0, 0, 0)

    def test_创建更新删除全流程(self):
        bot = _make_bot(online=True)
        # 预置一个会被删除的过期应用
        ChatApplication.objects.create(
            bot=bot, node_id="stale", app_type=ChatApplication.APP_TYPE_MOBILE, app_name="stale"
        )
        flow_json = {
            "nodes": [
                {
                    "id": "node-m",
                    "type": "mobile",
                    "data": {"config": {"appName": "移动", "appTags": ["x"]}},
                },
                {
                    "id": "node-w",
                    "type": "web_chat",
                    "data": {"config": {"appName": "网页", "appIcon": "i.png"}},
                },
                # 缺 appName 的节点被跳过
                {"id": "node-skip", "type": "mobile", "data": {"config": {}}},
                # 无 id 的节点被跳过
                {"type": "web_chat", "data": {"config": {"appName": "noid"}}},
                # 非目标类型忽略
                {"id": "other", "type": "agent", "data": {}},
            ]
        }
        wf = BotWorkFlow(bot=bot, flow_json=flow_json)
        created, updated, deleted = ChatApplication.sync_applications_from_workflow(wf)
        assert created == 2
        assert updated == 0
        assert deleted == 1  # stale 被删
        names = set(ChatApplication.objects.filter(bot=bot).values_list("node_id", flat=True))
        assert names == {"node-m", "node-w"}

        # 再次同步：相同节点 → update 而非 create
        c2, u2, d2 = ChatApplication.sync_applications_from_workflow(wf)
        assert c2 == 0
        assert u2 == 2
        assert d2 == 0


class TestMisc:
    def test_display_fields(self):
        fields = WorkFlowConversationHistory.display_fields()
        assert "conversation_content" in fields
        assert "entry_type" in fields
        assert fields[0] == "id"

    def test_download_token_生成32位hex(self):
        tok = generate_workflow_attachment_download_token()
        assert len(tok) == 32
        int(tok, 16)
        assert tok != generate_workflow_attachment_download_token()
