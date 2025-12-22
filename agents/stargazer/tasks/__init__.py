# -- coding: utf-8 --
# @File: __init__.py
# @Time: 2025/12/19
# @Author: AI Assistant
"""
Tasks 模块 - 异步任务系统

目录结构：
- handlers/     任务处理器（具体的任务函数）
- collectors/   数据采集器（采集逻辑实现）
- utils/        工具函数（通用功能）
"""
from .handlers.plugin_handler import collect_plugin_task
from .handlers.monitor_handler import (
    collect_vmware_metrics_task,
    collect_qcloud_metrics_task,
)

# 导出所有任务函数
__all__ = [
    'collect_plugin_task',
    'collect_vmware_metrics_task',
    'collect_qcloud_metrics_task',
]

