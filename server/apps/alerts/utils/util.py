# -- coding: utf-8 --
# @File: util.py
# @Time: 2025/5/14 13:44
# @Author: windyzhao
import hashlib
import json
import os
import base64
from functools import wraps
from typing import Dict, Any, List

from django.utils.crypto import get_random_string

from apps.core.backends import logger


def gen_app_secret():
    """生成app_secret方法"""
    return get_random_string(32)


def catch_exception(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.exception(e)
            logger.exception(f"[catch_exception] method name:{func.__name__} error")

        return None

    return wrapper


def split_list(_list, count=100):
    n = len(_list)
    sublists = [_list[i: i + count] for i in range(0, n, count)]
    return sublists


def _parse_time_to_seconds(time_str: str) -> int:
    """解析时间字符串为秒数"""
    if time_str.endswith('min'):
        return int(time_str[:-3]) * 60
    elif time_str.endswith('h'):
        return int(time_str[:-1]) * 3600
    elif time_str.endswith('s'):
        return int(time_str[:-1])
    else:
        return int(time_str) * 60  # 默认按分钟处理


def _parse_time_to_minutes(time_str: str) -> int:
    """解析时间字符串为分钟数"""
    if time_str.endswith('min'):
        return int(time_str[:-3])
    elif time_str.endswith('h'):
        return int(time_str[:-1]) * 60
    else:
        return int(time_str)  # 默认按分钟处理


def image_to_base64(image_path, output_format="jpeg"):
    """
    将图片文件转换为Base64编码字符串

    参数:
        image_path (str): 图片文件路径
        output_format (str): 输出格式，如 "jpeg", "png", "gif" 等

    返回:
        str: 格式为 "data:image/[format];base64,[encoded data]" 的字符串
    """

    # 检查文件是否存在
    if not os.path.isfile(image_path):
        raise FileNotFoundError(f"图片文件不存在: {image_path}")

    # 确定文件扩展名
    ext = os.path.splitext(image_path)[1].lower().replace(".", "")
    if not ext:
        ext = output_format.lower()

    # 读取图片文件并编码
    with open(image_path, "rb") as image_file:
        encoded_string = base64.b64encode(image_file.read()).decode("utf-8")

    # 返回前端可用的Data URL
    return f"data:image/{ext};base64,{encoded_string}"


def generate_instance_fingerprint(event_data: Dict[str, Any], fields: List = []) -> str:
    """
    生成实例指纹，用于标识唯一实例

    Args:
        event_data: 事件数据
        fields: 用于生成指纹的字段列表，默认使用['item', 'resource_id', 'resource_type', 'alert_source']

    Returns:
        32位MD5哈希字符串作为实例指纹
    """
    fingerprint_data = {}

    if not fields:
        fields = ['item', 'resource_id', 'resource_type', 'alert_source']

    for field in fields:
        value = event_data.get(field)

        # 处理None值和空字符串
        if value is not None and str(value).strip():
            fingerprint_data[field] = str(value).strip()
        else:
            # 为空值提供默认值，确保指纹的一致性
            fingerprint_data[field] = 'unknown'
            logger.debug(f"Field '{field}' is empty or None, using 'unknown' as default")

    # 确保字段顺序一致
    sorted_data = json.dumps(fingerprint_data, sort_keys=True, ensure_ascii=False)
    fingerprint = hashlib.md5(sorted_data.encode('utf-8')).hexdigest()

    return fingerprint


def window_size_to_int(window_size: str) -> int:
    """
    将窗口大小字符串转换为整数分钟数

    Args:
        window_size: 窗口大小字符串，如 "5min", "1h", "30s"

    Returns:
        int: 窗口大小对应的分钟数
    """
    if window_size.endswith('min'):
        return int(window_size[:-3])
    elif window_size.endswith('h'):
        return int(window_size[:-1]) * 60
    elif window_size.endswith('s'):
        seconds = int(window_size[:-1])
        return max(1, seconds // 60)  # 秒转分钟，最少1分钟
    else:
        raise ValueError(f"无法解析窗口大小: {window_size}")