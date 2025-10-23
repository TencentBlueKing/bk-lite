from apps.base.models import User
from apps.opspilot.services.bot_init_service import BotInitService
from apps.opspilot.services.channel_init_service import ChannelInitService

# from apps.opspilot.model_provider_mgmt.services.model_provider_init_service import ModelProviderInitService


def user_create_signal(**kwargs):
    user, _ = User.objects.get_or_create(username="admin", defaults={"is_superuser": True, "is_staff": True})
    service = BotInitService(owner=user)
    service.init()

    channel_service = ChannelInitService(owner=user)
    channel_service.init()

    # model_service = ModelProviderInitService(owner=user)
    # model_service.init()
