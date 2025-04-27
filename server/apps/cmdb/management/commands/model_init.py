import logging

from django.core.management import BaseCommand

from apps.cmdb.model_migrate.migrete_service import ModelMigrate


class Command(BaseCommand):
    help = "初始化模型"

    def handle(self, *args, **options):
        logger = logging.getLogger(__name__)

        # 模型初始化
        logger.info("初始化模型！")
        result = ModelMigrate().main()
        logger.info("初始化模型完成！结果如下：")
        logger.info(result)
