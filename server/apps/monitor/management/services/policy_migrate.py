import json
from pathlib import Path

from apps.core.logger import monitor_logger as logger
from apps.monitor.constants.plugin import PluginConstants
from apps.monitor.management.utils import find_files_by_pattern
from apps.monitor.models import MonitorObject, MonitorPlugin
from apps.monitor.services.policy import PolicyService


def _is_legacy_policy_document(policy_data):
    """识别仅供旧版策略引擎使用、无法转换为内置模板的配置。"""
    return policy_data == {} or (
        isinstance(policy_data, dict)
        and "policy" in policy_data
        and not policy_data.get("object")
        and not policy_data.get("plugin")
    )


def _filter_unavailable_policy_documents(documents):
    valid_documents = []
    skipped_count = 0
    seen_pairs = set()
    seen_keys = set()
    for file_path, data in documents:
        try:
            normalized = PolicyService._normalize_builtin_documents([data])
        except Exception as e:
            logger.warning("跳过不符合内置模板契约的策略配置: %s, 错误: %s", file_path, e)
            skipped_count += 1
            continue
        pair = (str(data["object"]).strip(), str(data["plugin"]).strip())
        keys = {item["key"] for item in normalized}
        if pair in seen_pairs or keys & seen_keys:
            logger.warning("跳过与先前文件重复定义内置模板的策略配置: %s", file_path)
            skipped_count += 1
            continue
        seen_pairs.add(pair)
        seen_keys.update(keys)
        valid_documents.append((file_path, data))

    object_names = {str(data["object"]).strip() for _, data in valid_documents}
    plugin_names = {str(data["plugin"]).strip() for _, data in valid_documents}
    available_objects = set(MonitorObject.objects.filter(name__in=object_names).values_list("name", flat=True))
    available_plugins = set(MonitorPlugin.objects.filter(name__in=plugin_names).values_list("name", flat=True))

    available_documents = []
    for file_path, data in valid_documents:
        object_name = str(data["object"]).strip()
        plugin_name = str(data["plugin"]).strip()
        if object_name not in available_objects or plugin_name not in available_plugins:
            logger.warning(
                "跳过引用未导入监控对象或插件的策略配置: %s, object=%s, plugin=%s",
                file_path,
                object_name,
                plugin_name,
            )
            skipped_count += 1
            continue
        available_documents.append(data)
    return available_documents, skipped_count


def migrate_policy():
    """
    迁移策略。

    优化：使用统一的文件查找函数
    """
    # 社区版策略
    path_list = find_files_by_pattern(PluginConstants.DIRECTORY, filename_pattern="policy.json")
    # 商业版策略
    enterprise_path_list = find_files_by_pattern(PluginConstants.ENTERPRISE_DIRECTORY, filename_pattern="policy.json")
    path_list.extend(enterprise_path_list)
    logger.info(f'找到 {len(path_list)} 个策略配置文件')

    documents = []
    skipped_count = 0
    for file_path in sorted(path_list):
        try:
            policy_data = json.loads(Path(file_path).read_text(encoding='utf-8'))
            if policy_data == []:
                logger.info(f'跳过空策略配置: {file_path}')
                continue
            if _is_legacy_policy_document(policy_data):
                logger.warning(f'跳过不兼容的遗留策略配置: {file_path}')
                skipped_count += 1
                continue
            documents.append((file_path, policy_data))
        except Exception as e:
            logger.error(f'读取策略配置失败: {file_path}, 错误: {e}')
            skipped_count += 1
    documents, unavailable_count = _filter_unavailable_policy_documents(documents)
    skipped_count += unavailable_count
    if not documents:
        logger.error("没有可同步的内置策略模板，保留上一次有效内置模板")
        return
    try:
        result = PolicyService.sync_builtin_policy_templates(documents, delete_missing=not skipped_count)
    except Exception as e:
        logger.error(f"策略模板校验或对账失败，保留上一次有效内置模板: {e}")
        return
    logger.info(
        "策略模板对账完成: 创建=%s, 更新=%s, 删除=%s, 跳过=%s",
        result["created_count"],
        result["updated_count"],
        result["deleted_count"],
        skipped_count,
    )
