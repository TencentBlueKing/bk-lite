from apps.system_mgmt.models import IMNotificationChannel
from apps.system_mgmt.providers import RuntimeApplicationService

from .im_channel_access import can_access_im_channel, filter_accessible_im_channels


class IMGroupChannelError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


class IMGroupRuntimeService:
    @staticmethod
    def list_ready_channels(user):
        channels = IMNotificationChannel.objects.select_related("integration_instance").filter(
            enabled=True,
            status="ready",
            integration_instance__provider_key="feishu",
            integration_instance__enabled=True,
            integration_instance__status="ready",
            integration_instance__capability_status__im_notification="ready",
            integration_instance__capability_status__im_group="ready",
        )
        return filter_accessible_im_channels(channels, user)

    @staticmethod
    def require_ready_channel(user, channel_id: int):
        channel = IMNotificationChannel.objects.select_related("integration_instance").filter(id=channel_id).first()
        if not channel or not channel.enabled:
            raise IMGroupChannelError("im_group.channel_unavailable", "IM 群协作渠道不存在或已禁用")
        if channel.status != "ready":
            raise IMGroupChannelError("im_group.channel_not_ready", "IM 群协作渠道尚未就绪")

        instance = channel.integration_instance
        if instance.provider_key != "feishu":
            raise IMGroupChannelError("im_group.provider_unsupported", "IM 群协作仅支持飞书渠道")
        if not instance.enabled or instance.status != "ready":
            raise IMGroupChannelError("im_group.instance_not_ready", "IM 群协作集成实例尚未就绪")
        if (
            instance.capability_status.get("im_notification") != "ready"
            or instance.capability_status.get("im_group") != "ready"
        ):
            raise IMGroupChannelError("im_group.capability_not_ready", "IM 群协作能力尚未就绪")
        if not can_access_im_channel(user, channel):
            raise IMGroupChannelError("im_group.channel_access_denied", "无权访问该团队数据")
        return channel

    @staticmethod
    def execute(channel: IMNotificationChannel, operation: str, **kwargs):
        return RuntimeApplicationService().execute(
            provider_key=channel.integration_instance.provider_key,
            capability_key="im_group",
            operation=operation,
            config=channel.integration_instance.get_runtime_config(),
            channel=channel,
            **kwargs,
        )
