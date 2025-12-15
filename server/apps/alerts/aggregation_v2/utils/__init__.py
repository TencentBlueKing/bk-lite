# -- coding: utf-8 --
"""
工具函数模块

提供通用工具函数
"""

# 从现有模块复用工具函数
from apps.alerts.utils.util import (
    generate_instance_fingerprint,
    window_size_to_int,
    gen_app_secret,
)

# 导入新的工具类
from apps.alerts.aggregation_v2.utils.time_utils import TimeUtils, WindowCalculator
from apps.alerts.aggregation_v2.utils.fingerprint import FingerprintGenerator
from apps.alerts.aggregation_v2.utils.metrics import PerformanceMonitor

__all__ = [
    # 复用的函数
    'generate_instance_fingerprint',
    'window_size_to_int',
    'gen_app_secret',
    'WindowCalculator',
    # 新增的类
    'TimeUtils',
    'FingerprintGenerator',
    'PerformanceMonitor'
]
