from django.core.management import BaseCommand
from apps.node_mgmt.node_init.cloud_init import cloud_init
from apps.node_mgmt.node_init.collector_init import collector_init
from apps.node_mgmt.node_init.controller_init import controller_init
from apps.core.logger import node_logger as logger


class Command(BaseCommand):
    help = "节点管理内置数据初始化"

    def handle(self, *args, **options):
        logger.info("初始化默认云区域！")
        cloud_init()
        logger.info("初始化默认云区域完成！")

        logger.info("初始化控制器！")
        controller_init()
        logger.info("初始化控制器完成！")

        logger.info("初始化采集器！")
        collector_init()
        logger.info("初始化采集器完成！")
