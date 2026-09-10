import json
import re
import traceback
from copy import deepcopy
from pathlib import Path

from apps.core.logger import monitor_logger as logger
from apps.monitor.constants.database import DatabaseConstants
from apps.monitor.constants.plugin import PluginConstants
from apps.monitor.management.utils import extract_plugin_path_info, find_files_by_pattern, parse_template_filename
from apps.monitor.services.plugin import MonitorPluginService
from apps.monitor.services.plugin_import_bulk import prepare_plugin_import_plan
from apps.monitor.utils.snmp_ifmib_capability import IFMIB_METRIC_CATALOG, is_ifmib_capable_plugin_data
from apps.monitor.utils.snmp_interface_template import COMMON_IFMIB_TABLE_PATH
from apps.rpc.node_mgmt import NodeMgmt

TEMPLATE_COLLECT_TYPE_PATTERN = re.compile(r"""collect_type\s*=\s*["']([^"']+)["']""")
REMOTE_HOST_METRICS_MODULES = ("cpu", "mem", "disk", "diskio", "net", "processes", "system")
REMOTE_HOST_METRICS_MODULES_CSV = ",".join(REMOTE_HOST_METRICS_MODULES)
REMOTE_HOST_CONFIG_TYPES = ("host", "windows_wmi")
METRICS_MODULES_TOML_LINE_PATTERN = re.compile(r'(?m)^(\s*metrics_modules\s*=\s*)"[^"\n]*"')
LOCAL_TEMPLATE_ASSET_PATTERN = re.compile(r"(?m)^[ \t]*# @bk_include_file (?P<path>\S+)[ \t]*$")
COMMON_IFMIB_TABLE_DIRECTIVE = "# @bk_include_ifmib_table"


# IF-MIB 是所有 Network Device SNMP 模板共享的采集契约。此处只维护一次指标目录，
# 导入时合并到每个厂商模板，避免为了显示指标而新增一个可被用户接入的公共插件。
_IFMIB_METRICS_BY_INSTANCE_TYPE = {}


def _build_common_ifmib_metrics(instance_type):
    """Build the complete public IF-MIB metric catalog for one runtime object."""
    cached = _IFMIB_METRICS_BY_INSTANCE_TYPE.get(instance_type)
    if cached is not None:
        return deepcopy(cached)
    metrics = []
    interface_dimensions = [
        {"name": "ifIndex", "description": "ifIndex"},
        {"name": "ifDescr", "description": "ifDescr"},
    ]
    for group, name, display_name, data_type, unit, description in IFMIB_METRIC_CATALOG:
        if name.startswith("device_total_"):
            direction = "In" if name.endswith("incoming_traffic") else "Out"
            query = (
                f"sum(rate(interface_ifHC{direction}Octets{{instance_type='{instance_type}', __$labels__}}[5m]) "
                f"or rate(interface_if{direction}Octets{{instance_type='{instance_type}', __$labels__}}[5m])) by (instance_id)"
            )
            dimensions = []
        elif name == "interface_ifSpeed":
            query = (
                f"(interface_ifHighSpeed{{instance_type='{instance_type}', __$labels__}} > 0) * 1000000 "
                f"or interface_ifSpeed{{instance_type='{instance_type}', __$labels__}}"
            )
            dimensions = interface_dimensions
        elif name in {"interface_ifAdminStatus", "interface_ifOperStatus"}:
            query = f"{name}{{instance_type='{instance_type}', __$labels__}}"
            dimensions = interface_dimensions
        elif name in {"interface_ifInUcastPkts", "interface_ifOutUcastPkts"}:
            direction = "In" if "InUcast" in name else "Out"
            query = (
                f"rate(interface_ifHC{direction}UcastPkts{{instance_type='{instance_type}', __$labels__}}[5m]) "
                f"or rate({name}{{instance_type='{instance_type}', __$labels__}}[5m])"
            )
            dimensions = interface_dimensions
        else:
            query = f"rate({name}{{instance_type='{instance_type}', __$labels__}}[5m])"
            dimensions = interface_dimensions
        metrics.append(
            {
                "metric_group": group,
                "name": name,
                "query": query,
                "display_name": display_name,
                "data_type": data_type,
                "unit": unit,
                "dimensions": dimensions,
                "instance_id_keys": ["instance_id"],
                "description": description,
                "is_ifmib": True,
            }
        )
    _IFMIB_METRICS_BY_INSTANCE_TYPE[instance_type] = metrics
    return deepcopy(metrics)


