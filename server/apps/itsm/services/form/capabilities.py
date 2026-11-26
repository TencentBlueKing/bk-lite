"""字段取数能力契约；设计器与服务端共用此定义。"""

import math

from .schema import FIELD_TYPES

FIELD_CAPABILITIES = {kind: {"sources": [], "mode": None, "shape": None, "fill": False} for kind in FIELD_TYPES}
for kind in ("input", "textarea", "number"):
    FIELD_CAPABILITIES[kind] = {
        "sources": ["api", "python", "table"],
        "mode": "value",
        "shape": "number" if kind == "number" else "string",
        "fill": False,
    }
for kind in ("select", "multiselect", "radio", "checkbox", "cascade", "multiCascade"):
    tree = kind in {"cascade", "multiCascade"}
    FIELD_CAPABILITIES[kind] = {
        "sources": ["api", "python", "dictionary"] + ([] if tree else ["table"]),
        "mode": "options",
        "shape": "tree" if tree else "options",
        "fill": kind in {"select", "radio", "cascade"},
    }
for kind in ("table", "nestedTable"):
    FIELD_CAPABILITIES[kind] = {"sources": ["api", "python", "table"], "mode": "table", "shape": "rows", "fill": False}


def table_columns(field):
    columns = field.get("columns") or []
    if columns:
        return {c["key"]: c.get("type", "input") for c in columns}
    result = {}
    for line in str(field.get("props", {}).get("columns", "")).splitlines():
        parts = line.split(":")
        if len(parts) >= 2:
            result[parts[1].strip()] = parts[2].strip() if len(parts) > 2 else "input"
    return result


def validate_binding(field, *, inspect=False):
    cfg = field.get("fetch")
    if not cfg:
        return
    cap = FIELD_CAPABILITIES.get(field["type"], {})
    source = cfg.get("source")
    if source == "integration":
        source = cfg.get("snapshot", {}).get("kind") or cfg.get("integration_kind")
    if source not in cap.get("sources", []) or cfg.get("mode") != cap.get("mode"):
        raise ValueError(f"字段 {field['key']} 不支持此数据来源或取数用途")
    if cfg.get("trigger", "change") not in {"change", "manual"}:
        raise ValueError("取数时机无效")
    if not isinstance(cfg.get("inputs", {}), dict):
        raise ValueError("输入参数必须是对象")
    if cfg.get("fill") and not cap["fill"]:
        raise ValueError("只有单选字段支持选中后填充")
    for key in ("fill", "columns"):
        if not isinstance(cfg.get(key, {}), dict) or any(not isinstance(v, str) or not v for v in cfg.get(key, {}).values()):
            raise ValueError("字段映射必须是非空路径")
    if cfg["mode"] == "table" and not inspect:
        if not cfg.get("columns") or set(cfg["columns"]) - table_columns(field).keys():
            raise ValueError("表格映射必须使用已定义的目标列")
    if source == "dictionary":
        if cfg.get("inputs") or cfg.get("list_path"):
            raise ValueError("字典不支持输入参数或列表路径")
        if not cfg.get("transform_id") and (cfg.get("label_path", "label") != "label" or cfg.get("value_path", "value") != "value"):
            raise ValueError("字典使用固定的 label/value 字段")
    if source == "table" and cfg.get("list_path"):
        raise ValueError("数据表不支持列表路径")
    if source == "python":
        inputs = cfg.get("inputs", {})
        rows = inputs.get("rows", [])
        if set(inputs) - {"rows", "params"} or not isinstance(inputs.get("params", {}), dict):
            raise ValueError("Python 输入只支持 rows 数组和 params 对象")
        if not (isinstance(rows, list) and all(isinstance(row, dict) for row in rows)) and not (
            isinstance(rows, str) and rows.startswith("${form.") and rows.endswith("}")
        ):
            raise ValueError("Python rows 必须是对象数组或表格字段引用")


def validate_result(field, value):
    kind = field["type"]
    if kind == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError("数值字段取数结果必须是有限数值")
    elif kind in {"input", "textarea"}:
        if not isinstance(value, str):
            raise ValueError("文本字段取数结果必须是字符串")
    elif kind in {"table", "nestedTable"}:
        columns = table_columns(field)
        if not isinstance(value, list) or not columns:
            raise ValueError("表格取数结果必须是对象数组，且需先定义列")
        for row in value:
            if not isinstance(row, dict) or set(row) - columns.keys() or set(field.get("fetch", {}).get("columns", {})) - row.keys():
                raise ValueError("表格取数结果与列定义不匹配")
            for key, item in row.items():
                validate_result({"type": "number" if columns[key] in {"number", "integer", "float"} else "input"}, item)
