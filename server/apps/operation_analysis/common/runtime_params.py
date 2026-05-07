from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from rest_framework.exceptions import ValidationError


RUNTIME_EXTRA_PARAM_NAMES = {"namespace_id", "page", "page_size", "query_list"}


def _format_datetime(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, str) and value.strip():
        return value.strip()
    raise ValidationError("时间参数格式不合法")


def _normalize_time_range(value: Any) -> list[str]:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        end_time = datetime.now()
        start_time = end_time - timedelta(minutes=int(value))
        return [_format_datetime(start_time), _format_datetime(end_time)]

    if isinstance(value, (list, tuple)) and len(value) == 2:
        return [_format_datetime(value[0]), _format_datetime(value[1])]

    if isinstance(value, dict):
        select_value = value.get("selectValue")
        if isinstance(select_value, (int, float)) and not isinstance(select_value, bool) and select_value > 0:
            end_time = datetime.now()
            start_time = end_time - timedelta(minutes=int(select_value))
            return [_format_datetime(start_time), _format_datetime(end_time)]
        start = value.get("start")
        end = value.get("end")
        if start and end:
            return [_format_datetime(start), _format_datetime(end)]

    raise ValidationError("timeRange 参数格式不合法")


def _normalize_query_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValidationError("query_list 必须为数组")

    normalized = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ValidationError(f"query_list[{index}] 必须为对象")
        field = item.get("field")
        query_type = item.get("type")
        if not isinstance(field, str) or not field.strip():
            raise ValidationError(f"query_list[{index}].field 不能为空")
        if not isinstance(query_type, str) or not query_type.strip():
            raise ValidationError(f"query_list[{index}].type 不能为空")
        normalized_item = {"field": field.strip(), "type": query_type.strip()}
        if "value" in item:
            if not isinstance(item["value"], str):
                raise ValidationError(f"query_list[{index}].value 必须为字符串")
            normalized_item["value"] = item["value"].strip()
        if "start" in item:
            normalized_item["start"] = _format_datetime(item["start"])
        if "end" in item:
            normalized_item["end"] = _format_datetime(item["end"])
        normalized.append(normalized_item)
    return normalized


def _normalize_positive_int(name: str, value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{name} 必须为正整数")
    if parsed <= 0:
        raise ValidationError(f"{name} 必须为正整数")
    return parsed


def _normalize_param_value(param_type: str, value: Any) -> Any:
    if param_type == "string":
        if isinstance(value, str):
            return value
        raise ValidationError("string 参数必须为字符串")

    if param_type == "number":
        if isinstance(value, bool):
            raise ValidationError("number 参数必须为数字")
        if isinstance(value, (int, float)):
            return value
        if isinstance(value, str):
            try:
                number = Decimal(value)
            except InvalidOperation:
                raise ValidationError("number 参数必须为数字")
            return float(number) if "." in value else int(number)
        raise ValidationError("number 参数必须为数字")

    if param_type == "boolean":
        if isinstance(value, bool):
            return value
        raise ValidationError("boolean 参数必须为布尔值")

    if param_type == "date":
        return _format_datetime(value)

    if param_type == "timeRange":
        return _normalize_time_range(value)

    return value


def build_runtime_params(param_schema: Any, raw_params: Any) -> dict[str, Any]:
    schema_items = param_schema if isinstance(param_schema, list) else []
    request_params = dict(raw_params or {})

    allowed_param_names = {
        item.get("name")
        for item in schema_items
        if isinstance(item, dict) and isinstance(item.get("name"), str) and item.get("name").strip()
    }
    unknown_keys = set(request_params) - allowed_param_names - RUNTIME_EXTRA_PARAM_NAMES
    if unknown_keys:
        keys = ", ".join(sorted(str(key) for key in unknown_keys))
        raise ValidationError(f"存在未声明的数据源参数: {keys}")

    normalized: dict[str, Any] = {}
    for item in schema_items:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        name = name.strip()
        param_type = item.get("type") or "string"
        filter_type = item.get("filterType") or "fixed"
        default_value = item.get("value")
        has_input = name in request_params

        if filter_type == "fixed":
            if has_input and request_params[name] != default_value:
                raise ValidationError(f"固定参数 {name} 不允许被覆盖")
            if default_value not in (None, ""):
                normalized[name] = _normalize_param_value(param_type, default_value)
            continue

        if has_input:
            normalized[name] = _normalize_param_value(param_type, request_params[name])
            continue

        if default_value not in (None, ""):
            normalized[name] = _normalize_param_value(param_type, default_value)

    if "namespace_id" in request_params:
        normalized["namespace_id"] = _normalize_positive_int("namespace_id", request_params["namespace_id"])
    if "page" in request_params:
        normalized["page"] = _normalize_positive_int("page", request_params["page"])
    if "page_size" in request_params:
        normalized["page_size"] = _normalize_positive_int("page_size", request_params["page_size"])
    if "query_list" in request_params:
        normalized["query_list"] = _normalize_query_list(request_params["query_list"])

    return normalized
