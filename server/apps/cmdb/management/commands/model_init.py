from django.core.management import BaseCommand

from apps.cmdb.model_migrate.migrete_service import ModelMigrate
from apps.cmdb.services.model import ModelManage
from apps.core.logger import cmdb_logger as logger


class Command(BaseCommand):
    help = "初始化模型"

    def add_arguments(self, parser):
        parser.add_argument(
            "--sync-app-topo-layer",
            action="store_true",
            help="用种子表覆盖已有模型的应用拓扑层级（一次性对齐当前内置分层，默认不覆盖）",
        )

    def handle(self, *args, **options):
        migrator = ModelMigrate(sync_app_topo_layer=bool(options.get("sync_app_topo_layer")))

        # 模型初始化
        logger.info("初始化模型！")
        result = migrator.main()
        ModelManage._apply_model_config_post_import_extras(
            migrator.model_config,
            keep_existing_unique_rules_on_conflict=True,
        )
        logger.info("初始化模型完成！")
        logger.debug(result)
