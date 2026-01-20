import json
from pathlib import Path

from apps.core.logger import monitor_logger as logger
from apps.monitor.constants.database import DatabaseConstants
from apps.monitor.constants.plugin import PluginConstants
from apps.monitor.management.utils import (
    find_files_by_pattern,
    extract_plugin_path_info,
    parse_template_filename,
)
from apps.monitor.services.plugin import MonitorPluginService


def _import_plugins_from_files(path_list):
    """导入插件基础信息"""
    success_count = 0
    error_count = 0

    for file_path in path_list:
        try:
            plugin_data = json.loads(Path(file_path).read_text(encoding="utf-8"))

            # 从文件路径提取采集器和采集方式信息
            collector, collect_type = extract_plugin_path_info(file_path)
            plugin_data["collector"] = collector
            plugin_data["collect_type"] = collect_type

            plugin_name = plugin_data.get("plugin")
            MonitorPluginService.import_monitor_plugin(plugin_data)
            logger.info(f"导入插件成功: {plugin_name} ({collector}/{collect_type})")
            success_count += 1

        except Exception as e:
            logger.error(f"导入插件失败: {file_path}, 错误: {e}")
            import traceback

            logger.error(traceback.format_exc())
            error_count += 1

    return success_count, error_count


def _load_plugins_to_memory():
    """加载所有插件到内存"""
    from apps.monitor.models import MonitorPlugin

    plugins_dict = {plugin.name: plugin for plugin in MonitorPlugin.objects.all()}
    logger.info(f"已加载 {len(plugins_dict)} 个插件到内存")
    return plugins_dict


def _load_templates_to_memory():
    """预加载所有模板到内存"""
    from apps.monitor.models import MonitorPluginConfigTemplate, MonitorPluginUITemplate

    # 按插件 ID 分组的配置模板
    all_config_templates = {}
    for tpl in MonitorPluginConfigTemplate.objects.select_related("plugin").all():
        if tpl.plugin_id not in all_config_templates:
            all_config_templates[tpl.plugin_id] = {}
        key = (tpl.type, tpl.config_type, tpl.file_type)
        all_config_templates[tpl.plugin_id][key] = tpl

    # 按插件 ID 分组的 UI 模板
    all_ui_templates = {
        tpl.plugin_id: tpl
        for tpl in MonitorPluginUITemplate.objects.select_related("plugin").all()
    }

    logger.info(f"已加载配置模板和 UI 模板到内存")
    return all_config_templates, all_ui_templates


def _process_config_templates(plugin_dir, plugin_obj, db_templates):
    """处理配置模板：收集需要创建、更新、删除的模板"""
    from apps.monitor.models import MonitorPluginConfigTemplate

    to_create = []
    to_update = []
    file_templates = {}

    # 收集文件中的模板
    for j2_file in plugin_dir.glob("*.j2"):
        if not j2_file.is_file():
            continue
        try:
            type_name, config_type, file_type = parse_template_filename(j2_file.name)
            if not type_name or not config_type or not file_type:
                continue

            content = j2_file.read_text(encoding="utf-8")
            template_key = (type_name, config_type, file_type)
            file_templates[template_key] = content
        except Exception as e:
            logger.error(f"读取模板文件失败: {j2_file}, 错误: {e}")

    # 对比数据库模板
    for template_key, content in file_templates.items():
        type_name, config_type, file_type = template_key

        if template_key in db_templates:
            db_template = db_templates[template_key]
            if db_template.content != content:
                db_template.content = content
                to_update.append(db_template)
        else:
            to_create.append(
                MonitorPluginConfigTemplate(
                    plugin=plugin_obj,
                    type=type_name,
                    config_type=config_type,
                    file_type=file_type,
                    content=content,
                )
            )

    # 找出需要删除的模板
    to_delete = [
        db_template
        for template_key, db_template in db_templates.items()
        if template_key not in file_templates
    ]

    return to_create, to_update, to_delete


def _process_ui_templates(plugin_dir, plugin_obj, db_ui_template):
    """处理 UI 模板：收集需要创建、更新、删除的模板"""
    from apps.monitor.models import MonitorPluginUITemplate

    to_create = []
    to_update = []
    to_delete = []

    ui_file = plugin_dir / "UI.json"

    if ui_file.exists() and ui_file.is_file():
        try:
            ui_data = json.loads(ui_file.read_text(encoding="utf-8"))

            if db_ui_template:
                if db_ui_template.content != ui_data:
                    db_ui_template.content = ui_data
                    to_update.append(db_ui_template)
            else:
                to_create.append(
                    MonitorPluginUITemplate(plugin=plugin_obj, content=ui_data)
                )
        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"处理 UI 文件失败: {ui_file}, 错误: {e}")
    else:
        if db_ui_template:
            to_delete.append(db_ui_template)

    return to_create, to_update, to_delete


