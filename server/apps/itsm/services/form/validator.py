from typing import Any

from apps.itsm.services.form.options import option_values, resolve_options
from apps.itsm.services.form.rules import ExpressionError, evaluate_expr, match_when
from apps.itsm.services.form.schema import FIELD_TYPES, LAYOUT_ONLY, FormSchemaModel
from apps.itsm.services.form.table_columns import TABLE_FIELDS

LIST_TYPES = {
    "checkbox",
    "multiselect",
    "user",
    "group",
    "attachment",
    "multiUser",
    "multiCascade",
    "userGroup",
    "multiUserGroup",
    "dateRange",
    "multiCmdb",
    "associateConfig",
    "task",
    "nestedTable",
    "subProcessForm",
}
STRING_TYPES = {
    "input",
    "textarea",
    "richtext",
    "radio",
    "select",
    "datetime",
    "date",
    "time",
    "cascade",
    "link",
    "organization",
    "singleAssociateConfig",
    "signature",
}
NUMBER_TYPES = {"number", "calculate"}


class FormValidator:
    def __init__(self, schema: dict[str, Any], field_perm: dict[str, str] | None = None, dictionary_lookup=None):
        self.schema = FormSchemaModel.model_validate(schema)
        self.field_perm = field_perm or {}
        self.dictionary_lookup = dictionary_lookup

    def _fields(self, *, include_table_columns=True):
        def walk(fields, inherited="editable"):
            for field in fields:
                mode = self.field_perm.get(field.key, self.field_perm.get("*", "editable"))
                if inherited in {"readonly", "hidden"}:
                    mode = inherited
                if field.state in {"readonly", "disabled"}:
                    mode = "readonly"
                elif field.state == "hidden":
                    mode = "hidden"
                yield field, mode
                if include_table_columns or field.type not in TABLE_FIELDS:
                    yield from walk(field.children, mode)

        yield from walk(self.schema.fields)

    def merge(self, original, incoming):
        writable = {
            field.key
            for field, mode in self._fields(include_table_columns=False)
            if mode not in {"readonly", "hidden"} and field.type not in LAYOUT_ONLY
        }
        accepted = {key: value for key, value in incoming.items() if key in writable}
        cleaned, errors = self.apply({**original, **accepted})
        return {**original, **cleaned}, errors

    def validate(self, data: dict[str, Any] | None) -> dict[str, str]:
        cleaned, errors = self.apply(data or {})
        self.cleaned = cleaned
        return errors

    def apply(self, data: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
        values = dict(data)
        kinds = {field.key: field.type for field in self.schema.fields}
        for key, raw in list(values.items()):
            values[key] = _coerce(kinds.get(key, ""), raw)
        compute_rules = {rule.field: rule for rule in self.schema.rules if rule.type == "compute" and rule.expr}
        errors: dict[str, str] = {}
        cleaned: dict[str, Any] = {}
        visible_keys = visible_field_keys(self.schema, values)
        required_by_rule = {rule.field for rule in self.schema.rules if rule.type == "required" and match_when(rule.when, values, strict=False)}
        for field, inherited_mode in self._fields(include_table_columns=False):
            if field.type in LAYOUT_ONLY:
                continue
            if field.type not in FIELD_TYPES:
                errors[field.key] = "未知控件"
                continue
            visible = field.key in visible_keys
            mode = inherited_mode
            if not visible or mode == "hidden" or field.state == "hidden":
                continue
            if mode == "readonly" or field.state in {"readonly", "disabled"}:
                continue
            raw = _coerce(field.type, values.get(field.key, field.default))
            if _empty(raw) and field.key in compute_rules:
                try:
                    raw = evaluate_expr(compute_rules[field.key].expr or "", values)
                    values[field.key] = raw
                    visible_keys = visible_field_keys(self.schema, values)
                except ExpressionError as exc:
                    errors[field.key] = str(exc)
                    continue
            required = field.required or mode == "required" or field.key in required_by_rule
            if _empty(raw):
                if required:
                    errors[field.key] = "必填"
                else:
                    cleaned[field.key] = raw
                continue
            type_error = _check_type(field.model_dump(), raw, self.dictionary_lookup)
            if not type_error and field.type in TABLE_FIELDS:
                raw, type_error = self._validate_rows(field, raw)
            if type_error:
                errors[field.key] = type_error
            else:
                cleaned[field.key] = raw
        return cleaned, errors

    def _validate_rows(self, field, rows):
        columns = []
        for column in field.children:
            mode = self.field_perm.get(column.key, self.field_perm.get("*"))
            if mode not in {"readonly", "hidden"} and column.state not in {"hidden", "disabled", "readonly"}:
                columns.append((column, column.model_dump(), column.required or mode == "required"))
        cleaned = []
        for index, row in enumerate(rows, 1):
            if not isinstance(row, dict):
                return [], f"第 {index} 行格式错误"
            values = dict(row)
            for column, config, required in columns:
                if not match_when(column.visibleWhen, row, strict=False):
                    continue
                value = _coerce(column.type, row.get(column.key))
                label = column.label or column.key
                if _empty(value):
                    if required:
                        return [], f"请填写第 {index} 行的{label}"
                    continue
                error = _check_type(config, value, self.dictionary_lookup)
                if error:
                    return [], f"第 {index} 行的{label}：{error}"
                values[column.key] = value
            cleaned.append(values)
        return cleaned, ""


def _coerce(kind: str, value: Any) -> Any:
    if (
        kind in TABLE_FIELDS
        and isinstance(value, list)
        and len(value) == 1
        and isinstance(value[0], dict)
        and all(_empty(v) for v in value[0].values())
    ):
        return []
    if kind != "number" or not isinstance(value, str):
        return value
    text = value.strip()
    if not text:
        return value
    try:
        return float(text) if "." in text else int(text)
    except ValueError:
        return value


def visible_field_keys(schema: FormSchemaModel, data: dict[str, Any]) -> set[str]:
    rules = {rule.field: rule.when for rule in schema.rules if rule.type == "visible"}
    visible = set()

    def visit(fields):
        for field in fields:
            if field.state == "hidden" or not match_when(rules.get(field.key, field.visibleWhen), data, strict=False):
                continue
            visible.add(field.key)
            visit(field.children)

    visit(schema.fields)
    return visible


def _walk(fields):
    for field in fields:
        yield field
        yield from _walk(field.children)


def _bound(value: Any) -> int | float | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return value
    try:
        text = str(value).strip()
        return float(text) if "." in text else int(text)
    except ValueError:
        return None


def _empty(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def _check_type(field: dict[str, Any], value: Any, dictionary_lookup) -> str:
    kind = field["type"]
    if kind in NUMBER_TYPES and (isinstance(value, bool) or not isinstance(value, (int, float))):
        return "必须是数字"
    if (
        kind in STRING_TYPES
        and not isinstance(value, str)
        and not (kind in {"select", "radio", "cascade"} and isinstance(value, (int, float)) and not isinstance(value, bool))
    ):
        return "必须是字符串"
    if kind in LIST_TYPES and not isinstance(value, list):
        return "必须是列表"
    if kind in TABLE_FIELDS and not isinstance(value, list):
        return "必须是表格"
    if kind == "cmdb":
        if not isinstance(value, list) or any(not isinstance(item, dict) or "inst_id" not in item for item in value):
            return "CMDB 值不合法"
    props = field.get("props") or {}
    if kind == "input" and isinstance(value, str) and props.get("maxLength") and len(value) > int(props["maxLength"]):
        return "超过长度限制"
    if kind in NUMBER_TYPES and isinstance(value, (int, float)) and not isinstance(value, bool):
        lower = _bound(props.get("min"))
        upper = _bound(props.get("max"))
        if lower is not None and value < lower:
            return "小于最小值"
        if upper is not None and value > upper:
            return "大于最大值"
    if kind in {"radio", "select", "cascade", "checkbox", "multiselect", "multiCascade"}:
        options = resolve_options(field, dictionary_lookup)
        allowed = set(option_values(options))
        chosen = value if isinstance(value, list) else [value]
        if any(isinstance(item, (dict, list)) or (allowed and item not in allowed) for item in chosen):
            return "选项不存在"
    return ""
