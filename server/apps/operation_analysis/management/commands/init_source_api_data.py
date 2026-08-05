# -- coding: utf-8 --
# @File: init_source_api_data.py
# @Time: 2025/7/24 17:00
# @Author: windyzhao

from django.core.management import BaseCommand

from apps.core.logger import operation_analysis_logger as logger
from apps.operation_analysis.common.builtin_datasource_identity import find_claimable_datasource
from apps.operation_analysis.common.load_json_data import load_support_json
from apps.operation_analysis.models.datasource_models import DataSourceAPIModel, DataSourceTag, NameSpace


class Command(BaseCommand):
    help = "初始化数据源标签和源API数据"

    def add_arguments(self, parser):
        parser.add_argument(
            "--force-update",
            "--update",
            action="store_true",
            dest="force_update",
            help="强制更新已存在的数据源配置",
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

    @staticmethod
    def get_default_groups():
        """
        获取 Default 组织 ID 列表。未初始化 Default 时不阻断数据源初始化。
        """
        from apps.system_mgmt.models.user import Group

        default_group = Group.objects.filter(name="Default").first()
        if default_group:
            return [default_group.id]
        return []

    def init_tags(self):
        """
        初始化数据源标签
        """
        logger.info("===开始初始化数据源标签===")
        self.stdout.write(self.style.SUCCESS("开始初始化数据源标签"))

        tags_data = load_support_json("tags.json")
        created_count = 0

        for data in tags_data:
            tag_id = data["tag_id"]
            if DataSourceTag.objects.filter(tag_id=tag_id).exists():
                logger.info("[SourceApiInit] 标签 %s 已存在，跳过创建", tag_id)
                self.stdout.write(self.style.WARNING(f"标签 {tag_id} 已存在，跳过创建"))
                continue

            DataSourceTag.objects.create(**data)
            created_count += 1
            logger.info("[SourceApiInit] 标签 %s 创建成功", tag_id)
            self.stdout.write(self.style.SUCCESS(f"标签 {tag_id} 创建成功"))

        logger.info("[SourceApiInit] 数据源标签初始化完成，创建 %s 个", created_count)

    def handle(self, *args, **options):
        logger.info("===开始初始化数据源标签和源API数据===")
        force_update = options["force_update"]

        try:
            # 先初始化标签
            self.init_tags()

            # 获取默认命名空间
            namespace_id = self.get_default_namespace()
            if not namespace_id:
                error_msg = "未找到默认命名空间，请先初始化默认命名空间"
                logger.error(error_msg)
                self.stdout.write(self.style.ERROR(error_msg))
                return
            default_groups = self.get_default_groups()

            # 从JSON文件加载源API数据
            source_api_data_list = load_support_json("source_api.json")
            created_count = 0
            updated_count = 0

            for api_data in source_api_data_list:
                # 提取标签数据,避免在defaults中包含多对多字段
                tags = api_data.pop("tag", [])
                # 显式 key 优先，避免改展示名时拖动稳定身份。
                stable_key = api_data.pop("key", None) or f"{api_data['name']}::{api_data['rest_api']}"

                # 准备创建数据(排除多对多字段)
                defaults = {k: v for k, v in api_data.items() if k not in ["name", "rest_api"]}
                defaults["created_by"] = "system"
                defaults["updated_by"] = "system"
                defaults["groups"] = default_groups
                defaults["is_build_in"] = True
                defaults["build_in_key"] = stable_key

                # 仅按 build_in_key / 精确 (name, rest_api) / key 内历史名认领；禁止只按 rest_api。
                obj = find_claimable_datasource(
                    DataSourceAPIModel,
                    stable_key=stable_key,
                    name=api_data["name"],
                    rest_api=api_data["rest_api"],
                )

                created = False
                if not obj:
                    obj = DataSourceAPIModel.objects.create(
                        name=api_data["name"],
                        rest_api=api_data["rest_api"],
                        **defaults,
                    )
                    created = True

                # 获取标签实例
                tag_instances = DataSourceTag.objects.filter(tag_id__in=tags)

                if created:
                    obj.namespaces.set([namespace_id])
                    if tag_instances.exists():
                        obj.tag.set(tag_instances)
                    created_count += 1
                    logger.info("[SourceApiInit] 创建数据源：%s", api_data["name"])
                elif force_update:
                    # build_in_key / rest_api 是内置配置的稳定身份；允许覆盖展示名。
                    for key, value in api_data.items():
                        if key not in ["name", "rest_api"]:
                            setattr(obj, key, value)

                    obj.name = api_data["name"]
                    obj.rest_api = api_data["rest_api"]
                    obj.updated_by = "system"
                    obj.is_build_in = True
                    obj.build_in_key = stable_key
                    if not obj.groups and default_groups:
                        obj.groups = default_groups
                    obj.save()

                    # 更新标签关联
                    if tag_instances.exists():
                        obj.tag.set(tag_instances)

                    updated_count += 1
                    logger.info("[SourceApiInit] 更新数据源：%s", api_data["name"])
                else:
                    if not obj.groups and default_groups:
                        obj.groups = default_groups
                        obj.save(update_fields=["groups"])
                        logger.info("[SourceApiInit] 补充数据源默认组织：%s", api_data["name"])
                    logger.info("[SourceApiInit] 跳过已存在的数据源：%s", api_data["name"])

            success_msg = f"源API数据初始化完成 - 创建: {created_count}, 更新: {updated_count}"
            self.stdout.write(self.style.SUCCESS(success_msg))
            logger.info("[SourceApiInit] %s", success_msg)

        except Exception as e:
            error_msg = f"初始化源API数据失败: {e}"
            logger.error("[SourceApiInit] 初始化源API数据失败：%s", e, exc_info=True)
            self.stdout.write(self.style.ERROR(error_msg))
            raise
