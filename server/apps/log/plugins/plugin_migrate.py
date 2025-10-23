import os
import json

from apps.core.logger import log_logger as logger
from apps.log.models import CollectType
from apps.log.plugins import PLUGIN_DIRECTORY


def migrate_collect_type():
    """迁移采集方式"""
    collect_types_path = []
    for collector in os.listdir(PLUGIN_DIRECTORY):
        collector_path = os.path.join(PLUGIN_DIRECTORY, collector)
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


    for file_path in collect_types_path:
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                collect_types_data = json.load(file)
                CollectType.objects.update_or_create(
                    name=collect_types_data['name'],
                    collector=collect_types_data['collector'],
                    defaults=collect_types_data,
                )
        except Exception as e:
            logger.error(f'导入采集方式 {file_path} 失败！原因：{e}')
