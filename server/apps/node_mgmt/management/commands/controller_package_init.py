import logging
from django.core.management import BaseCommand
from apps.node_mgmt.management.utils import package_version_upload


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "controller 包文件初始化"

    def add_arguments(self, parser):
        parser.add_argument(
            "--os",
            type=str,
            help="操作系统类型",
            default="linux",
        )
        parser.add_argument(
            "--object",
            type=str,
            help="包对象",
            default="Controller",
        )
        parser.add_argument(
            "--pk_version",
            type=str,
            help="包版本号",
            default="",
        )
        parser.add_argument(
            "--file_path",
            type=str,
            help="文件路径",
            default="",
        )

    def handle(self, *args, **options):
        logger.info("controller 文件初始化开始！")

        package_version_upload("controller", options)

        logger.info("controller 文件初始化完成！")
