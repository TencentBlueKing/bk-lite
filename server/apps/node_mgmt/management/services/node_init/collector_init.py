import json
import os

from apps.node_mgmt.models.sidecar import Collector
from apps.core.logger import node_logger as logger


COMMUNITY_PLUGIN_DIRECTORY = "apps/node_mgmt/support-files/collectors"
ENTERPRISE_PLUGIN_DIRECTORY = "apps/node_mgmt/enterprise/support-files/collectors"


def import_collector(collectors):
    old_collector = Collector.objects.all()
    old_collector_set = {i.id for i in old_collector}

    create_collectors, update_collectors = [], []

    for collector_info in collectors:
        if collector_info["id"] in old_collector_set:
            # 更新时确保内置采集器标记为 is_pre=True
            collector_info["is_pre"] = True
            update_collectors.append(collector_info)
        else:
            # 创建时依赖模型默认值 is_pre=True，无需显式设置
            create_collectors.append(collector_info)

    if create_collectors:
        Collector.objects.bulk_create([Collector(**i) for i in create_collectors])

    if update_collectors:
        Collector.objects.bulk_update(
            [Collector(**i) for i in update_collectors],
            [
                "service_type",
                "executable_path",
                "execute_parameters",
                "validation_parameters",
                "default_template",
                "introduction",
                "controller_default_run",
                "default_config",
                "tags",
                "package_name",
                "is_pre",
            ],
        )


def migrate_collector():
    """迁移采集器"""
    collectors_path = []

    plugin_directories = [COMMUNITY_PLUGIN_DIRECTORY]
    if os.path.isdir(ENTERPRISE_PLUGIN_DIRECTORY):
        plugin_directories.append(ENTERPRISE_PLUGIN_DIRECTORY)

    for plugin_dir in plugin_directories:
        if not os.path.isdir(plugin_dir):
            continue
        for file_name in os.listdir(plugin_dir):
            file_path = os.path.join(plugin_dir, file_name)
            if os.path.isfile(file_path) and file_name.endswith(".json"):
                collectors_path.append(file_path)

    # 收集所有内置采集器的ID
    builtin_collector_ids = set()

    for file_path in collectors_path:
        # 打开并读取 JSON 文件
        try:
            with open(file_path, "r", encoding="utf-8") as file:
                collectors_data = json.load(file)
                import_collector(collectors_data)
                # 收集当前文件中的采集器ID
                for collector in collectors_data:
                    builtin_collector_ids.add(collector["id"])
        except Exception as e:
            logger.error(f"导入采集器 {file_path} 失败！原因：{e}")

    # 删除已移除的内置采集器（只删除 is_pre=True 的采集器）
    # 这样可以保护用户通过视图创建的采集器（is_pre=False）
    removed_builtin_collectors = Collector.objects.filter(is_pre=True).exclude(
        id__in=builtin_collector_ids
    )

    if removed_builtin_collectors.exists():
        removed_count = removed_builtin_collectors.count()
        removed_ids = list(removed_builtin_collectors.values_list("id", flat=True))
        removed_builtin_collectors.delete()
        logger.info(f"已删除 {removed_count} 个从内置目录中移除的采集器: {removed_ids}")


def collector_init():
    """
    初始化采集器
    """
    try:
        migrate_collector()
    except Exception as e:
        logger.exception(e)
