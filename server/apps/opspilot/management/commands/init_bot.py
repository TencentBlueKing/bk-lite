from django.core.management import BaseCommand

from apps.opspilot.services.bot_init_service import BotInitService


class Command(BaseCommand):
    help = "初始化机器人"

    def handle(self, *args, **options):
        BotInitService("admin").init()
