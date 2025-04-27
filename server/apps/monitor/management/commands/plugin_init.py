import logging

from django.core.management import BaseCommand
from apps.monitor.plugin_migrate.service import migrate_plugin

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = "监控插件初始化"

    def handle(self, *args, **options):
        logger.info("初始化监控插件开始！")
        migrate_plugin()
        logger.info("初始化监控插件完成！")
