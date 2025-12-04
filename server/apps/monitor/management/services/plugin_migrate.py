import json
from pathlib import Path
from typing import Tuple, List

from apps.core.logger import monitor_logger as logger
from apps.monitor.constants.database import DatabaseConstants
from apps.monitor.constants.plugin import PluginConstants
from apps.monitor.services.plugin import MonitorPluginService
from apps.monitor.services.policy import PolicyService


def find_files_by_pattern(root_dir: str, filename_pattern: str = None, extension: str = None) -> List[str]:
    """
    通用文件查找函数，支持按文件名或扩展名过滤。

    路径格式: plugins/level1/level2/level3/*

    :param root_dir: 根目录路径
    :param filename_pattern: 目标文件名（精确匹配）
    :param extension: 文件扩展名（如 '.j2', '.json'）
    :return: 符合条件的文件完整路径列表
    """
    result = []
    root_path = Path(root_dir)

    if not root_path.exists() or not root_path.is_dir():
        logger.warning(f'目录不存在或不是目录: {root_dir}')
        return result

    try:
        # 递归遍历目录，最多4层（采集器/采集方式/具体插件/文件）
        for level1 in root_path.iterdir():
            if not level1.is_dir():
                continue
            for level2 in level1.iterdir():
                if not level2.is_dir():
                    continue
                for level3 in level2.iterdir():
                    if not level3.is_dir():
                        continue
                    for file_path in level3.iterdir():
                        if file_path.is_file():
                            # 按文件名过滤
                            if filename_pattern and file_path.name == filename_pattern:
                                result.append(str(file_path))
                            # 按扩展名过滤
                            elif extension and file_path.suffix == extension:
                                result.append(str(file_path))
    except Exception as e:
        logger.error(f'遍历目录失败: {root_dir}, 错误: {e}')

    return result


def parse_template_filename(filename: str) -> Tuple[str, str, str]:
    """
    解析模板文件名，提取 type、config_type、file_type。

    文件名格式: {type}.{config_type}.{file_type}.j2
    例如: cpu.child.toml.j2 -> type=cpu, config_type=child, file_type=toml
          oracle.base.yaml.j2 -> type=oracle, config_type=base, file_type=yaml

    :param filename: 模板文件名
    :return: (type, config_type, file_type) 元组
    """
    # 移除 .j2 后缀
    if not filename.endswith('.j2'):
        logger.warning(f'模板文件名不以 .j2 结尾: {filename}')
        return "", "", ""

    name_without_ext = filename[:-3]  # 比 replace 更高效
    parts = name_without_ext.split('.')

    if len(parts) < 3:
        logger.warning(f'模板文件名格式不正确（应为 type.config_type.file_type.j2）: {filename}')
        return "", "", ""

    # 格式: type.config_type.file_type
    return parts[0], parts[1], parts[2]


def extract_plugin_path_info(file_path: str) -> Tuple[str, str]:
    """
    从插件文件路径中提取采集器和采集方式信息。

    路径格式: .../plugins/采集器/采集方式/具体插件/文件名
    例如: apps/monitor/support-files/plugins/Telegraf/host/os/metrics.json

    :param file_path: 插件文件完整路径
    :return: (collector, collect_type) 元组
    """
    try:
        path = Path(file_path)
        parts = path.parts

        # 找到 plugins 目录的索引
        if 'plugins' in parts:
            plugins_idx = parts.index('plugins')
            # plugins 后面的第一个目录是采集器，第二个是采集方式
            if len(parts) > plugins_idx + 2:
                return parts[plugins_idx + 1], parts[plugins_idx + 2]
    except Exception as e:
        logger.warning(f'从路径提取插件信息失败: {file_path}, 错误: {e}')

    return "", ""


