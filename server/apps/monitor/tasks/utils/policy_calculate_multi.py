"""多指标条件判定：按锚点维度对齐，级别取各条件命中级别的最低者。"""

from string import Template

from apps.monitor.constants.alert_policy import AlertConstants
from apps.monitor.tasks.utils.policy_calculate import (
    _all_meet_threshold,
    _extract_monitor_instance_id_by_key,
    _format_value_with_unit,
    _parse_finite_float,
)
from apps.monitor.utils.dimension import (
    build_dimensions,
    build_metric_template_vars,
    format_dimension_str,
    format_dimension_value,
)


def _series_key(metric_labels, group_by):
    labels = metric_labels or {}
    return tuple(labels.get(key) for key in group_by)


def _index_series(items, group_by):
    indexed = {}
    for item in items or []:
        if not isinstance(item, dict):
            continue
        indexed[_series_key(item.get("metric"), group_by)] = item
    return indexed


def _values_by_timestamp(series_item):
    parsed = {}
    for pair in (series_item or {}).get("values") or []:
        if not isinstance(pair, (list, tuple)) or len(pair) < 2:
            continue
        raw_ts = pair[0]
        try:
            timestamp = int(raw_ts)
        except (TypeError, ValueError):
            timestamp = raw_ts
        parsed[timestamp] = _parse_finite_float(pair[1])
    return parsed


def _threshold_for_level(condition, level):
    for item in condition.get("threshold") or []:
        if isinstance(item, dict) and item.get("level") == level:
            return item
    return None


def _levels_high_to_low(conditions):
    levels = {
        item.get("level")
        for condition in conditions
        if condition.get("role") == "level"
        for item in condition.get("threshold") or []
        if isinstance(item, dict) and item.get("level")
    }
    return sorted(levels, key=lambda level: AlertConstants.LEVEL_WEIGHT.get(level, 0), reverse=True)


def _aligned_window(series_by_ref, conditions, timestamps, n):
    window = {}
    for condition in conditions:
        ref = condition.get("ref")
        parsed = series_by_ref[ref]
        values = [parsed.get(timestamp) for timestamp in timestamps]
        if any(value is None for value in values):
            return None
        window[ref] = values
    if any(len(values) < n for values in window.values()):
        return None
    return window


