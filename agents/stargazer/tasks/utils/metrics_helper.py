# -- coding: utf-8 --
# @File: metrics_helper.py
# @Time: 2025/12/19
# @Author: AI Assistant
"""
指标生成辅助工具
生成各种格式的 Prometheus 指标
"""

import time
from typing import Any, Dict


def generate_monitor_error_metrics(params: Dict[str, Any], error: Exception) -> str:
    """
    生成监控采集错误指标（Prometheus 格式）

    Args:
        params: 采集参数
        error: 异常对象

    Returns:
        Prometheus 格式的错误指标
    """
    current_timestamp = int(params.get("_publish_timestamp_ms") or time.time() * 1000)
    error_type = type(error).__name__
    monitor_type = params.get("monitor_type", "unknown")

    prometheus_lines = [
        "# HELP monitor_collection_status Monitor collection status",
        "# TYPE monitor_collection_status gauge",
        f'monitor_collection_status{{monitor_type="{monitor_type}",status="error",error_type="{error_type}"}} 1 {current_timestamp}',
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
    # task_id 保留在调用契约中用于 callback/发布关联，但不得进入指标标签。
    _ = task_id
    current_timestamp = int(time.time() * 1000)
    labels = {
        "monitor_type": monitor_type,
        "event": event,
        "status": status,
    }
    if isinstance(extra_labels, dict):
        reason = extra_labels.get("reason")
        if reason is not None:
            labels["reason"] = reason

    def escape_label(label_value: Any) -> str:
        return str(label_value).replace("\\", "\\\\").replace('"', '\\"')

    rendered_labels = ",".join(f'{key}="{escape_label(label_value)}"' for key, label_value in labels.items())
    return (
        "\n".join(
            [
                "# HELP host_remote_state Host remote collection lifecycle state",
                "# TYPE host_remote_state gauge",
                f"host_remote_state{{{rendered_labels}}} {value} {current_timestamp}",
            ]
        )
        + "\n"
    )
