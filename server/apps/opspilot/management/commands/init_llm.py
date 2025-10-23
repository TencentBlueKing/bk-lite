from django.core.management import BaseCommand

from apps.opspilot.services.model_provider_init_service import ModelProviderInitService


class Command(BaseCommand):
    help = "初始化模型数据"

    def handle(self, *args, **options):
        ModelProviderInitService(owner="admin").init()
