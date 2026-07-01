"""opspilot-biz 切片: models/channel_mgmt.Channel 真实 DB 行为测试。

覆盖 save 时按渠道类型对配置字段加解密（避免重复加密）、decrypted_channel_config
还原明文、format_channel_config 对敏感字段掩码。只真实落库后断言。
"""

import pytest

from apps.opspilot.enum import ChannelChoices
from apps.opspilot.models.channel_mgmt import Channel

pytestmark = pytest.mark.django_db


DINGTALK_KEY = "channels.dingtalk_channel.DingTalkChannel"
GITLAB_KEY = "channels.gitlab_review_channel.GitlabReviewChannel"


class TestChannelEncryption:
    def test_dingtalk_保存时加密client_secret(self):
        ch = Channel.objects.create(
            name="钉钉",
            channel_type=ChannelChoices.DING_TALK,
            channel_config={DINGTALK_KEY: {"client_id": "cid", "client_secret": "topsecret"}},
        )
        ch.refresh_from_db()
        stored = ch.channel_config[DINGTALK_KEY]
        # client_secret 已被加密（不再等于明文）
        assert stored["client_secret"] != "topsecret"
        # 非加密字段保持原值
        assert stored["client_id"] == "cid"

    def test_decrypted_channel_config_还原明文(self):
        ch = Channel.objects.create(
            name="钉钉2",
            channel_type=ChannelChoices.DING_TALK,
            channel_config={DINGTALK_KEY: {"client_secret": "topsecret"}},
        )
        ch.refresh_from_db()
        decrypted = ch.decrypted_channel_config
        assert decrypted[DINGTALK_KEY]["client_secret"] == "topsecret"

    def test_重复save不二次加密(self):
        ch = Channel.objects.create(
            name="钉钉3",
            channel_type=ChannelChoices.DING_TALK,
            channel_config={DINGTALK_KEY: {"client_secret": "abc123"}},
        )
        ch.refresh_from_db()
        ch.save()  # 第二次保存：save 先解密再加密，应仍能正确还原
        ch.refresh_from_db()
        # 清除 cached_property 缓存后重新取
        ch2 = Channel.objects.get(id=ch.id)
        assert ch2.decrypted_channel_config[DINGTALK_KEY]["client_secret"] == "abc123"

    def test_gitlab_加密secret_token(self):
        ch = Channel.objects.create(
            name="gitlab",
            channel_type=ChannelChoices.GITLAB,
            channel_config={GITLAB_KEY: {"url": "https://git", "secret_token": "tok"}},
        )
        ch.refresh_from_db()
        stored = ch.channel_config[GITLAB_KEY]
        assert stored["secret_token"] != "tok"
        assert stored["url"] == "https://git"
        assert ch.decrypted_channel_config[GITLAB_KEY]["secret_token"] == "tok"

    def test_未配置加密的渠道类型不变(self):
        ch = Channel.objects.create(
            name="web",
            channel_type=ChannelChoices.WEB,
            channel_config={"channels.web.WebChannel": {"secret_token": "plain"}},
        )
        ch.refresh_from_db()
        # WEB 类型不在加密配置映射中，保持原值
        assert ch.channel_config["channels.web.WebChannel"]["secret_token"] == "plain"
        assert ch.decrypted_channel_config["channels.web.WebChannel"]["secret_token"] == "plain"

    def test_空配置不报错(self):
        ch = Channel.objects.create(
            name="empty",
            channel_type=ChannelChoices.DING_TALK,
            channel_config=None,
        )
        ch.refresh_from_db()
        assert ch.channel_config is None
        assert ch.decrypted_channel_config is None

    def test_配置缺少渠道键时跳过(self):
        # channel_config 不含 CHANNEL_ENCRYPT_CONFIG 指定的 key，加解密应安全跳过
        ch = Channel.objects.create(
            name="ding-no-key",
            channel_type=ChannelChoices.DING_TALK,
            channel_config={"unrelated": {"x": 1}},
        )
        ch.refresh_from_db()
        assert ch.channel_config == {"unrelated": {"x": 1}}
        assert ch.decrypted_channel_config == {"unrelated": {"x": 1}}


class TestFormatChannelConfig:
    def test_掩码敏感字段(self):
        ch = Channel(
            name="fmt",
            channel_type=ChannelChoices.DING_TALK,
            channel_config={
                "section": {
                    "secret": "s1",
                    "token": "t1",
                    "aes_key": "a1",
                    "client_secret": "c1",
                    "client_id": "keep-me",
                    "empty": "",
                }
            },
        )
        out = ch.format_channel_config()
        sec = out["section"]
        assert sec["secret"] == "******"
        assert sec["token"] == "******"
        assert sec["aes_key"] == "******"
        assert sec["client_secret"] == "******"
        # 非敏感字段保持原值
        assert sec["client_id"] == "keep-me"
        # 敏感字段但值为空 → 不掩码（保持空）
        assert sec["empty"] == ""

    def test_str方法返回name(self):
        ch = Channel(name="my-channel", channel_type=ChannelChoices.WEB)
        assert str(ch) == "my-channel"
