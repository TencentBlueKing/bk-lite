from typing import Any

from apps.itsm.services.form.options import resolve_options
from apps.itsm.services.form.rules import ExpressionError, evaluate_expr, match_when
from apps.itsm.services.form.schema import FIELD_TYPES, LAYOUT_ONLY, FormSchemaModel

LIST_TYPES = {"checkbox", "multiselect", "user", "group", "attachment"}


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
        for rule in self.schema.rules:
            if rule.type == "compute" and rule.expr:
                try:
                    values[rule.field] = evaluate_expr(rule.expr, values)
                except ExpressionError as exc:
                    return {}, {rule.field: str(exc)}
        errors: dict[str, str] = {}
        cleaned: dict[str, Any] = {}
        wildcard = self.field_perm.get("*", "editable")
        required_by_rule = {rule.field for rule in self.schema.rules if rule.type == "required" and match_when(rule.when, values)}
        for field in self.schema.fields:
            if field.type in LAYOUT_ONLY:
                continue
            if field.type not in FIELD_TYPES:
                errors[field.key] = "未知控件"
                continue
            visible = _is_visible(self.schema, field.key, values)
            mode = self.field_perm.get(field.key, wildcard)
            if not visible or mode == "hidden":
                continue
            if mode == "readonly":
                continue
            raw = values.get(field.key, field.default)
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


def _is_visible(schema: FormSchemaModel, key: str, data: dict[str, Any]) -> bool:
    visible = True
    for rule in schema.rules:
        if rule.type == "visible" and rule.field == key:
            visible = match_when(rule.when, data)
    return visible


def _empty(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def _check_type(field: dict[str, Any], value: Any, dictionary_lookup) -> str:
    kind = field["type"]
    if kind == "number" and not isinstance(value, (int, float)):
        return "必须是数字"
    if kind in {"input", "textarea", "richtext", "radio", "select", "datetime"} and not isinstance(value, str):
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
    if kind == "number" and isinstance(value, (int, float)):
        if props.get("min") is not None and value < props["min"]:
            return "小于最小值"
        if props.get("max") is not None and value > props["max"]:
            return "大于最大值"
    if kind in {"radio", "select"}:
        options = resolve_options(field, dictionary_lookup)
        allowed = {item.get("value") for item in options} if options else set()
        if allowed and value not in allowed:
            return "选项不存在"
    return ""
