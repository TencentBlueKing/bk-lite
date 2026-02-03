from apps.core.logger import opspilot_logger as logger
from apps.opspilot.enum import ChannelChoices
from apps.opspilot.models import Channel


class ChannelInitService:
    def __init__(self, owner):
        self.owner = owner

    def init(self):
        logger.info("初始化企业微信应用通道")
        Channel.objects.get_or_create(
            name=ChannelChoices.ENTERPRISE_WECHAT.value,
            channel_type=ChannelChoices.ENTERPRISE_WECHAT,
            created_by=self.owner,
            defaults={
                "channel_config": {
                    "channels.enterprise_wechat_channel.EnterpriseWechatChannel": {
                        "corp_id": "",
                        "secret": "",  # 加密
                        "token": "",  # 加密
                        "aes_key": "",  # 加密
                        "agent_id": "",
                    }
                },
            },
        )

        logger.info("初始化钉钉通道")
        Channel.objects.get_or_create(
            name=ChannelChoices.DING_TALK.value,
            channel_type=ChannelChoices.DING_TALK,
            created_by=self.owner,
            defaults={
                "channel_config": {
                    "channels.dingtalk_channel.DingTalkChannel": {
                        "client_id": "",
                        "client_secret": "",  # 加密
                        "enable_eventbus": False,
                    }
                }
            },
        )

        logger.info("初始化Web通道")
        Channel.objects.get_or_create(
            name=ChannelChoices.WEB.value,
            channel_type=ChannelChoices.WEB,
            created_by=self.owner,
            defaults={"channel_config": {"rest": {}}},
        )

        logger.info("初始化微信公众号通道")
        Channel.objects.update_or_create(
            name=ChannelChoices.WECHAT_OFFICIAL_ACCOUNT.value,
            channel_type=ChannelChoices.WECHAT_OFFICIAL_ACCOUNT,
            created_by=self.owner,
            defaults={
                "channel_config": {
                    "channels.wechat_official_account_channel.WechatOfficialAccountChannel": {
                        "appid": "",
                        "secret": "",  # 加密
                        "token": "",  # 加密
                        "aes_key": "",  # 加密
                    }
                },
            },
        )
