import json
from pathlib import Path

from apps.core.logger import monitor_logger as logger
from apps.monitor.constants.plugin import PluginConstants
from apps.monitor.management.utils import find_files_by_pattern
from apps.monitor.services.policy import PolicyService


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
    error_count = 0
    for file_path in sorted(path_list):
        try:
            policy_data = json.loads(Path(file_path).read_text(encoding='utf-8'))
            if policy_data == []:
                logger.info(f'跳过空策略配置: {file_path}')
                continue
            documents.append(policy_data)
        except Exception as e:
            logger.error(f'读取策略配置失败: {file_path}, 错误: {e}')
            error_count += 1
    if error_count:
        logger.error(f"策略配置读取失败，保留上一次有效内置模板: 失败={error_count}")
        return
    try:
        result = PolicyService.sync_builtin_policy_templates(documents)
    except Exception as e:
        logger.error(f"策略模板校验或对账失败，保留上一次有效内置模板: {e}")
        return
    logger.info(
        "策略模板对账完成: 创建=%s, 更新=%s, 删除=%s",
        result["created_count"],
        result["updated_count"],
        result["deleted_count"],
    )
