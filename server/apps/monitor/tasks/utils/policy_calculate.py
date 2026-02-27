import pandas as pd
from string import Template

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.constants.alert_policy import AlertConstants
from apps.monitor.utils.dimension import (
    build_dimensions,
    extract_monitor_instance_id,
    format_dimension_str,
    format_dimension_value,
    build_metric_template_vars,
)


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


def _format_value_with_unit(
    value: float, unit: str, enum_value_map: dict = None
) -> str:
    if value is None:
        return "N/A"
    if enum_value_map:
        int_value = int(value)
        if int_value in enum_value_map:
            return enum_value_map[int_value]
    formatted = f"{value:.2f}"
    if unit:
        return f"{formatted}{unit}"
    return formatted


def calculate_alerts(alert_name, df, thresholds, template_context=None, n=1):
    alert_events, info_events = [], []
    template_context = template_context or {}
    instances_map = template_context.get("instances_map", {})
    instance_id_keys = template_context.get("instance_id_keys", [])
    display_unit = template_context.get("display_unit", "")
    enum_value_map = template_context.get("enum_value_map", {})
    dimension_name_map = template_context.get("dimension_name_map", {})

    for _, row in df.iterrows():
        instance_id_tuple = row["instance_id"]
        metric_instance_id = str(instance_id_tuple)

        dimensions = build_dimensions(instance_id_tuple, instance_id_keys)
        monitor_instance_id = extract_monitor_instance_id(instance_id_tuple)
        resource_name = instances_map.get(monitor_instance_id, monitor_instance_id)
        dimension_str = format_dimension_str(dimensions, instance_id_keys)
        display_name = (
            f"{resource_name} - {dimension_str}" if dimension_str else resource_name
        )
        dimension_value = format_dimension_value(
            dimensions,
            ordered_keys=instance_id_keys,
            name_map=dimension_name_map,
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
                alert_value = float(values[-1][1])
                formatted_value = _format_value_with_unit(
                    alert_value, display_unit, enum_value_map
                )
                context = {
                    **raw_data,
                    "monitor_object": template_context.get("monitor_object", ""),
                    "instance_name": display_name,
                    "resource_name": resource_name,
                    "metric_name": template_context.get("metric_name", ""),
                    "level": threshold_info["level"],
                    "value": formatted_value,
                    "dimension_value": dimension_value,
                }
                context.update(build_metric_template_vars(dimensions))

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
