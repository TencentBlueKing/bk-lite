import os
import json

from apps.core.logger import monitor_logger as logger
from apps.monitor.services.plugin import MonitorPluginService
from apps.monitor.services.policy import PolicyService


PLUGIN_DIRECTORY = 'apps/monitor/plugins'


def find_json_paths(root_dir: str, target_filename: str = None):
    """
    查找 plugins/type/config_type/variant/* 的文件路径。

    只要 path，忽略中间目录名和非 .json 文件。
    跳过任何不是目录的中间层。
    可指定具体的文件名称进行过滤。

    :param root_dir: 根目录路径，例如 'plugins'
    :param target_filename: 目标文件名，例如 'Detection Device.json'
    :return: 所有符合条件的文件完整路径列表
    """
    result = []
    for type_name in os.listdir(root_dir):
        type_path = os.path.join(root_dir, type_name)
        if not os.path.isdir(type_path):
            continue
        for config_name in os.listdir(type_path):
            config_path = os.path.join(type_path, config_name)
            if not os.path.isdir(config_path):
                continue
            for variant_name in os.listdir(config_path):
                variant_path = os.path.join(config_path, variant_name)
                if not os.path.isdir(variant_path):
                    continue
                for filename in os.listdir(variant_path):
                    if filename == target_filename:
                        result.append(os.path.join(variant_path, filename))
                        continue
    return result


def migrate_plugin():
    """迁移插件"""
    path_list = find_json_paths(PLUGIN_DIRECTORY, "metrics.json")
    for file_path in path_list:
        # 打开并读取 JSON 文件
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                plugin_data = json.load(file)
                MonitorPluginService.import_monitor_plugin(plugin_data)
        except Exception as e:
            logger.error(f'导入插件 {file_path} 失败！原因：{e}')


def migrate_policy():
    """迁移策略"""
    path_list = find_json_paths(PLUGIN_DIRECTORY, "policy.json")
    for file_path in path_list:
        # 打开并读取 JSON 文件
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                policy_data = json.load(file)
                PolicyService.import_monitor_policy(policy_data)
        except Exception as e:
            logger.error(f'导入策略模版 {file_path} 失败！原因：{e}')
