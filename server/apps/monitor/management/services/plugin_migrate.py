import os
import json

from apps.core.logger import monitor_logger as logger
from apps.monitor.constants.database import DatabaseConstants
from apps.monitor.constants.plugin import PluginConstants
from apps.monitor.services.plugin import MonitorPluginService
from apps.monitor.services.policy import PolicyService


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
    path_list = find_json_paths(PluginConstants.DIRECTORY, "metrics.json")
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
    path_list = find_json_paths(PluginConstants.DIRECTORY, "policy.json")
    for file_path in path_list:
        # 打开并读取 JSON 文件
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                policy_data = json.load(file)
                PolicyService.import_monitor_policy(policy_data)
        except Exception as e:
            logger.error(f'导入策略模版 {file_path} 失败！原因：{e}')


def migrate_default_order():
    """
    初始化默认排序
    只初始化order=999（默认值）的分类和对象
    """

    try:
        from django.db import transaction
        from apps.monitor.constants.monitor_object import MonitorObjConstants
        from apps.monitor.models import MonitorObjectType, MonitorObject

        with transaction.atomic():
            # 找出所有需要初始化的分类（order=999）
            uninit_types = set(MonitorObjectType.objects.filter(order=999).values_list('id', flat=True))

            # 找出所有需要初始化的对象（order=999）
            uninit_objects = MonitorObject.objects.filter(order=999).select_related('type')

            type_updates = []
            object_updates = []

            # 遍历默认顺序配置
            for idx, item in enumerate(MonitorObjConstants.DEFAULT_OBJ_ORDER):
                type_id = item.get("type")
                name_list = item.get("name_list", [])

                # 如果该分类需要初始化
                if type_id in uninit_types:
                    obj_type, created = MonitorObjectType.objects.get_or_create(
                        id=type_id,
                        defaults={'order': idx}
                    )
                    if not created and obj_type.order == 999:
                        obj_type.order = idx
                        type_updates.append(obj_type)

                # 初始化该分类下需要初始化的对象
                for name_idx, name in enumerate(name_list):
                    for obj in uninit_objects:
                        if obj.name == name and obj.type_id == type_id:
                            obj.order = name_idx
                            object_updates.append(obj)

            # 批量更新
            if type_updates:
                MonitorObjectType.objects.bulk_update(type_updates, ['order'], batch_size=DatabaseConstants.MONITOR_OBJECT_BATCH_SIZE)
            if object_updates:
                MonitorObject.objects.bulk_update(object_updates, ['order'], batch_size=DatabaseConstants.MONITOR_OBJECT_BATCH_SIZE)

    except Exception as e:
        logger.error(f'初始化默认排序失败！原因：{e}')
