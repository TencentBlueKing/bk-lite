# -- coding: utf-8 --
# @File: metrics_helper.py
# @Time: 2025/12/19
# @Author: AI Assistant
"""
指标生成辅助工具
生成各种格式的 Prometheus 指标
"""
import time
from typing import Dict, Any


def generate_plugin_error_metrics(params: Dict[str, Any], error: Exception) -> str:
    """
    生成插件采集错误指标（Prometheus 格式）

    Args:
        params: 采集参数
        error: 异常对象

    Returns:
        Prometheus 格式的错误指标
    """
    current_timestamp = int(time.time() * 1000)
    error_type = type(error).__name__
    plugin_name = params.get('plugin_name', 'unknown')

    prometheus_lines = [
        "# HELP collection_status Auto-generated help for collection_status",
        "# TYPE collection_status gauge",
        f'collection_status{{plugin="{plugin_name}",status="error",error_type="{error_type}"}} 1 {current_timestamp}'
    ]

    return "\n".join(prometheus_lines) + "\n"


def generate_monitor_error_metrics(params: Dict[str, Any], error: Exception) -> str:
    """
    生成监控采集错误指标（Prometheus 格式）

    Args:
        params: 采集参数
        error: 异常对象

    Returns:
        Prometheus 格式的错误指标
    """
    current_timestamp = int(time.time() * 1000)
    error_type = type(error).__name__
    monitor_type = params.get('monitor_type', 'unknown')

    prometheus_lines = [
        "# HELP monitor_collection_status Monitor collection status",
        "# TYPE monitor_collection_status gauge",
        f'monitor_collection_status{{monitor_type="{monitor_type}",status="error",error_type="{error_type}"}} 1 {current_timestamp}'
    ]

    return "\n".join(prometheus_lines) + "\n"


def generate_host_remote_state_metric(
    event: str,
    task_id: str,
    status: str,
    value: int = 1,
    monitor_type: str = "host",
    extra_labels: Dict[str, Any] | None = None,
) -> str:
    current_timestamp = int(time.time() * 1000)
    labels = {
        "monitor_type": monitor_type,
        "event": event,
        "task_id": str(task_id or ""),
        "status": status,
    }
    if isinstance(extra_labels, dict):
        for key, label_value in extra_labels.items():
            if label_value is not None:
                labels[key] = label_value

    rendered_labels = ",".join(
        f'{key}="{str(value).replace("\\", "\\\\").replace("\"", "\\\"")}"'
        for key, value in labels.items()
    )
    return "\n".join(
        [
            "# HELP host_remote_state Host remote collection lifecycle state",
            "# TYPE host_remote_state gauge",
            f"host_remote_state{{{rendered_labels}}} {value} {current_timestamp}",
        ]
    ) + "\n"
