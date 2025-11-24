# -- coding: utf-8 --
# @File: init_default_groups.py
# @Time: 2025/11/6 10:00
# @Author: windyzhao

from django.core.management import BaseCommand
from django.db import transaction

from apps.core.logger import operation_analysis_logger as logger
from apps.operation_analysis.models.datasource_models import DataSourceAPIModel
from apps.operation_analysis.models.models import Directory, Dashboard, Topology, Architecture


def get_default_group_id():
    """
    获取默认组织ID
    :return: 默认组织ID列表
    """
    from apps.system_mgmt.models.user import Group
    default_group = Group.objects.get(name="Default")
    return [default_group.id]


class Command(BaseCommand):
    help = "初始化运营分析模块所有表的默认组织数据（仅为空数据补充）"

    def handle(self, *args, **options):
        """
        为运营分析模块中所有使用了 Groupo 的表初始化默认组织数据
        只为 groups 字段为空的记录补充默认组织
        """
        self.stdout.write(
            self.style.WARNING("开始初始化运营分析模块组织数据...")
        )
        logger.info("开始初始化运营分析模块组织数据")

        # 获取默认组织ID
        try:
            default_groups = get_default_group_id()
            self.stdout.write(
                self.style.SUCCESS(f"默认组织ID: {default_groups}")
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"获取默认组织失败: {e}")
            )
            logger.error(f"获取默认组织失败: {e}")
            return

        # 定义需要初始化的模型列表
        models_to_init = [
            (Directory, "目录"),
            (Dashboard, "仪表盘"),
            (Topology, "拓扑图"),
            (Architecture, "架构图"),
            (DataSourceAPIModel, "数据源API"),
        ]

        total_updated = 0
        total_skipped = 0

        try:
            with transaction.atomic():
                for model_class, model_name in models_to_init:
                    updated, skipped = self._init_model_groups(
                        model_class, model_name, default_groups
                    )
                    total_updated += updated
                    total_skipped += skipped

            self.stdout.write(
                self.style.SUCCESS(
                    f"\n初始化完成! 共更新 {total_updated} 条记录，跳过 {total_skipped} 条记录"
                )
            )
            logger.info(f"初始化组织数据完成! 共更新 {total_updated} 条记录，跳过 {total_skipped} 条记录")

        except Exception as e:
            logger.error(f"初始化组织数据失败: {e}", exc_info=True)
            self.stdout.write(
                self.style.ERROR(f"初始化组织数据失败: {e}")
            )
            raise

    def _init_model_groups(self, model_class, model_name, default_groups):
        """
        为指定模型初始化组织数据
        只为 groups 字段为空的记录补充默认组织
        
        :param model_class: 模型类
        :param model_name: 模型名称（用于日志显示）
        :param default_groups: 默认组织ID列表
        :return: (更新数量, 跳过数量)
        """
        updated_count = 0
        skipped_count = 0

        # 获取所有记录
        all_records = model_class.objects.all()
        total_count = all_records.count()

        if total_count == 0:
            self.stdout.write(
                self.style.WARNING(f"  [{model_name}] 无数据，跳过")
            )
            return 0, 0

        self.stdout.write(f"  [{model_name}] 共 {total_count} 条记录")

        for record in all_records:
            # 获取当前 groups 字段值
            current_groups = record.groups

            # 只处理 groups 为空的记录
            if not current_groups:
                # groups 为空（None 或 []），设置默认组织
                record.groups = default_groups
                record.save(update_fields=['groups'])
                updated_count += 1
            else:
                # groups 不为空，跳过
                skipped_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"  [{model_name}] 更新 {updated_count} 条，跳过 {skipped_count} 条"
            )
        )
        logger.info(f"[{model_name}] 更新 {updated_count} 条，跳过 {skipped_count} 条")

        return updated_count, skipped_count
