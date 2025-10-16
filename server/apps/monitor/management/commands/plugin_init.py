from django.core.management import BaseCommand

from apps.core.logger import monitor_logger as logger
from apps.monitor.management.services.plugin_migrate import migrate_plugin, migrate_policy


class Command(BaseCommand):
    help = "监控插件初始化"

    def handle(self, *args, **options):
        logger.info("初始化监控插件开始！")
        migrate_plugin()
        migrate_policy()
        logger.info("初始化监控插件完成！")
