from django.core.management import BaseCommand

from apps.opspilot.services.channel_init_service import ChannelInitService


class Command(BaseCommand):
    help = "初始化消息通道"

    def handle(self, *args, **options):
        ChannelInitService(owner="admin").init()
