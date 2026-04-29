from django.core.management import BaseCommand
from asgiref.sync import async_to_sync

from apps.core.logger import node_logger as logger
from apps.node_mgmt.constants.installer import InstallerConstants
from apps.node_mgmt.constants.node import NodeConstants
from apps.node_mgmt.utils.s3 import upload_file_to_s3


class Command(BaseCommand):
    help = "安装器初始化 - 上传安装器文件到 latest 路径"

    def add_arguments(self, parser):
        parser.add_argument(
            "--os",
            type=str,
            choices=["windows", "linux"],
            default="windows",
            help="安装器目标操作系统",
        )
        parser.add_argument(
            "--file_path",
            type=str,
            help="安装器文件路径",
            required=True,
        )
        parser.add_argument(
            "--cpu_architecture",
            type=str,
            choices=[NodeConstants.X86_64_ARCH, NodeConstants.ARM64_ARCH],
            default=NodeConstants.X86_64_ARCH,
            help="安装器 CPU 架构",
        )

    def handle(self, *args, **options):
        target_os = options["os"]
        file_path = options["file_path"]
        cpu_architecture = options["cpu_architecture"]
        alias_path = InstallerConstants.build_latest_alias_path(target_os, cpu_architecture)

        logger.info(f"{target_os}/{cpu_architecture} 安装器初始化开始，文件路径: {file_path}")

        try:
            with open(file_path, "rb") as file:
                data = file.read()
            from io import BytesIO

            alias_file = BytesIO(data)
            alias_file.name = file_path

            async_to_sync(upload_file_to_s3)(alias_file, alias_path)
            logger.info(f"{target_os}/{cpu_architecture} 安装器上传成功，latest 路径: {alias_path}")
        except FileNotFoundError:
            logger.error(f"文件不存在: {file_path}")
            raise
        except Exception as e:
            logger.error(f"{target_os}/{cpu_architecture} 安装器上传失败: {e}")
            raise

        logger.info(f"{target_os}/{cpu_architecture} 安装器初始化完成！")
