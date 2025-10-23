# -- coding: utf-8 --
# @File: init_tag.py
# @Time: 2025/9/3 15:27
# @Author: windyzhao
from django.core.management import BaseCommand
from apps.operation_analysis.init_constants import INIT_TAG_DATA
from apps.operation_analysis.models import DataSourceTag
from apps.core.logger import operation_analysis_logger as logger


class Command(BaseCommand):
    help = "初始化源API数据Tag"

    def handle(self, *args, **options):
        logger.info("===开始初始化源API数据Tag===")
        self.stdout.write(self.style.SUCCESS("开始初始化源API数据Tag"))
        for data in INIT_TAG_DATA:
            tag_id = data["tag_id"]
            if DataSourceTag.objects.filter(tag_id=tag_id).exists():
                logger.info(f"Tag {tag_id} 已存在，跳过创建")
                self.stdout.write(self.style.SUCCESS(f"Tag {tag_id} 已存在，跳过创建"))
                continue

            DataSourceTag.objects.create(**data)
            logger.info(f"Tag {tag_id} 创建成功")
            self.stdout.write(self.style.SUCCESS(f"Tag {tag_id} 创建成功"))
