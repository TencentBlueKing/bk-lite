import math
from string import Template

import pandas as pd

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.constants.alert_policy import AlertConstants
from apps.monitor.utils.dimension import (
    build_dimensions,
    build_metric_template_vars,
    extract_monitor_instance_id,
    format_dimension_str,
    format_dimension_value,
)


def vm_to_dataframe(vm_data, instance_id_keys=None):
    df = pd.json_normalize(vm_data or [], sep="_")

    metric_cols = [col for col in df.columns if col.startswith("metric_")]

    if instance_id_keys:
        selected_cols = [f"metric_{key}" for key in instance_id_keys if f"metric_{key}" in metric_cols]
    else:
        selected_cols = ["metric_instance_id"] if "metric_instance_id" in df.columns else []

    # pandas DataFrame.apply(axis=1) crashes on 0-column / empty frames:
    # ValueError: Length of values (0) does not match length of index (1)
    if not selected_cols:
        df["instance_id"] = [() for _ in range(len(df.index))]
        return df

    df["instance_id"] = [tuple(row) for row in df[selected_cols].to_numpy()]
    return df


def _format_value_with_unit(value: float, unit: str, enum_value_map: dict = None) -> str:
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


def _parse_finite_float(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _threshold_configured(threshold):
    return bool(isinstance(threshold, dict) and threshold.get("method") and threshold.get("value") is not None)


def _all_meet_threshold(numeric_values, method_key, threshold_value):
    method = AlertConstants.THRESHOLD_METHODS.get(method_key)
    if not method:
        raise BaseAppException(f"Invalid threshold method: {method_key}")
    return all(method(value, threshold_value) for value in numeric_values)


def calculate_alerts(alert_name, df, thresholds, template_context=None, n=1, recovery_threshold=None):
    alert_events, info_events, hold_events = [], [], []
    template_context = template_context or {}
    instances_map = template_context.get("instances_map", {})
    instance_id_keys = template_context.get("instance_id_keys", [])
    display_unit = template_context.get("display_unit", "")
    source_display_unit = template_context.get("source_display_unit", display_unit)
    enum_value_map = template_context.get("enum_value_map", {})
    dimension_name_map = template_context.get("dimension_name_map", {})
    monitor_instance_id_key = template_context.get("monitor_instance_id_key")
    resource_context_resolver = template_context.get("resource_context_resolver")
    overlay_current_map = template_context.get("overlay_current_map") or {}
    overlay_baseline_map = template_context.get("overlay_baseline_map") or {}
    recovery_enabled = _threshold_configured(recovery_threshold)

    for _, row in df.iterrows():
        instance_id_tuple = row["instance_id"]
        metric_instance_id = str(instance_id_tuple)

        dimensions = build_dimensions(instance_id_tuple, instance_id_keys)
        monitor_instance_id = _extract_monitor_instance_id_by_key(
            instance_id_tuple,
            instance_id_keys,
            monitor_instance_id_key,
        )
        resource_context = {}
        if callable(resource_context_resolver):
            resource_context = resource_context_resolver(metric_instance_id) or {}
            monitor_instance_id = resource_context.get("monitor_instance_id", monitor_instance_id)
        resource_name = resource_context.get(
            "resource_name",
            instances_map.get(monitor_instance_id, monitor_instance_id),
        )
        dimension_str = format_dimension_str(dimensions, instance_id_keys)
        display_name = f"{resource_name} - {dimension_str}" if dimension_str else resource_name
        sub_dimension_keys = [k for k in instance_id_keys if k != "instance_id"]
        dimension_value = format_dimension_value(
            dimensions,
            ordered_keys=sub_dimension_keys,
            name_map=dimension_name_map,
        )

        values = row["values"][-n:]
        if len(values) < n:
            continue
        numeric_values = [_parse_finite_float(value[1]) for value in values]
        if any(value is None for value in numeric_values):
            continue

        raw_data = row.to_dict()
        raw_data["values"] = values

        alert_triggered = False
        sorted_thresholds = sorted(
            thresholds,
            key=lambda item: AlertConstants.LEVEL_WEIGHT.get(item.get("level"), 0),
            reverse=True,
        )
        for threshold_info in sorted_thresholds:
            if _all_meet_threshold(numeric_values, threshold_info["method"], threshold_info["value"]):
                alert_value = numeric_values[-1]
                formatted_value = _format_value_with_unit(alert_value, display_unit, enum_value_map)
                current_raw = overlay_current_map.get(metric_instance_id, alert_value)
                baseline_raw = overlay_baseline_map.get(metric_instance_id)
                context = {
                    **raw_data,
                    "monitor_object": template_context.get("monitor_object", ""),
                    "instance_name": display_name,
                    "resource_name": resource_name,
                    "metric_name": template_context.get("metric_name", ""),
                    "level": threshold_info["level"],
                    "value": formatted_value,
                    "current_value": _format_value_with_unit(current_raw, source_display_unit, enum_value_map),
                    "baseline_value": (
                        _format_value_with_unit(baseline_raw, source_display_unit, enum_value_map) if baseline_raw is not None else ""
                    ),
                    "dimension_value": dimension_value,
                    **resource_context,
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

        if alert_triggered:
            continue

        recovered = False
        if recovery_enabled:
            recovered = _all_meet_threshold(
                numeric_values,
                recovery_threshold["method"],
                recovery_threshold["value"],
            )
            if not recovered:
                hold_events.append(
                    {
                        "metric_instance_id": metric_instance_id,
                        "monitor_instance_id": monitor_instance_id,
                        "dimensions": dimensions,
                        "value": values[-1][1],
                        "timestamp": values[-1][0],
                        "level": "hold",
                        "content": "hold",
                        "raw_data": raw_data,
                    }
                )
                continue

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

    return alert_events, info_events, hold_events


def _extract_monitor_instance_id_by_key(
    instance_id_tuple: tuple,
    instance_id_keys: list,
    monitor_instance_id_key: str | None,
) -> str:
    if monitor_instance_id_key and monitor_instance_id_key in instance_id_keys:
        index = instance_id_keys.index(monitor_instance_id_key)
        if index < len(instance_id_tuple):
            return str((instance_id_tuple[index],))

    return extract_monitor_instance_id(instance_id_tuple)
