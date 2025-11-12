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


def migrate_config_templates():
    """
    迁移配置模板到数据库。

    扫描所有 .j2 模板文件，解析文件名和路径信息，导入到 MonitorPluginConfigTemplate 表中。

    优化点：
    1. 预加载所有插件到内存，避免循环中重复查询数据库
    2. 批量创建/更新，提升性能
    3. 使用 Path 对象简化路径操作
    """
    from django.db import transaction
    from apps.monitor.models import MonitorPlugin, MonitorPluginConfigTemplate

    # 查找所有模板文件
    template_files = find_files_by_pattern(PluginConstants.DIRECTORY, extension='.j2')
    logger.info(f'找到 {len(template_files)} 个模板文件')

    if not template_files:
        logger.warning('未找到任何模板文件')
        return

    # 优化：预加载所有插件到内存，建立索引
    plugins_dict = {}
    for plugin in MonitorPlugin.objects.all():
        key = (plugin.collector, plugin.collect_type)
        plugins_dict[key] = plugin

    logger.info(f'加载了 {len(plugins_dict)} 个插件到内存')

    success_count = 0
    skip_count = 0
    error_count = 0
    templates_to_process = []

    # 第一步：解析所有文件，准备数据
    for file_path in template_files:
        try:
            # 提取路径信息
            collector, collect_type = extract_plugin_path_info(file_path)
            if not collector or not collect_type:
                logger.warning(f'无法从路径提取信息，跳过: {file_path}')
                skip_count += 1
                continue

            # 解析文件名
            filename = Path(file_path).name
            type_name, config_type, file_type = parse_template_filename(filename)
            if not type_name or not config_type or not file_type:
                logger.warning(f'无法解析文件名，跳过: {filename}')
                skip_count += 1
                continue

            # 从内存中查找插件
            plugin_key = (collector, collect_type)
            plugin = plugins_dict.get(plugin_key)
            if not plugin:
                logger.warning(f'插件不存在: collector={collector}, collect_type={collect_type}, 跳过: {file_path}')
                skip_count += 1
                continue

            # 读取模板内容
            try:
                content = Path(file_path).read_text(encoding='utf-8')
            except Exception as e:
                logger.error(f'读取文件失败: {file_path}, 错误: {e}')
                error_count += 1
                continue

            # 准备模板数据
            templates_to_process.append({
                'plugin': plugin,
                'type': type_name,
                'config_type': config_type,
                'file_type': file_type,
                'content': content,
                'file_path': file_path
            })

        except Exception as e:
            logger.error(f'处理模板文件失败: {file_path}, 错误: {e}')
            error_count += 1

    # 第二步：批量处理数据库操作
    with transaction.atomic():
        for template_data in templates_to_process:
            try:
                plugin = template_data['plugin']
                type_name = template_data['type']
                config_type = template_data['config_type']
                file_type = template_data['file_type']
                content = template_data['content']

                # 使用 update_or_create 确保幂等性
                template, created = MonitorPluginConfigTemplate.objects.update_or_create(
                    plugin=plugin,
                    type=type_name,
                    config_type=config_type,
                    file_type=file_type,
                    defaults={'content': content}
                )

                action = '创建' if created else '更新'
                logger.info(f'{action}模板: {plugin.collector}/{plugin.collect_type}/{type_name}.{config_type}.{file_type}')
                success_count += 1

            except Exception as e:
                logger.error(f'保存模板失败: {template_data["file_path"]}, 错误: {e}')
                error_count += 1

    logger.info(f'模板导入完成: 成功={success_count}, 跳过={skip_count}, 失败={error_count}')


def migrate_ui_templates():
    """
    迁移 UI 模板到数据库。

    扫描所有 UI.json 文件，导入到 MonitorPluginUITemplate 表中。

    优化：使用统一的文件查找函数和预加载插件
    """
    from django.db import transaction
    from apps.monitor.models import MonitorPlugin, MonitorPluginUITemplate

    path_list = find_files_by_pattern(PluginConstants.DIRECTORY, filename_pattern="UI.json")
    logger.info(f'找到 {len(path_list)} 个 UI 模板配置文件')

    if not path_list:
        logger.warning('未找到任何 UI 模板文件')
        return

    # 优化：预加载所有插件到内存
    plugins_dict = {}
    for plugin in MonitorPlugin.objects.all():
        key = (plugin.collector, plugin.collect_type)
        plugins_dict[key] = plugin

    logger.info(f'加载了 {len(plugins_dict)} 个插件到内存')

    success_count = 0
    skip_count = 0
    error_count = 0

    with transaction.atomic():
        for file_path in path_list:
            try:
                # 读取 UI 模板内容
                ui_data = json.loads(Path(file_path).read_text(encoding='utf-8'))

                # 从文件路径提取采集器和采集方式信息
                collector, collect_type = extract_plugin_path_info(file_path)
                if not collector or not collect_type:
                    logger.warning(f'无法从路径提取信息，跳过: {file_path}')
                    skip_count += 1
                    continue

                # 从内存中查找插件
                plugin_key = (collector, collect_type)
                plugin = plugins_dict.get(plugin_key)
                if not plugin:
                    logger.warning(f'插件不存在: collector={collector}, collect_type={collect_type}, 跳过: {file_path}')
                    skip_count += 1
                    continue

                # 创建或更新 UI 模板
                ui_template, created = MonitorPluginUITemplate.objects.update_or_create(
                    plugin=plugin,
                    defaults={'content': ui_data}
                )

                action = '创建' if created else '更新'
                logger.info(f'{action} UI 模板: {collector}/{collect_type}')
                success_count += 1

            except json.JSONDecodeError as e:
                logger.error(f'JSON 解析失败: {file_path}, 错误: {e}')
                error_count += 1
            except Exception as e:
                logger.error(f'导入 UI 模板失败: {file_path}, 错误: {e}')
                error_count += 1

    logger.info(f'UI 模板导入完成: 成功={success_count}, 跳过={skip_count}, 失败={error_count}')


def migrate_plugin():
    """
    迁移插件。

    优化：使用统一的文件查找函数
    """
    path_list = find_files_by_pattern(PluginConstants.DIRECTORY, filename_pattern="metrics.json")
    logger.info(f'找到 {len(path_list)} 个插件配置文件')

    success_count = 0
    error_count = 0

    for file_path in path_list:
        try:
            plugin_data = json.loads(Path(file_path).read_text(encoding='utf-8'))

            # 从文件路径提取采集器和采集方式信息
            collector, collect_type = extract_plugin_path_info(file_path)
            plugin_data['collector'] = collector
            plugin_data['collect_type'] = collect_type

            MonitorPluginService.import_monitor_plugin(plugin_data)
            logger.info(f'导入插件成功: {collector}/{collect_type}')
            success_count += 1

        except Exception as e:
            logger.error(f'导入插件失败: {file_path}, 错误: {e}')
            error_count += 1

    logger.info(f'插件导入完成: 成功={success_count}, 失败={error_count}')


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
