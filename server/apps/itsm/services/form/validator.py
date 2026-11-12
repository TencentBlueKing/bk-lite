from typing import Any

from apps.itsm.services.form.options import resolve_options
from apps.itsm.services.form.rules import ExpressionError, evaluate_expr, match_when
from apps.itsm.services.form.schema import FIELD_TYPES, LAYOUT_ONLY, FormSchemaModel

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
        wildcard = self.field_perm.get("*", "editable")
        required_by_rule = {rule.field for rule in self.schema.rules if rule.type == "required" and match_when(rule.when, values)}
        for field in _walk(self.schema.fields):
            if field.type in LAYOUT_ONLY:
                continue
            if field.type not in FIELD_TYPES:
                errors[field.key] = "未知控件"
                continue
            visible = _is_visible(self.schema, field.key, values)
            mode = self.field_perm.get(field.key, wildcard)
            if not visible or mode == "hidden" or field.state == "hidden":
                continue
            if mode == "readonly" or field.state in {"readonly", "disabled"}:
                continue
            raw = _coerce(field.type, values.get(field.key, field.default))
            if _empty(raw) and field.key in compute_rules:
                try:
                    raw = evaluate_expr(compute_rules[field.key].expr or "", values)
                    values[field.key] = raw
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
            if type_error:
                errors[field.key] = type_error
            else:
                cleaned[field.key] = raw
        return cleaned, errors


def _coerce(kind: str, value: Any) -> Any:
    if kind != "number" or not isinstance(value, str):
        return value
    text = value.strip()
    if not text:
        return value
    try:
        return float(text) if "." in text else int(text)
    except ValueError:
        return value


def _is_visible(schema: FormSchemaModel, key: str, data: dict[str, Any]) -> bool:
    visible = True
    field = schema.field_map().get(key)
    if field is not None and field.visibleWhen:
        visible = match_when(field.visibleWhen, data)
    for rule in schema.rules:
        if rule.type == "visible" and rule.field == key:
            visible = match_when(rule.when, data)
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
    if kind in STRING_TYPES and not isinstance(value, str):
        return "必须是字符串"
    if kind in LIST_TYPES and not isinstance(value, list):
        return "必须是列表"
    if kind == "table" and not isinstance(value, list):
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
        allowed = {item.get("value") for item in options} if options else set()
        chosen = value if isinstance(value, list) else [value]
        if allowed and any(item not in allowed for item in chosen):
            return "选项不存在"
    return ""
