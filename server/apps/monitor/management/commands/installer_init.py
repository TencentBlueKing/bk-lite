from django.core.management import BaseCommand
from asgiref.sync import async_to_sync

from apps.core.logger import monitor_logger as logger
from apps.monitor.constants.installer import WINDOWS_INSTALLER_S3_PATH
from apps.node_mgmt.utils.s3 import upload_file_to_s3


class Command(BaseCommand):
    help = "Windows 安装器初始化 - 上传安装器文件到 S3"

    def add_arguments(self, parser):
        parser.add_argument(
            "--file_path",
            type=str,
            help="安装器文件路径",
            required=True,
        )

    def handle(self, *args, **options):
        file_path = options["file_path"]

        logger.info(f"Windows 安装器初始化开始，文件路径: {file_path}")

        try:
            with open(file_path, "rb") as file:
                async_to_sync(upload_file_to_s3)(file, WINDOWS_INSTALLER_S3_PATH)
            logger.info(f"Windows 安装器上传成功，S3 路径: {WINDOWS_INSTALLER_S3_PATH}")
        except FileNotFoundError:
            logger.error(f"文件不存在: {file_path}")
            raise
        except Exception as e:
            logger.error(f"Windows 安装器上传失败: {e}")
            raise

        logger.info("Windows 安装器初始化完成！")
