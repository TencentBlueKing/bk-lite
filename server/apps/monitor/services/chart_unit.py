from copy import deepcopy

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.utils.unit_converter import UnitConverter


def resolve_chart_unit(metric_unit="", calculation_unit="", threshold_unit=""):
    return threshold_unit or calculation_unit or metric_unit or ""


def _validate_conversion(source_unit, target_unit):
    if (
        source_unit
        and target_unit
        and source_unit != target_unit
        and not UnitConverter.is_convertible(source_unit, target_unit)
    ):
        raise BaseAppException(
            f"chart unit is not convertible: {source_unit} -> {target_unit}"
        )


def _convert_points_in_place(points, source_unit, target_unit):
    if not source_unit or not target_unit or source_unit == target_unit:
        return

    point_indexes = []
    values = []
    for index, point in enumerate(points or []):
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            continue
        if point[1] is None:
            continue
        point_indexes.append(index)
        values.append(float(point[1]))

    converted_values = UnitConverter.convert_values(
        values, source_unit, target_unit
    )
    for point_index, converted_value in zip(point_indexes, converted_values):
        timestamp = points[point_index][0]
        points[point_index] = [timestamp, str(converted_value)]


def convert_vm_result_copy(data, source_unit, target_unit):
    _validate_conversion(source_unit, target_unit)
    converted = deepcopy(data)
    for result in converted.get("data", {}).get("result", []):
        _convert_points_in_place(
            result.get("values") or [], source_unit, target_unit
        )
    return converted


def convert_snapshots_copy(snapshots, source_unit, target_unit):
    _validate_conversion(source_unit, target_unit)
    converted = deepcopy(snapshots)
    for snapshot in converted:
        raw_data = snapshot.get("raw_data")
        if not isinstance(raw_data, dict):
            continue
        _convert_points_in_place(
            raw_data.get("values") or [], source_unit, target_unit
        )
    return converted
