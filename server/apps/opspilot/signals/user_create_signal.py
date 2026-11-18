from apps.base.models import User
from apps.opspilot.services.bot_init_service import BotInitService
from apps.opspilot.services.channel_init_service import ChannelInitService


def user_create_signal(**kwargs):
    user, _ = User.objects.get_or_create(username="admin", defaults={"is_superuser": True, "is_staff": True})
    service = BotInitService(owner=user)
    service.init()

    channel_service = ChannelInitService(owner=user)
    channel_service.init()