def _collect_templates_to_process(
    path_list, plugins_dict, all_config_templates, all_ui_templates
):
    """收集所有需要处理的模板"""
    config_templates_to_create = []
    config_templates_to_update = []
    config_templates_to_delete = []
    ui_templates_to_create = []
    ui_templates_to_update = []
    ui_templates_to_delete = []

    for file_path in path_list:
        try:
            plugin_data = json.loads(Path(file_path).read_text(encoding="utf-8"))
            plugin_name = plugin_data.get("plugin")

            plugin_obj = plugins_dict.get(plugin_name)
            if not plugin_obj:
                logger.warning(f"插件对象未找到: {plugin_name}，跳过模板导入")
                continue

            plugin_dir = Path(file_path).parent
            db_templates = all_config_templates.get(plugin_obj.id, {})
            db_ui_template = all_ui_templates.get(plugin_obj.id)

            # 处理配置模板
            create, update, delete = _process_config_templates(
                plugin_dir, plugin_obj, db_templates
            )
            config_templates_to_create.extend(create)
            config_templates_to_update.extend(update)
            config_templates_to_delete.extend(delete)

            # 处理 UI 模板
            create, update, delete = _process_ui_templates(
                plugin_dir, plugin_obj, db_ui_template
            )
            ui_templates_to_create.extend(create)
            ui_templates_to_update.extend(update)
            ui_templates_to_delete.extend(delete)

        except Exception as e:
            logger.error(f"处理插件模板失败: {file_path}, 错误: {e}")
            import traceback

            logger.error(traceback.format_exc())

    return {
        "config": (
            config_templates_to_create,
            config_templates_to_update,
            config_templates_to_delete,
        ),
        "ui": (ui_templates_to_create, ui_templates_to_update, ui_templates_to_delete),
    }


def _batch_save_templates(templates_data):
    """批量执行数据库操作：创建、更新、删除模板"""
    from django.db import transaction
    from apps.monitor.models import MonitorPluginConfigTemplate, MonitorPluginUITemplate

    stats = {
        "config_create": 0,
        "config_update": 0,
        "config_delete": 0,
        "ui_create": 0,
        "ui_update": 0,
        "ui_delete": 0,
    }

    config_create, config_update, config_delete = templates_data["config"]
    ui_create, ui_update, ui_delete = templates_data["ui"]

    with transaction.atomic():
        # 配置模板操作
        if config_create:
            MonitorPluginConfigTemplate.objects.bulk_create(
                config_create, batch_size=DatabaseConstants.MONITOR_OBJECT_BATCH_SIZE
            )
            stats["config_create"] = len(config_create)
            logger.info(f"批量创建配置模板: {stats['config_create']} 个")

        if config_update:
            MonitorPluginConfigTemplate.objects.bulk_update(
                config_update,
                ["content"],
                batch_size=DatabaseConstants.MONITOR_OBJECT_BATCH_SIZE,
            )
            stats["config_update"] = len(config_update)
            logger.info(f"批量更新配置模板: {stats['config_update']} 个")

        if config_delete:
            template_ids = [tpl.id for tpl in config_delete]
            stats["config_delete"] = MonitorPluginConfigTemplate.objects.filter(
                id__in=template_ids
            ).delete()[0]
            logger.info(f"批量删除配置模板: {stats['config_delete']} 个")

        # UI 模板操作
        if ui_create:
            MonitorPluginUITemplate.objects.bulk_create(
                ui_create, batch_size=DatabaseConstants.MONITOR_OBJECT_BATCH_SIZE
            )
            stats["ui_create"] = len(ui_create)
            logger.info(f"批量创建 UI 模板: {stats['ui_create']} 个")

        if ui_update:
            MonitorPluginUITemplate.objects.bulk_update(
                ui_update,
                ["content"],
                batch_size=DatabaseConstants.MONITOR_OBJECT_BATCH_SIZE,
            )
            stats["ui_update"] = len(ui_update)
            logger.info(f"批量更新 UI 模板: {stats['ui_update']} 个")

        if ui_delete:
            template_ids = [tpl.id for tpl in ui_delete]
            stats["ui_delete"] = MonitorPluginUITemplate.objects.filter(
                id__in=template_ids
            ).delete()[0]
            logger.info(f"批量删除 UI 模板: {stats['ui_delete']} 个")

    return stats


