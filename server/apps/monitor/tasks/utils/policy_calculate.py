import pandas as pd
from string import Template

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.constants.alert_policy import AlertConstants


def vm_to_dataframe(vm_data, instance_id_keys=None):
    df = pd.json_normalize(vm_data, sep="_")

    metric_cols = [col for col in df.columns if col.startswith("metric_")]

    if instance_id_keys:
        selected_cols = [
            f"metric_{key}"
            for key in instance_id_keys
            if f"metric_{key}" in metric_cols
        ]
    else:
        selected_cols = ["metric_instance_id"]

    df["instance_id"] = df[selected_cols].apply(lambda row: tuple(row), axis=1)

    return df


def calculate_alerts(alert_name, df, thresholds, template_context=None, n=1):
    alert_events, info_events = [], []
    template_context = template_context or {}
    instances_map = template_context.get("instances_map", {})
    instance_id_keys = template_context.get("instance_id_keys", [])

    for _, row in df.iterrows():
        instance_id_tuple = row["instance_id"]
        metric_instance_id = str(instance_id_tuple)

        dimensions = _build_dimensions(instance_id_tuple, instance_id_keys)
        monitor_instance_id = _extract_monitor_instance_id(instance_id_tuple)
        instance_name = instances_map.get(monitor_instance_id, monitor_instance_id)
        dimension_str = _format_dimension_str(dimensions, instance_id_keys)
        display_name = (
            f"{instance_name} - {dimension_str}" if dimension_str else instance_name
        )

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
                    "instance_name": display_name,
                    "metric_name": template_context.get("metric_name", ""),
                    "level": threshold_info["level"],
                    "value": alert_value,
                }
                context.update(_build_metric_template_vars(dimensions))

                template = Template(alert_name)
                content = template.safe_substitute(context)

                event = {
                    "metric_instance_id": metric_instance_id,
                    "monitor_instance_id": monitor_instance_id,
                    "dimensions": dimensions,
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
                    "metric_instance_id": metric_instance_id,
                    "monitor_instance_id": monitor_instance_id,
                    "dimensions": dimensions,
                    "value": values[-1][1],
                    "timestamp": values[-1][0],
                    "level": "info",
                    "content": "info",
                    "raw_data": raw_data,
                }
            )

    return alert_events, info_events


def _build_dimensions(instance_id_tuple, instance_id_keys: list) -> dict:
    if not instance_id_keys or not isinstance(instance_id_tuple, tuple):
        return {}
    return {
        instance_id_keys[i]: instance_id_tuple[i]
        for i in range(min(len(instance_id_keys), len(instance_id_tuple)))
    }


def _extract_monitor_instance_id(instance_id_tuple) -> str:
    if isinstance(instance_id_tuple, tuple) and len(instance_id_tuple) > 0:
        return str(instance_id_tuple[0])
    return str(instance_id_tuple)


def _format_dimension_str(dimensions: dict, instance_id_keys: list) -> str:
    if not dimensions or not instance_id_keys:
        return ""
    first_key = instance_id_keys[0] if instance_id_keys else None
    sub_dimensions = {k: v for k, v in dimensions.items() if k != first_key}
    if not sub_dimensions:
        return ""
    return ", ".join(f"{k}:{v}" for k, v in sub_dimensions.items())


def _build_metric_template_vars(dimensions: dict) -> dict:
    return {f"metric__{k}": v for k, v in dimensions.items()}
