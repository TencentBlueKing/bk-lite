import os

from apps.node_mgmt.models.sidecar import Collector
from apps.core.logger import node_logger as logger
from apps.node_mgmt.management.services.node_init.definition_loader import load_definition_records
from apps.node_mgmt.utils.collector_tags import normalize_collector_tags


COMMUNITY_PLUGIN_DIRECTORY = "apps/node_mgmt/support-files/collectors"
ENTERPRISE_PLUGIN_DIRECTORY = "apps/node_mgmt/enterprise/support-files/collectors"


def import_collector(collectors):
    old_collector = Collector.objects.all()
    old_collector_set = {i.id for i in old_collector}

    create_collectors, update_collectors = [], []

    for collector_info in collectors:
        collector_info["tags"] = normalize_collector_tags(
            collector_info.get("tags"),
            collector_info.get("node_operating_system"),
            collector_info.get("cpu_architecture"),
        )
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
                "cpu_architecture",
                "is_pre",
            ],
        )


def migrate_collector():
    """迁移采集器"""
    collectors_data = load_definition_records(
        COMMUNITY_PLUGIN_DIRECTORY,
        ENTERPRISE_PLUGIN_DIRECTORY,
    )

    # 收集所有内置采集器的ID
    builtin_collector_ids = set()

    import_collector([{k: v for k, v in collector.items() if not k.startswith("_")} for collector in collectors_data])
    for collector in collectors_data:
        builtin_collector_ids.add(collector["id"])

    # 删除已移除的内置采集器（只删除 is_pre=True 的采集器）
    # 这样可以保护用户通过视图创建的采集器（is_pre=False）
    removed_builtin_collectors = Collector.objects.filter(is_pre=True).exclude(id__in=builtin_collector_ids)

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
