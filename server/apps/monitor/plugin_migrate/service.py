import os
import json
import logging
from apps.monitor.services.plugin import MonitorPluginService

logger = logging.getLogger(__name__)


def migrate_plugin():
    """迁移插件"""
    # 指定存放插件文件的目录
    files_directory = 'apps/monitor/plugin_migrate/plugins'

    # 遍历 files 目录中的所有文件
    for filename in os.listdir(files_directory):
        # 只处理 .json 文件
        if filename.endswith('.json'):
            file_path = os.path.join(files_directory, filename)

            # 打开并读取 JSON 文件
            try:
                with open(file_path, 'r', encoding='utf-8') as file:
                    plugin_data = json.load(file)
                    MonitorPluginService.import_monitor_plugin(plugin_data)
            except Exception as e:
                logger.error(f'导入插件 {filename} 失败！原因：{e}')