def merge_common_ifmib_metrics(plugin_data):
    """Inject the internal IF-MIB metric catalog into every Network Device SNMP template."""
    result = deepcopy(plugin_data)
    if not is_ifmib_capable_plugin_data(result):
        return result

    common_metrics = _build_common_ifmib_metrics(re.sub(r"(?<!^)(?=[A-Z])", "_", result["name"]).lower())
    common_metrics_by_name = {metric["name"]: metric for metric in common_metrics}
    merged_metrics = []
    existing_common_names = set()
    for metric in result.get("metrics", []):
        metric_name = metric.get("name")
        if metric_name in common_metrics_by_name:
            if metric_name in existing_common_names:
                continue
            metric = {**common_metrics_by_name[metric_name]}
            existing_common_names.add(metric_name)
        merged_metrics.append(metric)
    merged_metrics.extend(metric for metric in common_metrics if metric["name"] not in existing_common_names)
    result["metrics"] = merged_metrics
    return result


class PluginIdentityValidationError(ValueError):
    """Raised when plugin metadata and local template identity disagree."""


def _expand_local_template_assets(content: str, plugin_dir: Path) -> str:
    """将插件同目录资源嵌入配置，保持下发给采集端的配置自包含。"""
    plugin_root = plugin_dir.resolve()

    def replace(match):
        relative_path = Path(match.group("path"))
        asset_path = (plugin_root / relative_path).resolve()
        if relative_path.is_absolute() or not asset_path.is_relative_to(plugin_root):
            raise ValueError(f"非法的插件资源路径: {relative_path}")
        if not asset_path.is_file():
            raise ValueError(f"插件资源不存在: {relative_path}")
        return asset_path.read_text(encoding="utf-8").rstrip("\n")

    expanded = LOCAL_TEMPLATE_ASSET_PATTERN.sub(replace, content)
    if COMMON_IFMIB_TABLE_DIRECTIVE not in expanded:
        return expanded
    try:
        common_ifmib_table = COMMON_IFMIB_TABLE_PATH.read_text(encoding="utf-8").rstrip("\n")
    except OSError as exc:
        raise ValueError(f"通用 IF-MIB 模板不存在: {COMMON_IFMIB_TABLE_PATH}") from exc
    return expanded.replace(COMMON_IFMIB_TABLE_DIRECTIVE, common_ifmib_table)


def _clean_identity_value(value):
    if value is None:
        return ""
    return str(value).strip()


def _resolve_plugin_identity(file_path, plugin_data):
    """Resolve runtime identity from explicit metadata, then legacy path fallback."""
    collector_from_path, collect_type_from_path = extract_plugin_path_info(file_path)

    collector = _clean_identity_value(plugin_data.get("collector")) or collector_from_path
    collect_type = _clean_identity_value(plugin_data.get("collect_type")) or collect_type_from_path

    plugin_data["collector"] = collector
    plugin_data["collect_type"] = collect_type
    return collector, collect_type


def _validate_ui_identity(plugin_dir, collector, collect_type):
    ui_file = plugin_dir / "UI.json"
    if not ui_file.exists() or not ui_file.is_file():
        return

    ui_data = json.loads(ui_file.read_text(encoding="utf-8"))
    expected_values = {
        "collector": collector,
        "collect_type": collect_type,
    }
    for field, expected in expected_values.items():
        declared = _clean_identity_value(ui_data.get(field))
        if declared and declared != expected:
            raise PluginIdentityValidationError(f"{ui_file} {field} mismatch: resolved={expected}, declared={declared}")


