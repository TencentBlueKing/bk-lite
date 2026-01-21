import pandas as pd
from string import Template

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.constants.alert_policy import AlertConstants


def vm_to_dataframe(vm_data, instance_id_keys=None):
    """将 VM 数据转换为 DataFrame，支持多维度组合 instance_id"""
    df = pd.json_normalize(vm_data, sep="_")  # 展开 metric 字段

    # 获取所有 metric 维度
    metric_cols = [col for col in df.columns if col.startswith("metric_")]

    # 选择用于拼接 instance_id 的维度字段
    if instance_id_keys:
        selected_cols = [
            f"metric_{key}"
            for key in instance_id_keys
            if f"metric_{key}" in metric_cols
        ]
    else:
        selected_cols = ["metric_instance_id"]  # 默认使用 instance_id

    # 生成instance_id（拼接选定的维度字段）
    # df["instance_id"] = df[selected_cols].astype(str).agg("_".join, axis=1)
    df["instance_id"] = df[selected_cols].apply(lambda row: tuple(row), axis=1)

    return df


def calculate_alerts(alert_name, df, thresholds, template_context=None, n=1):
    """计算告警事件

    Args:
        alert_name: 告警名称模板
        df: 指标数据DataFrame
        thresholds: 阈值配置列表
        template_context: 模板变量上下文，包含 monitor_object, metric_name, instances_map 等
        n: 数据点窗口大小
    """
    alert_events, info_events = [], []
    template_context = template_context or {}
    instances_map = template_context.get("instances_map", {})

    for _, row in df.iterrows():
        instance_id = str(row["instance_id"])

        values = row["values"][-n:]
        if len(values) < n:
            continue

        raw_data = row.to_dict()
        raw_data["values"] = values

        alert_triggered = False
        for threshold_info in thresholds:
            method = AlertConstants.THRESHOLD_METHODS.get(threshold_info["method"])
            if not method:
                raise BaseAppException(
                    f"Invalid threshold method: {threshold_info['method']}"
                )

            if all(method(float(v[1]), threshold_info["value"]) for v in values):
                alert_value = values[-1][1]
                context = {
                    **raw_data,
                    "monitor_object": template_context.get("monitor_object", ""),
                    "instance_name": instances_map.get(instance_id, instance_id),
                    "metric_name": template_context.get("metric_name", ""),
                    "level": threshold_info["level"],
                    "value": alert_value,
                }

                template = Template(alert_name)
                content = template.safe_substitute(context)

                event = {
                    "instance_id": instance_id,
                    "value": alert_value,
                    "timestamp": values[-1][0],
                    "level": threshold_info["level"],
                    "content": content,
                    "raw_data": raw_data,
                }
                alert_events.append(event)
                alert_triggered = True
                break

        if not alert_triggered:
            info_events.append(
                {
                    "instance_id": instance_id,
                    "value": values[-1][1],
                    "timestamp": values[-1][0],
                    "level": "info",
                    "content": "info",
                    "raw_data": raw_data,
                }
            )

    return alert_events, info_events
