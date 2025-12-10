from pathlib import Path
from typing import Tuple, List

from apps.core.logger import monitor_logger as logger


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
