"""监控 NATS 查询输入与响应的无副作用兼容接缝。"""

from datetime import datetime

from apps.monitor.services.metrics import Metrics


def normalize_monitor_query_data(query_data: dict) -> dict:
    normalized = dict(query_data or {})
    if "monitor_obj_id" not in normalized and "monitor_object_id" in normalized:
        normalized["monitor_obj_id"] = normalized["monitor_object_id"]
    if "start" not in normalized and "start_time" in normalized:
        normalized["start"] = normalized["start_time"]
    if "end" not in normalized and "end_time" in normalized:
        normalized["end"] = normalized["end_time"]
    return normalized


def normalize_positive_int(value, field_name: str, default=None):
    if value in (None, ""):
        return default
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} 必须是整数")
    if normalized < 1:
        raise ValueError(f"{field_name} 必须大于等于 1")
    return normalized


def normalize_bool(value, field_name: str):
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return False
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no"}:
            return False
    raise ValueError(f"{field_name} 必须是布尔值")


def normalize_time_value(value, field_name: str):
    if value in (None, ""):
        raise ValueError(f"{field_name} 不能为空")
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value)
    if isinstance(value, str):
        value = value.strip()
        if value.isdigit():
            return datetime.fromtimestamp(int(value))
        try:
            return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        except ValueError as exc:
            raise ValueError(f"{field_name} 时间格式错误，应为 YYYY-MM-DD HH:MM:SS 或时间戳") from exc
    raise ValueError(f"{field_name} 时间格式错误")


def normalize_filter_values(value, field_name: str):
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item not in (None, "")]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    raise ValueError(f"{field_name} 必须是字符串或列表")


def build_vm_query_failure_result(resp: dict, default_message: str):
    error_message = resp.get("error") or resp.get("message") or default_message
    error_type = resp.get("errorType")
    if error_type:
        error_message = f"{error_type}: {error_message}"
    return {"result": False, "data": [], "message": error_message}


def normalize_step(step):
    if step in (None, ""):
        return "5m"
    Metrics.parse_step_to_seconds(step)
    return step


def normalize_dimensions(metric, dimensions):
    if dimensions in (None, ""):
        return {}
    if not isinstance(dimensions, dict):
        raise ValueError("dimensions 必须是字典")

    allowed_dimensions = set(metric.instance_id_keys or [])
    for item in metric.dimensions or []:
        if isinstance(item, dict):
            name = item.get("name")
            if name:
                allowed_dimensions.add(name)
        elif item:
            allowed_dimensions.add(item)

    invalid_keys = [key for key in dimensions if key not in allowed_dimensions]
    if invalid_keys:
        raise ValueError(f"dimensions 包含未定义维度: {', '.join(invalid_keys)}")

    return {str(key): str(value) for key, value in dimensions.items() if value is not None}


def paginate_items(items: list, page, page_size):
    total_count = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    return {
        "count": total_count,
        "page": page,
        "page_size": page_size,
        "items": items[start:end],
    }
