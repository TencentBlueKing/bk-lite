"""基于工单版本快照的字段检索与导出。"""

import json
import math

from django.db import connection
from django.db.models import CharField, F, Func, Value
from django.db.models.fields.json import KeyTextTransform, KeyTransform, compile_json_path
from django.db.models.functions import Cast
from django.utils.dateparse import parse_date

from apps.itsm.models import WorkflowVersion
from apps.itsm.services.form.options import resolve_options
from apps.itsm.views.access import domain_of

MAX_FORM_FILTERS = 8
MAX_VALUE_LENGTH = 200
CHOICE_TYPES = {"radio", "select"}
TABLE_FIELDS = {"table", "nestedTable", "cab", "task"}
OPERATORS = {
    "input": ("contains", "eq"),
    "textarea": ("contains", "eq"),
    "number": ("eq", "gte", "lte"),
    "date": ("eq",),
    "radio": ("eq",),
    "select": ("eq",),
}


class InvalidFormFilter(ValueError):
    """可以向用户展示的筛选校验信息。"""


def read_form_filters(value):
    if isinstance(value, str):
        if len(value) > 16000:
            raise InvalidFormFilter("表单筛选条件过长")
        try:
            value = json.loads(value)
        except ValueError as exc:
            raise InvalidFormFilter("表单筛选条件格式错误") from exc
    if not isinstance(value, list) or len(value) > MAX_FORM_FILTERS:
        raise InvalidFormFilter(f"最多添加 {MAX_FORM_FILTERS} 个表单条件")
    clauses = []
    for item in value:
        if not isinstance(item, dict) or set(item) != {"key", "operator", "value"}:
            raise InvalidFormFilter("请选择表单字段、匹配方式并填写值")
        key, operator, raw = item["key"], item["operator"], item["value"]
        if not isinstance(key, str) or not key or not isinstance(operator, str):
            raise InvalidFormFilter("表单筛选条件格式错误")
        if isinstance(raw, str):
            raw = raw.strip()
            valid = 0 < len(raw) <= MAX_VALUE_LENGTH and "\x00" not in raw
        else:
            valid = is_number(raw)
        if not valid:
            raise InvalidFormFilter("请输入有效的条件值，文本最多 200 字")
        clauses.append({"key": key, "operator": operator, "value": raw})
    return clauses


def is_number(value):
    return type(value) in {float, int} and abs(value) <= 10**100 and math.isfinite(value)


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


def version_fields(design, *, export=False):
    snapshot = design.get("form_schema")
    if not isinstance(snapshot, dict):
        return
    hidden_by_rule = {rule.get("field") for rule in snapshot.get("rules") or [] if rule.get("type") == "visible"}
    permissions = [node.get("field_perm") or {} for node in design.get("nodes") or []]

    def visible(field):
        key = field.get("key")
        return bool(key) and not (
            field.get("state") == "hidden"
            or field.get("visibleWhen")
            or key in hidden_by_rule
            or any(perm.get(key, perm.get("*")) == "hidden" for perm in permissions)
        )

    def walk(fields):
        for field in fields:
            if not visible(field):
                continue
            if export and field.get("type") in TABLE_FIELDS:
                yield {**field, "export_columns": [column for column in configured_table_columns(field) if visible(column)]}
            else:
                yield field
                yield from walk(field.get("children") or [])

    yield from walk(snapshot.get("fields") or [])


def workflow_versions(request, scoped_tickets, workflow_id):
    return (
        WorkflowVersion.objects.filter(
            workflow__domain=domain_of(request),
            workflow_id=workflow_id,
            id__in=scoped_tickets.filter(workflow_id=workflow_id).order_by().values("workflow_version_id"),
        )
        .order_by("-version_no")
        .values("id", "design")
        .iterator()
    )


def field_catalog(request, scoped_tickets, workflow_id):
    """同一字段只匹配类型一致且各节点均可见的版本。"""
    catalog = {}
    for version in workflow_versions(request, scoped_tickets, workflow_id):
        for field in version_fields(version["design"] or {}):
            key, kind = field["key"], field.get("type")
            if key in {"title", "priority"} or kind not in OPERATORS:
                continue
            if key not in catalog:
                options = (
                    [
                        {"label": str(option.get("label", option["value"])), "value": option["value"]}
                        for option in resolve_options(field)[:500]
                        if "value" in option and (isinstance(option["value"], str) or is_number(option["value"]))
                    ]
                    if kind in CHOICE_TYPES
                    else []
                )
                catalog[key] = {"key": key, "label": field.get("label") or key, "type": kind, "options": options, "version_ids": set()}
            if catalog[key]["type"] == kind:
                catalog[key]["version_ids"].add(version["id"])
    return catalog


def form_field(catalog, key):
    field = catalog.get(key)
    if not field:
        raise InvalidFormFilter("所选字段不可用，请重新选择表单字段")
    return field


def _validate_clause(catalog, clause):
    field = form_field(catalog, clause["key"])
    kind, operator, value = field["type"], clause["operator"], clause["value"]
    if operator not in OPERATORS[kind]:
        raise InvalidFormFilter("所选字段不支持该匹配方式")
    if kind == "number":
        if not is_number(value):
            raise InvalidFormFilter("数值字段需要填写数字")
    elif not isinstance(value, str) and kind not in CHOICE_TYPES:
        raise InvalidFormFilter("该字段需要填写文本")
    elif kind == "date":
        try:
            valid = parse_date(value) is not None
        except ValueError:
            valid = False
        if not valid:
            raise InvalidFormFilter("请选择有效日期")
    return field


def apply_form_filters(queryset, catalog, clauses):
    for index, clause in enumerate(clauses):
        field = _validate_clause(catalog, clause)
        key, operator, value = clause["key"], clause["operator"], clause["value"]
        alias = f"_form_filter_{index}"
        lookup = {"eq": "exact", "contains": "icontains", "gte": "gte", "lte": "lte"}[operator]
        transform = KeyTextTransform if operator == "contains" else KeyTransform
        expression = transform(key, F("form_data"))
        if field["type"] in CHOICE_TYPES and not field["options"] and isinstance(value, str):
            expression = Cast(KeyTextTransform(key, F("form_data")), output_field=CharField())
        queryset = queryset.alias(**{alias: expression}).filter(workflow_version_id__in=field["version_ids"], **{f"{alias}__{lookup}": value})
        if field["type"] == "number":
            # JSON 比较会对类型排序。排除旧数据中的空值与非数值，避免被范围条件误匹配。
            if connection.vendor == "postgresql":
                number_type = Func(expression, function="jsonb_typeof", output_field=CharField())
                types = ["number"]
            elif connection.vendor in {"sqlite", "mysql"}:
                number_type = Func(F("form_data"), Value(compile_json_path([key])), function="JSON_TYPE", output_field=CharField())
                types = ["integer", "real"] if connection.vendor == "sqlite" else ["INTEGER", "DOUBLE", "DECIMAL"]
            else:
                continue
            queryset = queryset.alias(**{f"{alias}_type": number_type}).filter(**{f"{alias}_type__in": types})
    return queryset
