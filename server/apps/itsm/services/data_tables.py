"""数据表结构和行数据共用类型约束。"""

import math
import re
from datetime import date, datetime

TYPES = {"string", "number", "boolean", "date", "datetime", "object", "array"}


def validate_fields(fields):
    if not isinstance(fields, list) or not 1 <= len(fields) <= 200:
        raise ValueError("请配置1至200个字段")
    result, seen = [], set()
    for field in fields:
        if not isinstance(field, dict):
            raise ValueError("字段格式无效")
        key, label, kind = field.get("key"), field.get("label") or field.get("key"), field.get("type", "string")
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", key) or key in seen:
            raise ValueError("字段标识须以字母开头，仅含字母、数字、下划线且不能重复")
        if not isinstance(label, str) or not label.strip() or len(label) > 128 or kind not in TYPES:
            raise ValueError("字段名称或类型无效")
        seen.add(key)
        result.append({"key": key, "label": label.strip(), "type": kind})
    return result


def validate_row(data, fields):
    if not isinstance(data, dict) or set(data) - {f["key"] for f in fields}:
        raise ValueError("数据必须为对象，且只能包含已配置字段")
    for field in fields:
        value = data.get(field["key"])
        if value is None:
            continue
        kind = field["type"]
        valid = {
            "string": isinstance(value, str),
            "number": type(value) in (int, float) and math.isfinite(value),
            "boolean": type(value) is bool,
            "object": isinstance(value, dict),
            "array": isinstance(value, list),
        }.get(kind, False)
        if kind in {"date", "datetime"}:
            try:
                if not isinstance(value, str):
                    raise ValueError()
                (date.fromisoformat if kind == "date" else datetime.fromisoformat)(value)
                valid = True
            except (ValueError, TypeError):
                valid = False
        if not valid:
            raise ValueError(f"字段「{field['label']}」不符合 {kind} 类型")
    return data


def field_definitions(table):
    return [{"key": f.key, "label": f.label or f.key, "type": f.field_type} for f in table.fields.order_by("id")]