def _validate_template_identity(plugin_dir, collect_type):
    for j2_file in sorted(plugin_dir.glob("*.j2")):
        if not j2_file.is_file():
            continue

        content = j2_file.read_text(encoding="utf-8")
        for match in TEMPLATE_COLLECT_TYPE_PATTERN.finditer(content):
            declared = _clean_identity_value(match.group(1))
            if not declared or "{" in declared or "}" in declared:
                continue
            if declared != collect_type:
                raise PluginIdentityValidationError(f"{j2_file} collect_type mismatch: resolved={collect_type}, declared={declared}")


def _validate_plugin_identity(file_path, collector, collect_type):
    plugin_dir = Path(file_path).parent
    _validate_ui_identity(plugin_dir, collector, collect_type)
    _validate_template_identity(plugin_dir, collect_type)


def _collect_file_supplementary_indicators(plugin_data, supplementary_map):
    """收集插件文件中定义的对象补充指标"""

    def _merge_object_indicators(object_data):
        object_name = object_data.get("name")
        if not object_name:
            return

        if object_name not in supplementary_map:
            supplementary_map[object_name] = set()

        supplementary_map[object_name].update(object_data.get("supplementary_indicators", []))

    if plugin_data.get("is_compound_object"):
        for object_data in plugin_data.get("objects", []):
            _merge_object_indicators(object_data)
        return

    _merge_object_indicators(plugin_data)


def _import_plugins_from_files(path_list):
    """导入插件基础信息"""
    success_count = 0
    error_count = 0
    supplementary_map = {}
    documents = []

    for file_path in path_list:
        try:
            plugin_data = json.loads(Path(file_path).read_text(encoding="utf-8"))
            _collect_file_supplementary_indicators(plugin_data, supplementary_map)

            collector, collect_type = _resolve_plugin_identity(file_path, plugin_data)
            _validate_plugin_identity(file_path, collector, collect_type)
            plugin_data = merge_common_ifmib_metrics(plugin_data)

            plugin_name = plugin_data.get("plugin")
            plugin_data["_mark_objects_builtin"] = True
            # 新 plugin 首次导入时,自动生成 language/ 空骨架(check_plugin_languages CI 要求)
            MonitorPluginService._ensure_language_skeleton(Path(file_path).parent, plugin_name)
            prepare_plugin_import_plan(plugin_data)
            documents.append(plugin_data)
            logger.info(f"导入插件成功: {plugin_name} ({collector}/{collect_type})")
            success_count += 1

        except Exception as e:
            logger.error(f"导入插件失败: {file_path}, 错误: {e}")
            logger.error(traceback.format_exc())
            error_count += 1

    if documents:
        try:
            MonitorPluginService.import_monitor_plugins(documents)
        except Exception as e:
            logger.error("批量导入插件失败，已回滚本次插件写入: %s", e)
            logger.error(traceback.format_exc())
            error_count += success_count
            success_count = 0
            # 整批 atomic 写失败不得伪装成初始化成功，否则 batch_init 绿但插件仍旧。
            raise

    return success_count, error_count, supplementary_map


def _reconcile_supplementary_indicators(supplementary_map):
    """根据插件定义统一重算对象补充指标，清理脏数据"""
    from apps.monitor.models import MonitorObject

    if not supplementary_map:
        logger.info("未收集到 supplementary_indicators，跳过重算")
        return 0

    monitor_objects = list(MonitorObject.objects.filter(name__in=supplementary_map.keys()))
    objects_to_update = []

    for monitor_object in monitor_objects:
        indicator_names = sorted(supplementary_map.get(monitor_object.name, set()))
        if monitor_object.supplementary_indicators == indicator_names:
            continue

        monitor_object.supplementary_indicators = indicator_names
        objects_to_update.append(monitor_object)

    if not objects_to_update:
        logger.info("supplementary_indicators 无需重算")
        return 0

    MonitorObject.objects.bulk_update(
        objects_to_update,
        ["supplementary_indicators"],
        batch_size=DatabaseConstants.MONITOR_OBJECT_BATCH_SIZE,
    )
    logger.info(f"已重算 {len(objects_to_update)} 个监控对象的 supplementary_indicators")
    return len(objects_to_update)


