# -- coding: utf-8 --
# @File: update_collect_task_data.py
# @Time: 2025/12/8 10:18
# @Author: windyzhao
"""
更新配置采集任务数据
1.模型CollectModels 给team补充缺失的数据organization
前提是ip_range字段是空的
然后默认补充的组织是默认组织是get_default_group_id函数
"""
from django.core.management import BaseCommand
from django.db.models import Q

from apps.core.logger import cmdb_logger as logger
from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.utils.base import get_default_group_id


class Command(BaseCommand):
    help = "更新采集任务数据,给team字段补充缺失的默认组织"

    def handle(self, *args, **options):
        logger.info("开始更新采集任务数据...")

        try:
            # 获取默认组织ID
            default_group_id = get_default_group_id()
            logger.info(f"默认组织ID: {default_group_id}")

            # 查询ip_range为空的采集任务
            collect_tasks = CollectModels.objects.filter(Q(ip_range__isnull=True) | Q(ip_range=''))
            total_count = collect_tasks.count()
            logger.info(f"找到 {total_count} 条需要更新的采集任务")

            # 收集需要更新的任务
            tasks_to_update = []
            for task in collect_tasks:
                # 检查team是否为空或不存在
                if not task.team:
                    task.team = default_group_id
                    tasks_to_update.append(task)
                    logger.info(f"任务ID: {task.id}, 任务名称: {task.name} - 准备更新team字段")
                else:
                    logger.info(f"任务ID: {task.id}, 任务名称: {task.name} - team字段已存在,跳过")

            # 批量更新
            updated_count = 0
            if tasks_to_update:
                CollectModels.objects.bulk_update(tasks_to_update, ['team'], batch_size=500)
                updated_count = len(tasks_to_update)
                logger.info(f"批量更新完成,共更新 {updated_count} 条数据")

            logger.info(f"更新完成! 总计: {total_count} 条, 实际更新: {updated_count} 条")

        except Exception as e:
            logger.error(f"更新采集任务数据失败: {str(e)}")
            raise