def migrate_plugin():
    """
    迁移插件及其配置模板和 UI 模板。

    设计思路：
    1. 扫描所有 metrics.json 文件
    2. 导入插件信息
    3. 同时导入该插件的配置模板（.j2 文件）
    4. 同时导入该插件的 UI 模板（UI.json 文件）
    5. 清理数据库中已不存在的模板

    性能优化：
    1. 预加载所有插件到内存，避免重复查询
    2. 按插件分组批量处理模板
    3. 使用 bulk_create 和 bulk_update 减少数据库交互
    4. 合并事务，减少事务开销
    """
    from django.db import transaction
    from apps.monitor.models import MonitorPlugin, MonitorPluginConfigTemplate, MonitorPluginUITemplate

    path_list = find_files_by_pattern(PluginConstants.DIRECTORY, filename_pattern="metrics.json")
    logger.info(f'找到 {len(path_list)} 个插件配置文件，开始同步插件及模板')

    success_count = 0
    error_count = 0

    total_config_create = 0
    total_config_update = 0
    total_config_delete = 0

    total_ui_create = 0
    total_ui_update = 0
    total_ui_delete = 0

    # ========== 性能优化：预加载所有插件到内存 ==========
    plugins_dict = {}  # {plugin_name: plugin_obj}

    # ========== 第一阶段：导入所有插件基础信息 ==========
    for file_path in path_list:
        try:
            # 读取插件配置
            plugin_data = json.loads(Path(file_path).read_text(encoding='utf-8'))

            # 从文件路径提取采集器和采集方式信息
            collector, collect_type = extract_plugin_path_info(file_path)
            plugin_data['collector'] = collector
            plugin_data['collect_type'] = collect_type

            # 重要：在调用 import_monitor_plugin 之前保存 plugin_name
            # 因为 import_monitor_plugin 内部会 pop('plugin')，导致键被移除
            plugin_name = plugin_data.get('plugin')

            # 导入插件基础信息
            MonitorPluginService.import_monitor_plugin(plugin_data)
            logger.info(f'导入插件成功: {plugin_name} ({collector}/{collect_type})')
            success_count += 1

        except Exception as e:
            logger.error(f'导入插件失败: {file_path}, 错误: {e}')
            import traceback
            logger.error(traceback.format_exc())
            error_count += 1

    # 一次性加载所有插件到内存
    for plugin in MonitorPlugin.objects.all():
        plugins_dict[plugin.name] = plugin

    logger.info(f'已加载 {len(plugins_dict)} 个插件到内存')

    # ========== 性能优化：预加载所有模板到内存 ==========
    # 按插件 ID 分组的配置模板
    all_config_templates = {}  # {plugin_id: {(type, config_type, file_type): template_obj}}
    for tpl in MonitorPluginConfigTemplate.objects.select_related('plugin').all():
        if tpl.plugin_id not in all_config_templates:
            all_config_templates[tpl.plugin_id] = {}
        key = (tpl.type, tpl.config_type, tpl.file_type)
        all_config_templates[tpl.plugin_id][key] = tpl

    # 按插件 ID 分组的 UI 模板
    all_ui_templates = {}  # {plugin_id: template_obj}
    for tpl in MonitorPluginUITemplate.objects.select_related('plugin').all():
        all_ui_templates[tpl.plugin_id] = tpl

    logger.info(f'已加载配置模板和 UI 模板到内存')

    # ========== 第二阶段：批量处理模板 ==========
    # 收集所有需要批量操作的数据
    config_templates_to_create = []
    config_templates_to_update = []
    config_templates_to_delete = []

    ui_templates_to_create = []
    ui_templates_to_update = []
    ui_templates_to_delete = []

    for file_path in path_list:
        try:
            # 读取插件配置
            plugin_data = json.loads(Path(file_path).read_text(encoding='utf-8'))
            plugin_name = plugin_data.get('plugin')

            # 从内存中获取插件对象
            plugin_obj = plugins_dict.get(plugin_name)
            if not plugin_obj:
                logger.warning(f'插件对象未找到: {plugin_name}，跳过模板导入')
                continue

            # 获取插件目录
            plugin_dir = Path(file_path).parent

            # ========== 处理配置模板 ==========
            # 收集该插件目录下的 .j2 模板文件
            file_templates = {}

            for j2_file in plugin_dir.glob('*.j2'):
                if not j2_file.is_file():
                    continue

                try:
                    # 解析文件名
                    type_name, config_type, file_type = parse_template_filename(j2_file.name)
                    if not type_name or not config_type or not file_type:
                        continue

                    # 读取模板内容
                    content = j2_file.read_text(encoding='utf-8')
                    template_key = (type_name, config_type, file_type)
                    file_templates[template_key] = content

                except Exception as e:
                    logger.error(f'读取模板文件失败: {j2_file}, 错误: {e}')

            # 获取数据库中该插件的所有配置模板
            db_templates = all_config_templates.get(plugin_obj.id, {})

            # 对比并收集需要操作的模板
            for template_key, content in file_templates.items():
                type_name, config_type, file_type = template_key

                if template_key in db_templates:
                    # 已存在，检查是否需要更新
                    db_template = db_templates[template_key]
                    if db_template.content != content:
                        db_template.content = content
                        config_templates_to_update.append(db_template)
                else:
                    # 不存在，需要创建
                    config_templates_to_create.append(
                        MonitorPluginConfigTemplate(
                            plugin=plugin_obj,
                            type=type_name,
                            config_type=config_type,
                            file_type=file_type,
                            content=content
                        )
                    )

            # 找出需要删除的模板
            for template_key, db_template in db_templates.items():
                if template_key not in file_templates:
                    config_templates_to_delete.append(db_template)

            # ========== 处理 UI 模板 ==========
            ui_file = plugin_dir / 'UI.json'
            db_ui_template = all_ui_templates.get(plugin_obj.id)

            if ui_file.exists() and ui_file.is_file():
                try:
                    ui_data = json.loads(ui_file.read_text(encoding='utf-8'))

                    if db_ui_template:
                        # 已存在，检查是否需要更新
                        if db_ui_template.content != ui_data:
                            db_ui_template.content = ui_data
                            ui_templates_to_update.append(db_ui_template)
                    else:
                        # 不存在，需要创建
                        ui_templates_to_create.append(
                            MonitorPluginUITemplate(
                                plugin=plugin_obj,
                                content=ui_data
                            )
                        )

                except (json.JSONDecodeError, Exception) as e:
                    logger.error(f'处理 UI 文件失败: {ui_file}, 错误: {e}')
            else:
                # UI.json 文件不存在
                if db_ui_template:
                    ui_templates_to_delete.append(db_ui_template)

        except Exception as e:
            logger.error(f'处理插件模板失败: {file_path}, 错误: {e}')
            import traceback
            logger.error(traceback.format_exc())

    # ========== 第三阶段：批量执行数据库操作 ==========
    with transaction.atomic():
        # 批量创建配置模板
        if config_templates_to_create:
            MonitorPluginConfigTemplate.objects.bulk_create(
                config_templates_to_create,
                batch_size=DatabaseConstants.MONITOR_OBJECT_BATCH_SIZE
            )
            total_config_create = len(config_templates_to_create)
            logger.info(f'批量创建配置模板: {total_config_create} 个')

        # 批量更新配置模板
        if config_templates_to_update:
            MonitorPluginConfigTemplate.objects.bulk_update(
                config_templates_to_update,
                ['content'],
                batch_size=DatabaseConstants.MONITOR_OBJECT_BATCH_SIZE
            )
            total_config_update = len(config_templates_to_update)
            logger.info(f'批量更新配置模板: {total_config_update} 个')

        # 批量删除配置模板
        if config_templates_to_delete:
            template_ids = [tpl.id for tpl in config_templates_to_delete]
            deleted_count = MonitorPluginConfigTemplate.objects.filter(id__in=template_ids).delete()[0]
            total_config_delete = deleted_count
            logger.info(f'批量删除配置模板: {total_config_delete} 个')

        # 批量创建 UI 模板
        if ui_templates_to_create:
            MonitorPluginUITemplate.objects.bulk_create(
                ui_templates_to_create,
                batch_size=DatabaseConstants.MONITOR_OBJECT_BATCH_SIZE
            )
            total_ui_create = len(ui_templates_to_create)
            logger.info(f'批量创建 UI 模板: {total_ui_create} 个')

        # 批量更新 UI 模板
        if ui_templates_to_update:
            MonitorPluginUITemplate.objects.bulk_update(
                ui_templates_to_update,
                ['content'],
                batch_size=DatabaseConstants.MONITOR_OBJECT_BATCH_SIZE
            )
            total_ui_update = len(ui_templates_to_update)
            logger.info(f'批量更新 UI 模板: {total_ui_update} 个')

        # 批量删除 UI 模板
        if ui_templates_to_delete:
            template_ids = [tpl.id for tpl in ui_templates_to_delete]
            deleted_count = MonitorPluginUITemplate.objects.filter(id__in=template_ids).delete()[0]
            total_ui_delete = deleted_count
            logger.info(f'批量删除 UI 模板: {total_ui_delete} 个')

    logger.info(f'插件导入完成: 成功={success_count}, 失败={error_count}')
    logger.info(
        f'配置模板统计: 创建={total_config_create}, 更新={total_config_update}, 删除={total_config_delete}'
    )
    logger.info(
        f'UI 模板统计: 创建={total_ui_create}, 更新={total_ui_update}, 删除={total_ui_delete}'
    )