def _replace_remote_host_metrics_modules_line(content):
    if not isinstance(content, str):
        return content, False

    changed = False

    def replace(match):
        nonlocal changed
        replacement = f'{match.group(1)}"{REMOTE_HOST_METRICS_MODULES_CSV}"'
        if match.group(0) == replacement:
            return match.group(0)
        changed = True
        return replacement

    updated_content = METRICS_MODULES_TOML_LINE_PATTERN.sub(replace, content)
    return updated_content, changed


def _sync_remote_host_metrics_modules():
    from apps.monitor.models import CollectConfig

    config_ids = list(
        CollectConfig.objects.filter(
            collect_type="http",
            config_type__in=REMOTE_HOST_CONFIG_TYPES,
            is_child=True,
        ).values_list("id", flat=True)
    )
    if not config_ids:
        logger.info("未发现需要同步采集模块的主机远程子配置")
        return 0

    node_mgmt = NodeMgmt()
    try:
        child_configs = node_mgmt.get_child_configs_by_ids(config_ids)
    except Exception as e:
        logger.error(f"获取主机远程子配置失败，跳过采集模块同步: {e}")
        return 0

    updated_count = 0
    for child_config in child_configs or []:
        config_id = child_config.get("id")
        updated_content, changed = _replace_remote_host_metrics_modules_line(child_config.get("content"))
        if not config_id or not changed:
            continue

        try:
            node_mgmt.update_child_config_content(config_id, updated_content)
            updated_count += 1
        except Exception as e:
            logger.error(f"同步主机远程子配置采集模块失败: config_id={config_id}, 错误={e}")

    return updated_count


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
    all_ui_templates = {tpl.plugin_id: tpl for tpl in MonitorPluginUITemplate.objects.select_related("plugin").all()}

    logger.info("已加载配置模板和 UI 模板到内存")
    return all_config_templates, all_ui_templates


def _process_config_templates(plugin_dir, plugin_obj, db_templates):
    """处理配置模板：收集需要创建、更新、删除的模板"""
    from apps.monitor.models import MonitorPluginConfigTemplate

    to_create = []
    to_update = []
    file_templates = {}
    failed_template_keys = set()

    # 收集文件中的模板
    for j2_file in plugin_dir.glob("*.j2"):
        if not j2_file.is_file():
            continue
        template_key = None
        try:
            type_name, config_type, file_type = parse_template_filename(j2_file.name)
            if not type_name or not config_type or not file_type:
                continue

            template_key = (type_name, config_type, file_type)
            content = _expand_local_template_assets(
                j2_file.read_text(encoding="utf-8"),
                plugin_dir,
            )
            file_templates[template_key] = content
        except Exception as e:
            logger.error(f"读取模板文件失败: {j2_file}, 错误: {e}")
            if template_key:
                # 单个文件失败时保留数据库中的最后可用版本，避免初始化过程产生破坏性删除。
                failed_template_keys.add(template_key)

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
        if template_key not in file_templates and template_key not in failed_template_keys
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
            # SNMP：入库前合并接口过滤字段，避免仅依赖读时 enrich
            if getattr(plugin_obj, "collect_type", None) == "snmp" or plugin_dir.parent.name == "snmp":
                from apps.monitor.utils.snmp_interface_template import merge_snmp_interface_filter_ui

                ui_data = merge_snmp_interface_filter_ui(ui_data, plugin=plugin_obj) or ui_data

            if db_ui_template:
                if db_ui_template.content != ui_data:
                    db_ui_template.content = ui_data
                    to_update.append(db_ui_template)
            else:
                to_create.append(MonitorPluginUITemplate(plugin=plugin_obj, content=ui_data))
        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"处理 UI 文件失败: {ui_file}, 错误: {e}")
    else:
        if db_ui_template:
            to_delete.append(db_ui_template)

    return to_create, to_update, to_delete


