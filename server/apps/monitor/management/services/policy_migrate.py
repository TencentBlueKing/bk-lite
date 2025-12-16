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
