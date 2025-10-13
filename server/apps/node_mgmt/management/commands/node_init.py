from django.core.management import BaseCommand
from apps.core.logger import node_logger as logger
from apps.node_mgmt.management.services.node_init.cloud_init import cloud_init
from apps.node_mgmt.management.services.node_init.collector_init import collector_init
from apps.node_mgmt.management.services.node_init.controller_init import controller_init


class Command(BaseCommand):
    help = "节点管理内置数据初始化"

    def handle(self, *args, **options):
        logger.info("初始化默认云区域！")
        cloud_init()

        logger.info("初始化控制器！")
        controller_init()

        logger.info("初始化采集器！")
        collector_init()
