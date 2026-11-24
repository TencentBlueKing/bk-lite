import json

from django.core.signing import Signer

TABLE_FIELDS = {"table", "nestedTable", "cab", "task"}
ROW_REFERENCE = "_itsm_row_ref"


def configured_table_columns(field):
    columns = field.get("children") or field.get("columns")
    if columns:
        return columns
    configured = (field.get("props") or {}).get("columns") or "名称:name\n数量:quantity:number"
    columns = []
    for line in str(configured).splitlines():
        label, *rest = line.split(":")
        key = (rest[0] if rest else label).strip()
        columns.append({"key": key, "label": label.strip(), "type": rest[1] if len(rest) > 1 else "input"})
    return columns


def hidden_column(field, permissions):
    return field.get("state") == "hidden" or permissions.get(field.get("key"), permissions.get("*")) == "hidden"


def _row_signature(row, index, context, field_key):
    signer = Signer(salt="itsm-table-row")
    value = json.dumps([context, field_key, index, row], sort_keys=True, separators=(",", ":"))
    return signer.signature(value)


def visible_table_rows(rows, columns, context, field_key, *, preserve_hidden):
    if not isinstance(rows, list):
        return []
    output = []
    for index, row in enumerate(rows):
        if isinstance(row, dict):
            visible = {key: value for key, value in row.items() if key in columns}
            if preserve_hidden:
                visible[ROW_REFERENCE] = _row_signature(row, index, context, field_key)
            output.append(visible)
    return output


def merge_table_rows(field, old_rows, rows, permissions, context):
    if not isinstance(rows, list):
        return rows
    columns = configured_table_columns(field)
    visible = {column["key"] for column in columns if column.get("key") and not hidden_column(column, permissions)}
    protected = {column["key"] for column in columns if column.get("key") and hidden_column(column, permissions)}
    if not visible:
        return old_rows
    previous = {
        _row_signature(row, index, context, field["key"]): {key: value for key, value in row.items() if key in protected}
        for index, row in enumerate(old_rows if isinstance(old_rows, list) else [])
        if protected and isinstance(row, dict)
    }
    result = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError({field["key"]: "表格行格式错误"})
        reference = row.get(ROW_REFERENCE)
        hidden = {}
        if reference is not None:
            if not isinstance(reference, str) or reference not in previous:
                raise ValueError({field["key"]: "表格数据已变化，请刷新后重试"})
            hidden = previous.pop(reference)
        result.append({**hidden, **{key: value for key, value in row.items() if key in visible}})
    return result