def calculate_multi_alerts(alert_name, series_by_ref, conditions, template_context=None, n=1):
    """返回与 calculate_alerts 相同的三类事件。多指标模式不产生 hold_events。"""
    template_context = template_context or {}
    conditions = [item for item in conditions or [] if isinstance(item, dict)]
    if len(conditions) < 2:
        return [], [], []

    anchor = conditions[0]
    anchor_ref = anchor.get("ref")
    anchor_group_by = list(anchor.get("group_by") or [])
    level_conditions = [item for item in conditions if item.get("role") == "level"]
    gate_conditions = [item for item in conditions if item.get("role") == "gate"]
    primary = level_conditions[0] if level_conditions else None
    if primary is None:
        return [], [], []

    indexed = {
        item.get("ref"): _index_series(series_by_ref.get(item.get("ref")) or [], item.get("group_by") or [])
        for item in conditions
    }
    display_units = template_context.get("condition_display_units") or {}
    metric_names = template_context.get("condition_metric_names") or {}
    enum_maps = template_context.get("condition_enum_maps") or {}
    instances_map = template_context.get("instances_map") or {}
    instance_id_keys = template_context.get("instance_id_keys") or anchor_group_by
    dimension_name_map = template_context.get("dimension_name_map") or {}
    monitor_instance_id_key = template_context.get("monitor_instance_id_key")
    resource_context_resolver = template_context.get("resource_context_resolver")
    levels = _levels_high_to_low(conditions)
    trigger_count = max(1, int(n or 1))

    alert_events = []
    info_events = []
    for anchor_key, anchor_item in indexed.get(anchor_ref, {}).items():
        joined = {anchor_ref: anchor_item}
        missing = False
        for condition in conditions[1:]:
            ref = condition.get("ref")
            join_key = _series_key(anchor_item.get("metric"), condition.get("group_by") or [])
            matched = indexed.get(ref, {}).get(join_key)
            if matched is None:
                missing = True
                break
            joined[ref] = matched
        if missing:
            continue

        parsed_by_ref = {ref: _values_by_timestamp(item) for ref, item in joined.items()}
        common = None
        for parsed in parsed_by_ref.values():
            stamps = {timestamp for timestamp, value in parsed.items() if value is not None}
            common = stamps if common is None else common & stamps
        ordered = sorted(common or [])
        if len(ordered) < trigger_count:
            continue
        timestamps = ordered[-trigger_count:]
        window = _aligned_window(parsed_by_ref, conditions, timestamps, trigger_count)
        if window is None:
            continue

        metric_instance_id = str(anchor_key)
        dimensions = build_dimensions(anchor_key, instance_id_keys)
        monitor_instance_id = _extract_monitor_instance_id_by_key(
            anchor_key,
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
        sub_dimension_keys = [key for key in instance_id_keys if key != "instance_id"]
        dimension_value = format_dimension_value(
            dimensions,
            ordered_keys=sub_dimension_keys,
            name_map=dimension_name_map,
        )
        condition_values = {ref: values[-1] for ref, values in window.items()}
        raw_series = {}
        for ref, item in joined.items():
            copied = dict(item)
            copied["values"] = [pair for pair in (item.get("values") or []) if _timestamp_of(pair) in set(timestamps)]
            raw_series[ref] = copied
        raw_data = {"series": raw_series, "condition_values": condition_values}
        primary_value = condition_values[primary.get("ref")]
        primary_unit = display_units.get(primary.get("ref"), "")
        primary_enum = enum_maps.get(primary.get("ref")) or {}
        formatted_primary = _format_value_with_unit(primary_value, primary_unit, primary_enum)

        matched_level = _matched_level(level_conditions, gate_conditions, window, levels)
        base_event = {
            "metric_instance_id": metric_instance_id,
            "monitor_instance_id": monitor_instance_id,
            "dimensions": dimensions,
            "value": primary_value,
            "timestamp": timestamps[-1],
            "raw_data": raw_data,
        }
        if matched_level is None:
            info_events.append(
                {
                    **base_event,
                    "level": "info",
                    "content": "info",
                }
            )
            continue

        context = {
            "monitor_object": template_context.get("monitor_object", ""),
            "instance_name": display_name,
            "resource_name": resource_name,
            "metric_name": template_context.get("metric_name", ""),
            "level": matched_level,
            "value": formatted_primary,
            "current_value": formatted_primary,
            "baseline_value": "",
            "dimension_value": dimension_value,
            **resource_context,
        }
        context.update(build_metric_template_vars(dimensions))
        for ref, number in condition_values.items():
            context[f"{ref}_value"] = _format_value_with_unit(
                number,
                display_units.get(ref, ""),
                enum_maps.get(ref) or {},
            )
            context[f"{ref}_metric_name"] = metric_names.get(ref, ref)
        content = Template(alert_name or "").safe_substitute(context)
        alert_events.append(
            {
                **base_event,
                "level": matched_level,
                "content": content,
            }
        )

    return alert_events, info_events, []


def _timestamp_of(pair):
    if not isinstance(pair, (list, tuple)) or not pair:
        return None
    try:
        return int(pair[0])
    except (TypeError, ValueError):
        return pair[0]


def _matched_level(level_conditions, gate_conditions, window, levels):
    for level in levels:
        if not _gates_pass(gate_conditions, window):
            return None
        if _levels_pass(level_conditions, window, level):
            return level
    return None


def _gates_pass(gate_conditions, window):
    for condition in gate_conditions:
        threshold = (condition.get("threshold") or [None])[0]
        if not isinstance(threshold, dict):
            return False
        values = window.get(condition.get("ref")) or []
        if not values or not _all_meet_threshold(values, threshold.get("method"), threshold.get("value")):
            return False
    return True


def _levels_pass(level_conditions, window, level):
    for condition in level_conditions:
        threshold = _threshold_for_level(condition, level)
        if threshold is None:
            return False
        values = window.get(condition.get("ref")) or []
        if not values or not _all_meet_threshold(values, threshold.get("method"), threshold.get("value")):
            return False
    return True


def summarize_multi_rows(series_by_ref, conditions, n=1):
    """给试跑用的逐行说明。不产生告警事件。"""
    conditions = [item for item in conditions or [] if isinstance(item, dict)]
    if len(conditions) < 2:
        return []
    anchor = conditions[0]
    anchor_ref = anchor.get("ref")
    level_conditions = [item for item in conditions if item.get("role") == "level"]
    gate_conditions = [item for item in conditions if item.get("role") == "gate"]
    if not level_conditions:
        return []
    trigger_count = max(1, int(n or 1))
    indexed = {
        item.get("ref"): _index_series(series_by_ref.get(item.get("ref")) or [], item.get("group_by") or [])
        for item in conditions
    }
    primary_ref = level_conditions[0].get("ref")
    rows = []
    for anchor_key, anchor_item in indexed.get(anchor_ref, {}).items():
        joined = {anchor_ref: anchor_item}
        missing_refs = []
        for condition in conditions[1:]:
            ref = condition.get("ref")
            join_key = _series_key(anchor_item.get("metric"), condition.get("group_by") or [])
            matched = indexed.get(ref, {}).get(join_key)
            if matched is None:
                missing_refs.append(ref)
                continue
            joined[ref] = matched
        rows.append(
            _summarize_joined_row(
                anchor_key,
                joined,
                missing_refs,
                conditions,
                level_conditions,
                gate_conditions,
                primary_ref,
                trigger_count,
            )
        )
    return rows


def _summarize_joined_row(
    anchor_key,
    joined,
    missing_refs,
    conditions,
    level_conditions,
    gate_conditions,
    primary_ref,
    trigger_count,
):
    if missing_refs:
        return {
            "metric_instance_id": str(anchor_key),
            "missing_refs": missing_refs,
            "short": False,
            "hit_count": 0,
            "matched_level": None,
            "levels_differ": False,
            "reason_kind": "missing",
            "reason_ref": missing_refs[0],
            "primary_value": _last_finite_value(joined.get(primary_ref)),
            "row_matched_threshold": None,
            "conditions": [_unjudged_condition_view(condition, joined.get(condition.get("ref"))) for condition in conditions],
        }

    parsed_by_ref = {ref: _values_by_timestamp(item) for ref, item in joined.items()}
    common = None
    for parsed in parsed_by_ref.values():
        stamps = {timestamp for timestamp, value in parsed.items() if value is not None}
        common = stamps if common is None else common & stamps
    ordered = sorted(common or [])
    hit_count = _combination_hit_count(
        parsed_by_ref,
        ordered[-trigger_count:],
        level_conditions,
        gate_conditions,
    )
    if len(ordered) < trigger_count:
        return {
            "metric_instance_id": str(anchor_key),
            "missing_refs": [],
            "short": True,
            "hit_count": hit_count,
            "matched_level": None,
            "levels_differ": False,
            "reason_kind": "short",
            "reason_ref": None,
            "primary_value": _last_common_value(parsed_by_ref, ordered, primary_ref),
            "row_matched_threshold": None,
            "conditions": [_unjudged_condition_view(condition, joined.get(condition.get("ref"))) for condition in conditions],
        }

    timestamps = ordered[-trigger_count:]
    window = {}
    for condition in conditions:
        ref = condition.get("ref")
        window[ref] = [parsed_by_ref[ref][timestamp] for timestamp in timestamps]
    levels = _levels_high_to_low(conditions)
    matched_level = _matched_level(level_conditions, gate_conditions, window, levels)
    condition_views = []
    hit_levels = []
    for condition in conditions:
        ref = condition.get("ref")
        values = window.get(ref) or []
        if condition.get("role") == "gate":
            threshold = (condition.get("threshold") or [None])[0]
            passed = _gates_pass([condition], window)
            condition_views.append(
                {
                    "ref": ref,
                    "value": values[-1] if values else None,
                    "gate_passed": passed,
                    "matched_threshold": _threshold_payload(threshold) if passed else None,
                }
            )
            continue
        hit_level, hit_threshold = _highest_level_met(condition, values)
        hit_levels.append(hit_level)
        condition_views.append(
            {
                "ref": ref,
                "value": values[-1] if values else None,
                "hit_level": hit_level,
                "matched_threshold": _threshold_payload(hit_threshold),
            }
        )
    failing_gate = next(
        (view for view in condition_views if "gate_passed" in view and not view["gate_passed"]),
        None,
    )
    missing_level = next(
        (view for view in condition_views if "hit_level" in view and not view["hit_level"]),
        None,
    )
    if matched_level:
        reason_kind = "trigger"
        reason_ref = None
    elif failing_gate is not None:
        reason_kind = "gate"
        reason_ref = failing_gate.get("ref")
    elif missing_level is not None:
        reason_kind = "miss"
        reason_ref = missing_level.get("ref")
    else:
        reason_kind = "miss"
        reason_ref = level_conditions[0].get("ref")
    known_levels = [level for level in hit_levels if level]
    primary_threshold = _threshold_for_level(level_conditions[0], matched_level) if matched_level else None
    return {
        "metric_instance_id": str(anchor_key),
        "missing_refs": [],
        "short": False,
        "hit_count": hit_count,
        "matched_level": matched_level,
        "levels_differ": len(set(known_levels)) > 1,
        "reason_kind": reason_kind,
        "reason_ref": reason_ref,
        "primary_value": window.get(primary_ref, [None])[-1],
        "row_matched_threshold": _threshold_payload(primary_threshold),
        "conditions": condition_views,
    }


def _combination_hit_count(parsed_by_ref, timestamps, level_conditions, gate_conditions):
    hits = 0
    for timestamp in timestamps:
        point_window = {}
        complete = True
        for ref, parsed in parsed_by_ref.items():
            value = parsed.get(timestamp)
            if value is None:
                complete = False
                break
            point_window[ref] = [value]
        if complete and _point_combination_hit(level_conditions, gate_conditions, point_window):
            hits += 1
    return hits


def _point_combination_hit(level_conditions, gate_conditions, point_window):
    if not _gates_pass(gate_conditions, point_window):
        return False
    for condition in level_conditions:
        values = point_window.get(condition.get("ref")) or []
        if not values or _highest_level_met(condition, values)[0] is None:
            return False
    return True


def _highest_level_met(condition, values):
    for level in _levels_high_to_low([condition]):
        threshold = _threshold_for_level(condition, level)
        if threshold is None or not values:
            continue
        if _all_meet_threshold(values, threshold.get("method"), threshold.get("value")):
            return level, threshold
    return None, None


def _threshold_payload(item):
    if not isinstance(item, dict):
        return None
    payload = {"method": item.get("method"), "value": item.get("value")}
    if item.get("level"):
        payload["level"] = item.get("level")
    return payload


def _last_finite_value(series_item):
    parsed = _values_by_timestamp(series_item)
    for timestamp in sorted(parsed, reverse=True):
        if parsed[timestamp] is not None:
            return parsed[timestamp]
    return None


def _last_common_value(parsed_by_ref, ordered, ref):
    if not ordered:
        return _last_finite_value_from_parsed(parsed_by_ref.get(ref) or {})
    return (parsed_by_ref.get(ref) or {}).get(ordered[-1])


def _last_finite_value_from_parsed(parsed):
    for timestamp in sorted(parsed, reverse=True):
        if parsed[timestamp] is not None:
            return parsed[timestamp]
    return None


def _unjudged_condition_view(condition, series_item):
    view = {
        "ref": condition.get("ref"),
        "value": _last_finite_value(series_item),
        "matched_threshold": None,
    }
    if condition.get("role") == "gate":
        view["gate_passed"] = False
    else:
        view["hit_level"] = None
    return view
