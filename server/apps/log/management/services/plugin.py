import os
import json

from django.db.models import Q

from apps.core.logger import log_logger as logger
from apps.log.constants.plugin import PluginConstants
from apps.log.models import CollectType


def migrate_collect_type():
    """迁移采集方式，同步文件系统中的插件配置到数据库，并删除已不存在的插件"""
    collect_types_path = []
    for collector in os.listdir(PluginConstants.DIRECTORY):
        collector_path = os.path.join(PluginConstants.DIRECTORY, collector)
        if not os.path.isdir(collector_path):
            continue
        for collect_type in os.listdir(collector_path):
            collect_type_path = os.path.join(collector_path, collect_type)
            if not os.path.isdir(collect_type_path):
                continue
            for config_name in os.listdir(collect_type_path):
                if config_name == "collect_type.json":
                    config_path = os.path.join(collect_type_path, config_name)
                    collect_types_path.append(config_path)
                    continue

    valid_keys = set()

    for file_path in collect_types_path:
        try:
            with open(file_path, "r", encoding="utf-8") as file:
                collect_types_data = json.load(file)
                name = collect_types_data["name"]
                collector = collect_types_data["collector"]
                valid_keys.add((name, collector))
                CollectType.objects.update_or_create(
                    name=name,
                    collector=collector,
                    defaults=collect_types_data,
                )
        except Exception as e:
            logger.error(f"导入采集方式 {file_path} 失败！原因：{e}")

    if valid_keys:
        try:
            keep_condition = Q()
            for name, collector in valid_keys:
                keep_condition |= Q(name=name, collector=collector)
            deleted_count, _ = CollectType.objects.exclude(keep_condition).delete()
            if deleted_count:
                logger.info(f"已删除 {deleted_count} 个不再存在的采集方式")
        except Exception as e:
            logger.warning(f"清理已删除的采集方式失败：{e}")
