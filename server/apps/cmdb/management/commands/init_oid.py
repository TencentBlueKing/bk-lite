# -- coding: utf-8 --
import json
import os

from django.core.management import BaseCommand
from apps.core.logger import cmdb_logger as logger

from apps.cmdb.models import OidMapping


class Command(BaseCommand):
    help = "初始化网络设备 OID 映射数据"

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="强制重新初始化,即使已存在内置数据",
        )

    def handle(self, *args, **options):
        force = options.get("force", False)

        # 检查是否已经初始化过
        if OidMapping.objects.filter(built_in=True).exists() and not force:
            logger.info("内置 OID 数据已存在,跳过初始化。使用 --force 参数可强制重新初始化。")
            self.stdout.write(
                self.style.WARNING("内置 OID 数据已存在,跳过初始化")
            )
            return

        # 获取 OID 文件路径
        oid_file_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "support-files",
            "systemoid.json",
        )

        if not os.path.exists(oid_file_path):
            error_msg = f"OID 文件不存在: {oid_file_path}"
            logger.error(error_msg)
            self.stdout.write(self.style.ERROR(error_msg))
            raise FileNotFoundError(error_msg)

        # 读取 OID 数据
        logger.info(f"开始读取 OID 文件: {oid_file_path}")
        with open(oid_file_path, encoding="utf-8") as r:
            net_work_oid_mapping = json.loads(r.read())

        # 如果是强制模式,先删除现有内置数据
        if force:
            delete_count = OidMapping.objects.filter(built_in=True).count()
            OidMapping.objects.filter(built_in=True).delete()
            logger.info(f"强制模式: 已删除 {delete_count} 条现有内置数据")
            self.stdout.write(
                self.style.WARNING(f"已删除 {delete_count} 条现有内置数据")
            )

        # 批量创建 OID 映射
        bulk_data = []
        for data in net_work_oid_mapping.values():
            device_type = data["FirstTypeId"].lower()
            params = {
                "oid": data["OID"],
                "model": data["model"],
                "brand": data["brand"],
                "device_type": device_type,
                "built_in": True,
            }
            bulk_data.append(OidMapping(**params))

        logger.info(f"准备批量创建 {len(bulk_data)} 条 OID 映射记录")
        created_objects = OidMapping.objects.bulk_create(
            bulk_data, batch_size=100, ignore_conflicts=True
        )

        success_msg = f"成功初始化 {len(created_objects)} 条 OID 映射记录"
        logger.info(success_msg)
        self.stdout.write(self.style.SUCCESS(success_msg))
