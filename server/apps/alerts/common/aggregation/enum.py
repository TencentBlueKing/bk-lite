# -- coding: utf-8 --
# @File: enum.py
# @Time: 2025/9/16 16:21
# @Author: windyzhao

# -- coding: utf-8 --
# @File: agg_rules.py
# @Time: 2025/6/16 15:23
# @Author: windyzhao

"""
聚合规则配置模块
定义不同窗口类型的聚合规则配置
"""
from dataclasses import dataclass
from typing import Dict, Any
from enum import Enum


class WindowType(str, Enum):
    """窗口类型枚举"""
    SLIDING = "sliding"  # 滑动窗口
    FIXED = "fixed"  # 固定窗口
    SESSION = "session"  # 会话窗口


# 窗口类型处理优先级
WINDOW_TYPE_PRIORITY = [
    WindowType.SLIDING,
    WindowType.FIXED,
    WindowType.SESSION
]

# 各窗口类型的默认配置
DEFAULT_WINDOW_CONFIGS = {
    WindowType.SLIDING: {
        'window_size': '10min',
        'slide_interval': '1min',
        'alignment': 'natural',
        'max_window_size': '1h',
        'execution_frequency': 'every_minute'  # 每分钟执行
    },
    WindowType.FIXED: {
        'window_size': '5min',
        'slide_interval': '5min',
        'alignment': 'minute',  # 改为支持的对齐方式
        'max_window_size': '1h',
        'execution_frequency': 'window_aligned'  # 按窗口对齐执行
    },
    WindowType.SESSION: {
        'window_size': '15min',
        'session_timeout': '30min',
        'session_key_fields': ['item', 'resource_id', 'resource_type', 'alert_source', 'rule_id'],  # 会话键字段和event指纹一致,
        'max_window_size': '2h',
        'max_event_count': 1000,  # 最大事件数量
        'execution_frequency': 'timeout_based'  # 基于超时时间执行
    }
}

# 默认的告警标题和内容模板
DEFAULT_TITLE = "【${resource_type}】${resource_name}发生${item} 异常"
DEFAULT_CONTENT = "【${resource_type}】${resource_name}发生${item} 异常"


def get_window_config(window_type: WindowType) -> Dict[str, Any]:
    """获取窗口类型的默认配置"""
    return DEFAULT_WINDOW_CONFIGS.get(window_type, {})


def validate_window_config(config: Dict[str, Any]) -> bool:
    """验证窗口配置的有效性"""
    required_fields = ['window_size', 'window_type']
    return all(field in config for field in required_fields)


@dataclass
class WindowConfig:
    """窗口配置"""
    window_type: str
    window_size: str = "10min"

    # 滑动窗口特有配置
    slide_interval: str = "1min"  # 滑动间隔

    # 固定窗口特有配置
    alignment: str = "minute"  # 对齐方式: minute, hour, day

    # 会话窗口特有配置
    session_timeout: str = "5min"  # 会话超时时间
    session_key_fields: list = None  # 会话分组字段，空数组表示使用事件指纹

    # 通用配置
    max_window_size: str = "1h"  # 最大窗口大小限制

    def __post_init__(self):
        if self.session_key_fields is None:
            # 默认使用指纹分组模式（空数组）
            self.session_key_fields = []

    @property
    def use_fingerprint_grouping(self) -> bool:
        """
        是否使用指纹分组模式

        指纹分组模式的优势：
        1. 每个唯一事件组合（资源+指标+告警源等）独立成会话
        2. 简化会话管理逻辑，提高性能
        3. 更精细的粒度控制，避免不相关事件混合

        Returns:
            bool: True表示使用指纹分组，False表示使用字段组合分组
        """
        return True