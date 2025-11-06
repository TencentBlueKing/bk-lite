# -- coding: utf-8 --
# @File: init_source_api_data.py
# @Time: 2025/7/24 17:00
# @Author: windyzhao

from django.core.management import BaseCommand

from apps.operation_analysis.models.datasource_models import DataSourceAPIModel, NameSpace, DataSourceTag
from apps.operation_analysis.common.load_json_data import load_support_json
from apps.core.logger import operation_analysis_logger as logger


class Command(BaseCommand):
    help = "初始化数据源标签和源API数据"

    def add_arguments(self, parser):
        parser.add_argument(
            '--force-update', '--update',
            action='store_true',
            dest='force_update',
            help='强制更新已存在的数据源配置',
        )

    @staticmethod
    def get_default_namespace():
        """
        获取默认命名空间名称
        :return: 默认命名空间名称
        """
        instance = NameSpace.objects.filter(name="默认命名空间")
        if instance.exists():
            return instance.first().id
        return

    def init_tags(self):
        """
        初始化数据源标签
        """
        logger.info("===开始初始化数据源标签===")
        self.stdout.write(self.style.SUCCESS("开始初始化数据源标签"))

        tags_data = load_support_json('tags.json')
        created_count = 0

        for data in tags_data:
            tag_id = data["tag_id"]
            if DataSourceTag.objects.filter(tag_id=tag_id).exists():
                logger.info(f"标签 {tag_id} 已存在，跳过创建")
                self.stdout.write(self.style.WARNING(f"标签 {tag_id} 已存在，跳过创建"))
                continue

            DataSourceTag.objects.create(**data)
            created_count += 1
            logger.info(f"标签 {tag_id} 创建成功")
            self.stdout.write(self.style.SUCCESS(f"标签 {tag_id} 创建成功"))

        logger.info(f"===数据源标签初始化完成 - 创建: {created_count}===")

    def handle(self, *args, **options):
        logger.info("===开始初始化数据源标签和源API数据===")
        force_update = options['force_update']

        try:
            # 先初始化标签
            self.init_tags()

            # 获取默认命名空间
            # 获取默认命名空间
            namespace_id = self.get_default_namespace()
            if not namespace_id:
                error_msg = "未找到默认命名空间，请先初始化默认命名空间"
                logger.error(error_msg)
                self.stdout.write(self.style.ERROR(error_msg))
                return

            # 从JSON文件加载源API数据
            source_api_data_list = load_support_json('source_api.json')
            created_count = 0
            updated_count = 0

            for api_data in source_api_data_list:
                obj, created = DataSourceAPIModel.objects.get_or_create(
                    name=api_data["name"],
                    rest_api=api_data["rest_api"],
                    defaults={
                        **api_data,
                        "created_by": "system",
                        "updated_by": "system"
                    }
                )

                if created:
                    obj.namespaces.set([namespace_id])
                    created_count += 1
                    logger.info(f"创建数据源: {api_data['name']}")
                elif force_update:
                    # 只有在强制更新模式下才更新现有数据源的配置
                    for key, value in api_data.items():
                        if key != "name":  # name作为唯一标识不更新
                            setattr(obj, key, value)
                    obj.updated_by = "system"
                    obj.save()
                    updated_count += 1
                    logger.info(f"更新数据源: {api_data['name']}")
                else:
                    logger.info(f"跳过已存在的数据源: {api_data['name']} (使用 --force-update 强制更新)")

            success_msg = f"源API数据初始化完成 - 创建: {created_count}, 更新: {updated_count}"
            self.stdout.write(self.style.SUCCESS(success_msg))
            logger.info(f"==={success_msg}===")

        except Exception as e:
            error_msg = f"初始化源API数据失败: {e}"
            logger.error(error_msg)
            self.stdout.write(self.style.ERROR(error_msg))
            raise
