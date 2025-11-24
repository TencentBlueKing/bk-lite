import json
import os

from apps.node_mgmt.models.sidecar import Collector
from apps.core.logger import node_logger as logger


PLUGIN_DIRECTORY = 'apps/node_mgmt/support-files/collectors'


def import_collector(collectors):
    old_collector = Collector.objects.all()
    old_collector_set = {i.id for i in old_collector}

    create_collectors, update_collectors = [], []

    for collector_info in collectors:
        if collector_info["id"] in old_collector_set:
            update_collectors.append(collector_info)
        else:
            create_collectors.append(collector_info)

    if create_collectors:
        Collector.objects.bulk_create([Collector(**i) for i in create_collectors])

    if update_collectors:
        Collector.objects.bulk_update([Collector(**i) for i in update_collectors],
                                      ["service_type", "executable_path", "execute_parameters", "validation_parameters",
                                       "default_template", "introduction", "enabled_default_config", "default_config","tags", "package_name"])


def migrate_collector():
    """迁移采集器"""
    collectors_path = []
    for file_name in os.listdir(PLUGIN_DIRECTORY):
        file_path = os.path.join(PLUGIN_DIRECTORY, file_name)
        # 直接检查JSON文件，跳过目录
        if os.path.isfile(file_path) and file_name.endswith('.json'):
            collectors_path.append(file_path)

    for file_path in collectors_path:
        # 打开并读取 JSON 文件
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                collectors_data = json.load(file)
                import_collector(collectors_data)
        except Exception as e:
            logger.error(f'导入采集器 {file_path} 失败！原因：{e}')


def collector_init():
    """
    初始化采集器
    """
    migrate_collector()
