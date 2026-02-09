"""维度处理工具函数 - 用于处理监控指标的维度数据"""

import ast
from typing import Union


def build_dimensions(
    instance_id: Union[tuple, str], instance_id_keys: list = None
) -> dict:
    """从实例ID构建维度字典

    Args:
        instance_id: 实例ID，可以是tuple或str格式
        instance_id_keys: 维度键列表，如 ["instance_id", "device"]

    Returns:
        维度字典，如 {"instance_id": "host1", "device": "eth0"}
    """
    if not instance_id_keys:
        return {}

    if isinstance(instance_id, str):
        try:
            instance_id = ast.literal_eval(instance_id)
        except Exception:
            return {}

    if not isinstance(instance_id, tuple):
        return {}

    return {
        instance_id_keys[i]: instance_id[i]
        for i in range(min(len(instance_id_keys), len(instance_id)))
    }


def extract_monitor_instance_id(instance_id: Union[tuple, str]) -> str:
    """从完整的metric_instance_id提取monitor_instance_id（第一个维度值）

    Args:
        instance_id: 实例ID，可以是tuple或str格式

    Returns:
        monitor_instance_id字符串，格式为 "('value',)"
    """
    if isinstance(instance_id, str):
        try:
            instance_id = ast.literal_eval(instance_id)
        except Exception:
            return instance_id

    if isinstance(instance_id, tuple) and len(instance_id) > 0:
        return str((instance_id[0],))

    return str(instance_id)


def format_dimension_str(dimensions: dict, instance_id_keys: list = None) -> str:
    """格式化维度字典为显示字符串（排除第一个维度）

    Args:
        dimensions: 维度字典
        instance_id_keys: 维度键列表，用于确定第一个键。如果为None，则使用字典的第一个键

    Returns:
        格式化的维度字符串，如 "device:eth0, mount:/home"
    """
    if not dimensions:
        return ""

    if instance_id_keys:
        first_key = instance_id_keys[0] if instance_id_keys else None
    else:
        keys = list(dimensions.keys())
        first_key = keys[0] if keys else None

    sub_dimensions = {k: v for k, v in dimensions.items() if k != first_key}
    if not sub_dimensions:
        return ""

    return ", ".join(f"{k}:{v}" for k, v in sub_dimensions.items())


def build_metric_template_vars(dimensions: dict) -> dict:
    """构建用于模板替换的维度变量

    Args:
        dimensions: 维度字典

    Returns:
        模板变量字典，键名格式为 "metric__key"
    """
    return {f"metric__{k}": v for k, v in dimensions.items()}
