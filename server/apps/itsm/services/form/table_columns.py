import json

from django.core.signing import Signer

from .rules import match_when

TABLE_FIELDS = {"table", "nestedTable", "cab", "task"}
ROW_REFERENCE = "_itsm_row_ref"


def configured_table_columns(field):
    columns = field.get("children") or field.get("columns")
    if columns:
        return columns
    configured = (field.get("props") or {}).get("columns")
    if field.get("children") == [] and not configured:
        return []
    configured = configured or "名称:name\n数量:quantity:number"
    columns = []
    for line in str(configured).splitlines():
        label, *rest = line.split(":")
        key = (rest[0] if rest else label).strip()
        columns.append({"key": key, "label": label.strip(), "type": rest[1] if len(rest) > 1 else "input"})
    return columns


def hidden_column(field, permissions):
    return field.get("state") == "hidden" or permissions.get(field.get("key"), permissions.get("*")) == "hidden"


def protected_column(field, permissions):
    return field.get("state") in {"hidden", "readonly", "disabled"} or permissions.get(field.get("key"), permissions.get("*")) in {
        "hidden",
        "readonly",
        "read",
    }


def row_signature(row, index, context, field_key):
    signer = Signer(salt="itsm-table-row")
    value = json.dumps([context, field_key, index, row], sort_keys=True, separators=(",", ":"))
    return signer.signature(value)


def visible_table_rows(rows, columns, context, field_key, *, preserve_hidden, labels=None):
    if not isinstance(rows, list):
        return []
    output = []
    for index, row in enumerate(rows):
        if isinstance(row, dict):
            visible = {
                column["key"]: row[column["key"]]
                for column in columns
                if column["key"] in row and match_when(column.get("visibleWhen"), row, strict=False)
            }
            row_labels = {key: labels[f"{field_key}.{index}.{key}"] for key in visible if labels and f"{field_key}.{index}.{key}" in labels}
            if row_labels:
                visible["_field_labels"] = row_labels
            if preserve_hidden:
                visible[ROW_REFERENCE] = row_signature(row, index, context, field_key)
            output.append(visible)
    return output


def merge_table_rows(field, old_rows, rows, permissions, context):
    if not isinstance(rows, list):
        return rows
    columns = configured_table_columns(field)
    editable = {column["key"]: column for column in columns if column.get("key") and not protected_column(column, permissions)}
    protected = {column["key"] for column in columns if column.get("key") and protected_column(column, permissions)}
    if not editable:
        return old_rows
    preserve = bool(protected) or any(column.get("visibleWhen") or column.get("fetch") for column in editable.values())
    previous = {
        row_signature(row, index, context, field["key"]): row
        for index, row in enumerate(old_rows if isinstance(old_rows, list) else [])
        if preserve and isinstance(row, dict)
    }
    result = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError({field["key"]: "表格行格式错误"})
        reference = row.get(ROW_REFERENCE)
        original = {}
        if reference is not None:
            if not isinstance(reference, str) or reference not in previous:
                raise ValueError({field["key"]: "表格数据已变化，请刷新后重试"})
            original = previous.pop(reference)
        merged = {key: original[key] for key in protected if key in original}
        candidate = {**merged, **{key: row[key] for key in editable if key in row}}
        for key, column in editable.items():
            if match_when(column.get("visibleWhen"), candidate, strict=False):
                if key in row:
                    merged[key] = row[key]
            elif key in original and column.get("hideValueClearMode") != "clear":
                merged[key] = original[key]
        result.append(merged)
    return result