def _collect_templates_to_process(path_list, plugins_dict, all_config_templates, all_ui_templates):
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
            create, update, delete = _process_config_templates(plugin_dir, plugin_obj, db_templates)
            config_templates_to_create.extend(create)
            config_templates_to_update.extend(update)
            config_templates_to_delete.extend(delete)

            # 处理 UI 模板
            create, update, delete = _process_ui_templates(plugin_dir, plugin_obj, db_ui_template)
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
            MonitorPluginConfigTemplate.objects.bulk_create(config_create, batch_size=DatabaseConstants.MONITOR_OBJECT_BATCH_SIZE)
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
            stats["config_delete"] = MonitorPluginConfigTemplate.objects.filter(id__in=template_ids).delete()[0]
            logger.info(f"批量删除配置模板: {stats['config_delete']} 个")

        # UI 模板操作
        if ui_create:
            MonitorPluginUITemplate.objects.bulk_create(ui_create, batch_size=DatabaseConstants.MONITOR_OBJECT_BATCH_SIZE)
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
            stats["ui_delete"] = MonitorPluginUITemplate.objects.filter(id__in=template_ids).delete()[0]
            logger.info(f"批量删除 UI 模板: {stats['ui_delete']} 个")

    return stats


def _collect_ondisk_builtin_plugin_names(path_list):
    """从仍存在的 metrics.json 收集内置插件名，作为删除对照的磁盘 allowlist。"""
    builtin_plugin_names = set()
    for file_path in path_list:
        try:
            plugin_data = json.loads(Path(file_path).read_text(encoding="utf-8"))
        except Exception as exc:
            logger.error(
                "event=read_ondisk_plugin_name_failed file_path=%s failed_stage=collect_ondisk_plugin_names error_type=%s",
                file_path,
                type(exc).__name__,
            )
            continue
        plugin_name = plugin_data.get("plugin")
        if plugin_name:
            builtin_plugin_names.add(plugin_name)
    return builtin_plugin_names


def _cleanup_removed_plugins(path_list):
    """删除 support-files 中已消失的内置插件及其 UI/配置模板。

    只对照磁盘 metrics.json 的 plugin 名 allowlist，且仅处理 is_pre=True。
    自定义插件（is_pre=False）不在此清理。allowlist 为空时跳过，避免误删。
    例如 Telegraf/http/host_aix/ 删除后，DB 中的 Host AIX 会在一次 plugin_init 后消失；
    Host AIX Remote 仍在磁盘上，不会被删。
    """
    from django.db import transaction

    from apps.monitor.models import MonitorPlugin, MonitorPluginConfigTemplate, MonitorPluginUITemplate
    from apps.monitor.models.monitor_policy import PolicyTemplate

    builtin_plugin_names = _collect_ondisk_builtin_plugin_names(path_list)
    if not builtin_plugin_names:
        logger.warning("event=skip_removed_plugin_cleanup reason=empty_ondisk_allowlist failed_stage=cleanup_removed_plugins")
        return

    removed_plugins = MonitorPlugin.objects.filter(is_pre=True).exclude(name__in=builtin_plugin_names)
    if not removed_plugins.exists():
        return

    removed_ids = list(removed_plugins.values_list("id", flat=True))
    removed_names = list(removed_plugins.values_list("name", flat=True))
    try:
        with transaction.atomic():
            ui_deleted, _ = MonitorPluginUITemplate.objects.filter(plugin_id__in=removed_ids).delete()
            config_deleted, _ = MonitorPluginConfigTemplate.objects.filter(plugin_id__in=removed_ids).delete()
            policy_deleted, _ = PolicyTemplate.objects.filter(plugin_id__in=removed_ids).delete()
            plugin_deleted, _ = removed_plugins.delete()
    except Exception:
        logger.exception(
            "event=cleanup_removed_plugins_failed plugin_count=%s failed_stage=cleanup_removed_plugins error_type=delete_error",
            len(removed_ids),
        )
        raise

    logger.info(
        "event=cleanup_removed_plugins plugin_count=%s ui_template_count=%s "
        "config_template_count=%s policy_template_count=%s plugin_delete_count=%s names=%s",
        len(removed_ids),
        ui_deleted,
        config_deleted,
        policy_deleted,
        plugin_deleted,
        ",".join(removed_names),
    )