def _cleanup_removed_plugins(path_list):
    """删除已移除的内置插件"""
    from django.db import transaction
    from apps.monitor.models import MonitorPlugin

    # 收集所有内置目录中的插件名称
    builtin_plugin_names = set()
    for file_path in path_list:
        try:
            plugin_data = json.loads(Path(file_path).read_text(encoding="utf-8"))
            plugin_name = plugin_data.get("plugin")
            if plugin_name:
                builtin_plugin_names.add(plugin_name)
        except Exception as e:
            logger.error(f"读取插件名称失败: {file_path}, 错误: {e}")

    # 删除已移除的内置插件
    removed_plugins = MonitorPlugin.objects.filter(is_pre=True).exclude(
        name__in=builtin_plugin_names
    )

    if removed_plugins.exists():
        removed_count = removed_plugins.count()
        removed_names = list(removed_plugins.values_list("name", flat=True))

        with transaction.atomic():
            removed_plugins.delete()

        logger.info(f"已删除 {removed_count} 个从内置目录中移除的插件: {removed_names}")
        logger.info(f"关联的配置模板和 UI 模板已自动级联删除")


def _cleanup_orphan_objects():
    """删除没有关联插件的监控对象"""
    from django.db import transaction
    from django.db.models import Count
    from apps.monitor.models import MonitorObject

    orphan_objects = MonitorObject.objects.annotate(
        plugin_count=Count("monitorplugin")
    ).filter(plugin_count=0)

    if orphan_objects.exists():
        orphan_count = orphan_objects.count()
        orphan_names = list(orphan_objects.values_list("name", flat=True))

        with transaction.atomic():
            orphan_objects.delete()

        logger.info(f"已删除 {orphan_count} 个没有关联插件的监控对象: {orphan_names}")
        logger.info(f"关联的指标组、指标、监控实例已自动级联删除")


def _cleanup_empty_builtin_metric_groups():
    """删除没有指标的内置指标分组"""
    from django.db import transaction
    from django.db.models import Count
    from apps.monitor.models import MetricGroup

    empty_groups = (
        MetricGroup.objects.filter(is_pre=True)
        .annotate(metric_count=Count("metric"))
        .filter(metric_count=0)
    )

    if empty_groups.exists():
        empty_count = empty_groups.count()
        empty_names = list(empty_groups.values_list("name", flat=True))

        with transaction.atomic():
            empty_groups.delete()

        logger.info(f"已删除 {empty_count} 个没有指标的内置指标分组: {empty_names}")


def migrate_plugin():
    """
    迁移插件及其配置模板和 UI 模板。

    流程：
    1. 导入插件基础信息
    2. 同步配置模板和 UI 模板
    3. 清理已移除的内置插件
    4. 清理孤立的监控对象
    """
    path_list = find_files_by_pattern(
        PluginConstants.DIRECTORY, filename_pattern="metrics.json"
    )
    logger.info(f"找到 {len(path_list)} 个插件配置文件，开始同步插件及模板")

    # 第一阶段：导入插件基础信息
    success_count, error_count = _import_plugins_from_files(path_list)

    # 第二阶段：加载数据到内存
    plugins_dict = _load_plugins_to_memory()
    all_config_templates, all_ui_templates = _load_templates_to_memory()

    # 第三阶段：收集需要处理的模板
    templates_data = _collect_templates_to_process(
        path_list, plugins_dict, all_config_templates, all_ui_templates
    )

    # 第四阶段：批量保存模板
    stats = _batch_save_templates(templates_data)

    # 输出统计信息
    logger.info(f"插件导入完成: 成功={success_count}, 失败={error_count}")
    logger.info(
        f"配置模板统计: 创建={stats['config_create']}, 更新={stats['config_update']}, 删除={stats['config_delete']}"
    )
    logger.info(
        f"UI 模板统计: 创建={stats['ui_create']}, 更新={stats['ui_update']}, 删除={stats['ui_delete']}"
    )

    # 第五阶段：清理已移除的内置插件
    _cleanup_removed_plugins(path_list)

    # 第六阶段：清理孤立的监控对象
    _cleanup_orphan_objects()

    # 第七阶段：清理空的内置指标分组
    _cleanup_empty_builtin_metric_groups()
