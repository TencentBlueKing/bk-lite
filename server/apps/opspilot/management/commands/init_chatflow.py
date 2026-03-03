from django.core.management import BaseCommand

from apps.opspilot.services.chatflow_init_service import ChatFlowInitService


class Command(BaseCommand):
    help = "初始化内置 ChatFlow Bot（从 chatflow_data 目录读取配置）"

    def handle(self, *args, **options):
        self.stdout.write("开始初始化 ChatFlow")

        service = ChatFlowInitService()
        service.init()

        self.stdout.write(self.style.SUCCESS("ChatFlow 初始化完成"))