def migrate_config_templates():
    """
    已合并到 migrate_plugin 中，保留此函数以兼容旧代码。
    """
    logger.warning('migrate_config_templates 已合并到 migrate_plugin 中，此调用将被忽略')


def migrate_ui_templates():
    """
    已合并到 migrate_plugin 中，保留此函数以兼容旧代码。
    """
    logger.warning('migrate_ui_templates 已合并到 migrate_plugin 中，此调用将被忽略')


def migrate_policy():
    """
    迁移策略。

    优化：使用统一的文件查找函数
    """
    path_list = find_files_by_pattern(PluginConstants.DIRECTORY, filename_pattern="policy.json")
    logger.info(f'找到 {len(path_list)} 个策略配置文件')

    success_count = 0
    error_count = 0

    for file_path in path_list:
        try:
            policy_data = json.loads(Path(file_path).read_text(encoding='utf-8'))
            PolicyService.import_monitor_policy(policy_data)
            logger.info(f'导入策略成功: {file_path}')
            success_count += 1

        except Exception as e:
            logger.error(f'导入策略失败: {file_path}, 错误: {e}')
            error_count += 1

    logger.info(f'策略导入完成: 成功={success_count}, 失败={error_count}')


def migrate_default_order():
    """
    初始化默认排序。

    只初始化 order=999（默认值）的分类和对象。

    优化：使用 bulk_update 批量更新
    """
    try:
        from django.db import transaction
        from apps.monitor.constants.monitor_object import MonitorObjConstants
        from apps.monitor.models import MonitorObjectType, MonitorObject

        with transaction.atomic():
            # 找出所有需要初始化的分类（order=999）
            uninit_types = set(MonitorObjectType.objects.filter(order=999).values_list('id', flat=True))

            # 找出所有需要初始化的对象（order=999）
            uninit_objects = {obj.id: obj for obj in MonitorObject.objects.filter(order=999).select_related('type')}

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
                    for obj_id, obj in uninit_objects.items():
                        if obj.name == name and obj.type_id == type_id:
                            obj.order = name_idx
                            object_updates.append(obj)

            # 批量更新
            if type_updates:
                MonitorObjectType.objects.bulk_update(
                    type_updates,
                    ['order'],
                    batch_size=DatabaseConstants.MONITOR_OBJECT_BATCH_SIZE
                )
                logger.info(f'更新了 {len(type_updates)} 个分类的排序')

            if object_updates:
                MonitorObject.objects.bulk_update(
                    object_updates,
                    ['order'],
                    batch_size=DatabaseConstants.MONITOR_OBJECT_BATCH_SIZE
                )
                logger.info(f'更新了 {len(object_updates)} 个对象的排序')

    except Exception as e:
        logger.error(f'初始化默认排序失败: {e}')
        raise
