from datetime import datetime
from typing import Any


def _is_empty(value: Any) -> bool:
    return value is None or value == ""


def _is_boolean_values(values: list[Any]) -> bool:
    return bool(values) and all(isinstance(value, bool) for value in values)


def _is_number_values(values: list[Any]) -> bool:
    if not values:
        return False

    for value in values:
        if isinstance(value, bool):
            return False
        try:
            float(value)
        except (TypeError, ValueError):
            return False
    return True


def _is_datetime_values(values: list[Any]) -> bool:
    if not values:
        return False

    for value in values:
        if isinstance(value, datetime):
            continue
        if not isinstance(value, str):
            return False
        text = value.strip()
        if not text:
            return False
        normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
        try:
            datetime.fromisoformat(normalized)
        except ValueError:
            return False
    return True


def _infer_value_type(values: list[Any]) -> str:
    non_empty = [value for value in values if not _is_empty(value)]
    if _is_boolean_values(non_empty):
        return "boolean"
    if _is_number_values(non_empty):
        return "number"
    if _is_datetime_values(non_empty):
        return "datetime"
    return "string"


def infer_fields(rows: list[Any], sample_size: int = 100) -> list[dict[str, str]]:
    first_record = next((row for row in rows if isinstance(row, dict) and row), None)
    if not first_record:
        return []

    keys = list(first_record.keys())
    sample_rows = [row for row in rows[:sample_size] if isinstance(row, dict)]

    return [
        {
            "key": key,
            "title": key,
            "value_type": _infer_value_type([row.get(key) for row in sample_rows]),
        }
        for key in keys
    ]
