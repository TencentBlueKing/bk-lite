from django.db import transaction

from apps.core.logger import node_logger as logger
from apps.node_mgmt.management.services.node_init.definition_loader import load_definition_records
from apps.node_mgmt.models.sidecar import Collector, CollectorDefaultBackfill
from apps.node_mgmt.services.collector_preset_refresh import refresh_collector_presets
from apps.node_mgmt.utils.collector_tags import normalize_collector_tags

COMMUNITY_PLUGIN_DIRECTORY = "apps/node_mgmt/support-files/collectors"
ENTERPRISE_PLUGIN_DIRECTORY = "apps/node_mgmt/enterprise/support-files/collectors"
_MODE_TEMPLATE_EXCLUDED_KEYS = {"add_config", "config_section"}


def _new_builtin_backfill_ids(create_collectors):
    collector_ids = []
    for item in create_collectors:
        if item.get("is_pre") is False or not item.get("controller_default_run"):
            continue
        default_config = item.get("default_config")
        if not isinstance(default_config, dict):
            continue
        has_template = any(
            key not in _MODE_TEMPLATE_EXCLUDED_KEYS and isinstance(value, str) and value.strip() for key, value in default_config.items()
        )
        if has_template:
            collector_ids.append(item["id"])
    return collector_ids


def _enqueue_new_collector_followup(*, schedule_task):
    from apps.node_mgmt.tasks.collector_default_backfill import enqueue_collector_default_backfill

    enqueue_collector_default_backfill(schedule_task=schedule_task)


def _collector_for_catalog_update(item, preserved_default_configs):
    collector = Collector(**item)
    if item["id"] in preserved_default_configs:
        collector.default_config = preserved_default_configs[item["id"]]
    return collector


def _refresh_changed_presets(old_by_id, update_collectors):
    """先改预置正文。失败的采集器本轮目录继续留着旧 default_config。"""
    preserved_default_configs = {}
    for item in update_collectors:
        current = old_by_id.get(item["id"])
        if current is None or not item.get("controller_default_run"):
            continue
        new_default_config = item.get("default_config")
        if current.default_config == new_default_config:
            continue
        if not refresh_collector_presets(current, new_default_config):
            preserved_default_configs[item["id"]] = current.default_config
    return preserved_default_configs


def import_collector(collectors):
    old_collectors = list(Collector.objects.all())
    old_by_id = {row.id: row for row in old_collectors}

    create_collectors, update_collectors = [], []

    for collector_info in collectors:
        collector_info["tags"] = normalize_collector_tags(
            collector_info.get("tags"),
            collector_info.get("node_operating_system"),
            collector_info.get("cpu_architecture"),
        )
        if collector_info["id"] in old_by_id:
            # 更新时确保内置采集器标记为 is_pre=True
            collector_info["is_pre"] = True
            update_collectors.append(collector_info)
        else:
            # 创建时依赖模型默认值 is_pre=True，无需显式设置
            create_collectors.append(collector_info)

    if create_collectors:
        backfill_ids = _new_builtin_backfill_ids(create_collectors)
        with transaction.atomic():
            Collector.objects.bulk_create([Collector(**item) for item in create_collectors])
            if backfill_ids:
                CollectorDefaultBackfill.objects.bulk_create(
                    [CollectorDefaultBackfill(collector_id=collector_id) for collector_id in backfill_ids],
                    ignore_conflicts=True,
                )
            schedule_task = bool(backfill_ids)
            transaction.on_commit(lambda schedule_task=schedule_task: _enqueue_new_collector_followup(schedule_task=schedule_task))

    if update_collectors:
        preserved_default_configs = _refresh_changed_presets(old_by_id, update_collectors)
        imported_ids = set(
            Collector.objects.filter(
                id__in=[item["id"] for item in update_collectors],
                imported_package_version__gt="",
            ).values_list("id", flat=True)
        )
        update_fields = [
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
        ]
        normal = [_collector_for_catalog_update(item, preserved_default_configs) for item in update_collectors if item["id"] not in imported_ids]
        imported = [_collector_for_catalog_update(item, preserved_default_configs) for item in update_collectors if item["id"] in imported_ids]
        if normal:
            Collector.objects.bulk_update(normal, update_fields)
        if imported:
            Collector.objects.bulk_update(
                imported,
                [field for field in update_fields if field != "execute_parameters"],
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
