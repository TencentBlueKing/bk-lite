"""维度处理工具函数 - 用于处理监控指标的维度数据"""

import ast
import base64
from typing import Any, Union


class ScopedInstanceMatcher:
    """把指标维度在策略已选实例范围内唯一解析为监控实例 ID。"""

    def __init__(self, object_instance_id_keys: list, scoped_instance_ids):
        self.object_instance_id_keys = list(object_instance_id_keys or [])
        self.scoped_instance_values = {
            instance_id: parse_instance_id(instance_id)
            for instance_id in scoped_instance_ids
        }
        self._indexes = {}

    def resolve(self, instance_values: tuple, instance_value_keys: list) -> str:
        dimensions = build_dimensions(instance_values, instance_value_keys)
        comparable_keys = [
            key for key in dimensions if key in self.object_instance_id_keys
        ]
        if not comparable_keys:
            return ""

        index_key = tuple(comparable_keys)
        match_index = self._indexes.get(index_key)
        if match_index is None:
            match_index = self._build_index(comparable_keys)
            self._indexes[index_key] = match_index

        identity = tuple(str(dimensions[key]) for key in comparable_keys)
        return match_index.get(identity, "")

    def _build_index(self, comparable_keys: list) -> dict:
        match_index = {}
        positions = [
            self.object_instance_id_keys.index(key) for key in comparable_keys
        ]
        for candidate_id, candidate_values in self.scoped_instance_values.items():
            if any(position >= len(candidate_values) for position in positions):
                continue
            identity = tuple(
                str(candidate_values[position]) for position in positions
            )
            # 空字符串是歧义哨兵；同一身份出现两次后不再猜测归属。
            match_index[identity] = "" if identity in match_index else candidate_id
        return match_index


def build_safe_instance_id(*parts: Any) -> str:
    """Encode identity parts into a stable label-safe instance id."""
    normalized_parts = [str(part).strip() for part in parts]
    if any(not part for part in normalized_parts):
        raise ValueError("instance id parts must not be empty")
    raw_value = ":".join(normalized_parts)
    return base64.urlsafe_b64encode(raw_value.encode("utf-8")).decode("ascii").rstrip("=")


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
        except (ValueError, SyntaxError):
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
        except (ValueError, SyntaxError):
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


def parse_instance_id(instance_id: Any) -> tuple:
    """统一解析实例ID为tuple，避免调用方重复写 literal_eval 兜底逻辑。"""
    if isinstance(instance_id, tuple):
        return instance_id

    if isinstance(instance_id, list):
        return tuple(instance_id)

    if isinstance(instance_id, str):
        try:
            parsed = ast.literal_eval(instance_id)
            if isinstance(parsed, tuple):
                return parsed
            if isinstance(parsed, list):
                return tuple(parsed)
            return (parsed,)
        except (ValueError, SyntaxError):
            return (instance_id,)

    return (instance_id,)


def normalize_instance_identity(instance_id: Any) -> dict:
    """统一解析实例ID，兼容原始值与遗留的tuple字符串格式。

    Args:
        instance_id: 原始实例ID，支持裸字符串（如 "abc123"）、
            单维 tuple 字符串（如 "('abc123',)"）、
            多维 tuple 字符串（如 "('vc-a', 'host-1')"）

    Returns:
        包含以下键的字典：
        - raw_input: 原始输入值
        - logical_instance_value: 逻辑实例值（第一维）
        - storage_instance_key: 存储键。
          单维实例保持为 "('value',)"，
          多维实例保持完整 tuple 串，如 "('vc-a', 'host-1')"

    Raises:
        ValueError: instance_id 为空或解析失败
    """
    if instance_id in (None, ""):
        raise ValueError("instance_id is required")

    parsed = parse_instance_id(instance_id)
    if not parsed or parsed[0] in (None, ""):
        raise ValueError(f"invalid instance_id: {instance_id}")

    logical_value = str(parsed[0])
    storage_instance_key = str(parsed) if len(parsed) > 1 else extract_monitor_instance_id(parsed)
    return {
        "raw_input": instance_id,
        "logical_instance_value": logical_value,
        "storage_instance_key": storage_instance_key,
    }


def format_dimension_value(
    dimensions: dict,
    ordered_keys: list = None,
    name_map: dict = None,
) -> str:
    """格式化dimension_value变量

    规则：
    - 按 ordered_keys 顺序输出，缺省按 dimensions 原顺序
    - 单项格式为 "维度名称:维度值"
    - 维度值为空时保留为 "维度名称:"
    - 多项以英文逗号","连接（不带空格）
    """
    if not dimensions:
        return ""

    name_map = name_map or {}
    keys = list(dimensions.keys()) if ordered_keys is None else ordered_keys
    parts = []

    for key in keys:
        if key not in dimensions:
            continue
        display_name = name_map.get(key) or key
        value = dimensions.get(key)
        value_str = "" if value is None else str(value)
        parts.append(f"{display_name}:{value_str}")

    return ",".join(parts)