def _cleanup_orphan_objects():
    """删除没有关联插件的监控对象"""
    from django.db import transaction
    from django.db.models import Count

    from apps.monitor.models import MonitorObject

    orphan_objects = MonitorObject.objects.annotate(plugin_count=Count("monitorplugin")).filter(plugin_count=0)

    if orphan_objects.exists():
        orphan_count = orphan_objects.count()
        orphan_names = list(orphan_objects.values_list("name", flat=True))

        with transaction.atomic():
            orphan_objects.delete()

        logger.info(f"已删除 {orphan_count} 个没有关联插件的监控对象: {orphan_names}")
        logger.info("关联的指标组、指标、监控实例已自动级联删除")


def _cleanup_empty_builtin_metric_groups():
    """删除没有指标的内置指标分组"""
    from django.db import transaction
    from django.db.models import Count

    from apps.monitor.models import MetricGroup

    empty_groups = MetricGroup.objects.filter(is_pre=True).annotate(metric_count=Count("metric")).filter(metric_count=0)

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
    3. 按磁盘 metrics.json allowlist 清理已消失的内置插件（含 UI/配置模板）
    4. 清理孤立的监控对象
    """
    # 社区版插件
    path_list = find_files_by_pattern(PluginConstants.DIRECTORY, filename_pattern="metrics.json")
    # 商业版插件
    enterprise_path_list = find_files_by_pattern(PluginConstants.ENTERPRISE_DIRECTORY, filename_pattern="metrics.json")
    path_list.extend(enterprise_path_list)
    logger.info(f"找到 {len(path_list)} 个插件配置文件，开始同步插件及模板")

    # 第一阶段：导入插件基础信息
    success_count, error_count, supplementary_map = _import_plugins_from_files(path_list)

    # 第二阶段：加载数据到内存
    plugins_dict = _load_plugins_to_memory()
    all_config_templates, all_ui_templates = _load_templates_to_memory()

    # 第三阶段：收集需要处理的模板
    templates_data = _collect_templates_to_process(path_list, plugins_dict, all_config_templates, all_ui_templates)

    # 第四阶段：批量保存模板
    stats = _batch_save_templates(templates_data)
    remote_host_synced_count = _sync_remote_host_metrics_modules()

    # 输出统计信息
    logger.info(f"插件导入完成: 成功={success_count}, 失败={error_count}")
    logger.info(f"配置模板统计: 创建={stats['config_create']}, 更新={stats['config_update']}, 删除={stats['config_delete']}")
    logger.info(f"UI 模板统计: 创建={stats['ui_create']}, 更新={stats['ui_update']}, 删除={stats['ui_delete']}")
    logger.info(f"主机远程采集模块同步完成: 更新={remote_host_synced_count}")

    # 第五阶段：清理已移除的内置插件
    _cleanup_removed_plugins(path_list)

    # 第六阶段：清理孤立的监控对象
    _cleanup_orphan_objects()

    # 第七阶段：统一重算补充指标，清理历史脏数据
    reconciled_count = _reconcile_supplementary_indicators(supplementary_map)

    # 第八阶段：清理空的内置指标分组
    _cleanup_empty_builtin_metric_groups()
    logger.info(f"补充指标重算完成: 更新={reconciled_count}")

    # 插件目录 / UI.json 变更后使进程内读盘缓存失效。
    from apps.monitor.services.plugin_guide import PluginGuideService
    from apps.monitor.services.ui_template_locale import clear_ui_file_overlay_cache

    PluginGuideService.clear_plugin_dir_cache()
    clear_ui_file_overlay_cache()
    logger.info("插件目录与 UI 模板磁盘缓存已清理")
