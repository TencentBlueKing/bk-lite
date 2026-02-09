"""维度处理工具模块

提供监控指标维度相关的通用处理函数，用于：
- 从实例ID元组构建维度字典
- 从metric_instance_id提取monitor_instance_id
- 格式化维度字符串用于显示
- 构建模板变量
"""

import ast
from typing import Union

from apps.core.logger import celery_logger as logger


def build_dimensions(instance_id_tuple: tuple, instance_id_keys: list) -> dict:
    """从实例ID元组和键列表构建维度字典

    Args:
        instance_id_tuple: 实例ID元组，如 ('host-01', 'cpu', 'core0')
        instance_id_keys: 键列表，如 ['host', 'metric', 'core']

    Returns:
        维度字典，如 {'host': 'host-01', 'metric': 'cpu', 'core': 'core0'}
    """
    if not instance_id_keys or not isinstance(instance_id_tuple, tuple):
        return {}
    return {
        instance_id_keys[i]: instance_id_tuple[i]
        for i in range(min(len(instance_id_keys), len(instance_id_tuple)))
    }


def extract_monitor_instance_id(
    metric_instance_id: Union[str, tuple], silent: bool = False
) -> str:
    """从metric_instance_id中提取monitor_instance_id

    支持两种输入格式：
    - 元组格式: ('host-01', 'cpu') -> "('host-01',)"
    - 字符串格式: "('host-01', 'cpu')" -> "('host-01',)"

    Args:
        metric_instance_id: 指标实例ID，可以是元组或元组字符串
        silent: 是否静默模式（不输出debug日志）

    Returns:
        提取的monitor_instance_id，格式为单元素元组的字符串表示
    """
    # 如果已经是元组，直接处理
    if isinstance(metric_instance_id, tuple):
        if len(metric_instance_id) > 0:
            return str((metric_instance_id[0],))
        return str(metric_instance_id)

    # 字符串格式，需要解析
    try:
        tuple_val = ast.literal_eval(metric_instance_id)
        if isinstance(tuple_val, tuple) and len(tuple_val) > 0:
            return str((tuple_val[0],))
    except (ValueError, SyntaxError) as e:
        if not silent:
            logger.debug(
                f"Unable to parse metric_instance_id='{metric_instance_id}' as tuple, "
                f"returning original value. Error: {e}"
            )

    return metric_instance_id if isinstance(metric_instance_id, str) else str(
        metric_instance_id
    )


def format_dimension_str(dimensions: dict, instance_id_keys: list = None) -> str:
    """将维度字典格式化为显示字符串

    跳过第一个键（通常是实例ID），只格式化其他维度。

    Args:
        dimensions: 维度字典
        instance_id_keys: 键列表，用于确定第一个键。如果不提供，使用字典的第一个键

    Returns:
        格式化的维度字符串，如 "metric:cpu, core:core0"
    """
    if not dimensions:
        return ""

    # 确定第一个键
    if instance_id_keys:
        first_key = instance_id_keys[0] if instance_id_keys else None
    else:
        keys = list(dimensions.keys())
        first_key = keys[0] if keys else None

    # 排除第一个键
    sub_dimensions = {k: v for k, v in dimensions.items() if k != first_key}
    if not sub_dimensions:
        return ""

    return ", ".join(f"{k}:{v}" for k, v in sub_dimensions.items())


def build_metric_template_vars(dimensions: dict) -> dict:
    """从维度字典构建模板变量

    为每个维度键添加 'metric__' 前缀，用于告警模板替换。

    Args:
        dimensions: 维度字典，如 {'host': 'host-01', 'metric': 'cpu'}

    Returns:
        模板变量字典，如 {'metric__host': 'host-01', 'metric__metric': 'cpu'}
    """
    return {f"metric__{k}": v for k, v in dimensions.items()}


def parse_dimensions_from_string(
    metric_instance_id: str, group_by_keys: list
) -> dict:
    """从metric_instance_id字符串解析维度信息

    Args:
        metric_instance_id: 格式为元组字符串，如 "('host-01', 'cpu', 'core0')"
        group_by_keys: 分组键列表，如 ['host', 'metric', 'core']

    Returns:
        维度字典，解析失败时返回空字典
    """
    try:
        tuple_val = ast.literal_eval(metric_instance_id)
        if isinstance(tuple_val, tuple):
            return {
                group_by_keys[i]: tuple_val[i]
                for i in range(min(len(group_by_keys), len(tuple_val)))
            }
    except (ValueError, SyntaxError) as e:
        logger.debug(
            f"Unable to parse dimensions from metric_instance_id='{metric_instance_id}', "
            f"returning empty dict. Error: {e}"
        )
    return {}
