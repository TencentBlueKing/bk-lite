from datetime import datetime
from typing import Any


def apply_query_list_to_payload(payload: Any, query_list: Any) -> Any:
    conditions = _normalize_query_list(query_list)
    if not conditions:
        return payload

    if isinstance(payload, list):
        return [row for row in payload if _row_matches(row, conditions)]

    if isinstance(payload, dict) and isinstance(payload.get("items"), list):
        original_items = payload["items"]
        filtered_items = [row for row in original_items if _row_matches(row, conditions)]
        next_payload = dict(payload)
        next_payload["items"] = filtered_items
        total = payload.get("count")
        if total is None or total == len(original_items):
            next_payload["count"] = len(filtered_items)
        return next_payload

    return payload


def _normalize_query_list(query_list: Any) -> list[dict[str, Any]]:
    if query_list is None:
        return []
    if isinstance(query_list, dict):
        query_list = [query_list]
    if not isinstance(query_list, list):
        return []
    return [item for item in query_list if isinstance(item, dict) and item.get("field")]


def _row_matches(row: Any, conditions: list[dict[str, Any]]) -> bool:
    if not isinstance(row, dict):
        return False
    return all(_condition_matches(row, condition) for condition in conditions)


def _condition_matches(row: dict[str, Any], condition: dict[str, Any]) -> bool:
    field = condition.get("field")
    cond_type = condition.get("type")
    raw_value = row.get(field)

    if cond_type == "time":
        start = _parse_datetime(condition.get("start"))
        end = _parse_datetime(condition.get("end"))
        current = _parse_datetime(raw_value)
        if start is None or end is None or current is None:
            return False
        return start <= current <= end

    needle = str(condition.get("value") or "").strip().lower()
    if not needle:
        return True
    haystack = "" if raw_value is None else str(raw_value).lower()
    if cond_type == "str=":
        return haystack == needle
    return needle in haystack


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None
