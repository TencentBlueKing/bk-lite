from django.core.management import BaseCommand

from apps.base.models import User
from apps.opspilot.bot_mgmt.services.bot_init_service import BotInitService


class Command(BaseCommand):
    help = "初始化机器人"

    def handle(self, *args, **options):
        admin_user = User.objects.get(username="admin")
        BotInitService(owner=admin_user).init()
