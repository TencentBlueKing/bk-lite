from dataclasses import dataclass
from operator import attrgetter

from django.utils.html import format_html, format_html_join
from django.utils.timezone import localtime
from jinja2 import TemplateError, TemplateSyntaxError, nodes
from jinja2.sandbox import SandboxedEnvironment

from apps.itsm.models import Ticket, TicketTask
from apps.itsm.services.form.fetch import walk
from apps.itsm.services.form.options import resolve_options
from apps.itsm.services.form.rules import match_when
from apps.itsm.services.ticket.export_fields import FORM_FIELDS, OPTION_TYPES, format_form_value, joined, option_labels
from apps.itsm.services.ticket.form_filters import TABLE_FIELDS, configured_table_columns


def _time(value):
    return localtime(value).strftime("%Y-%m-%d %H:%M:%S") if value else ""


SYSTEM_FIELDS = {
    "title": ("工单标题", "示例工单", attrgetter("ticket.title")),
    "sn": ("工单编号", "REQ202611200001", attrgetter("ticket.sn")),
    "creator": ("提单人", "demo_user", attrgetter("ticket.creator")),
    "status": ("工单状态", "处理中", lambda ctx: ctx.ticket.status.name if ctx.ticket.status_id else ""),
    "service": ("服务名称", "运维服务", lambda ctx: ctx.ticket.service.name if ctx.ticket.service_id else ""),
    "workflow": ("流程名称", "服务申请流程", attrgetter("ticket.workflow.name")),
    "node": ("当前节点", "部门审批", lambda ctx: joined(task.node_name or task.node_id for task in ctx.active_tasks)),
    "assignees": ("当前处理人", "demo_handler", lambda ctx: joined(task.assignee for task in ctx.active_tasks)),
    "created_at": ("创建时间", "2026-11-20 09:00:00", lambda ctx: _time(ctx.ticket.created_at)),
    "updated_at": ("更新时间", "2026-11-20 09:10:00", lambda ctx: _time(ctx.ticket.updated_at)),
    "finished_at": ("完成时间", "2026-11-20 09:30:00", lambda ctx: _time(ctx.ticket.finished_at)),
}
_SYSTEM_EXAMPLES = {key: sample for key, (_, sample, _) in SYSTEM_FIELDS.items()}
_FORM_EXAMPLES = (
    ("申请金额", 1200),
    ("申请说明", "更换会议室损坏的设备"),
    ("备注", ""),
)
_LAYOUT_FIELDS = {"section", "tab"}

_ENVIRONMENT = SandboxedEnvironment(autoescape=True)
_ALLOWED_NODES = (
    nodes.Output,
    nodes.TemplateData,
    nodes.Name,
    nodes.Const,
    nodes.If,
    nodes.Not,
    nodes.And,
    nodes.Or,
    nodes.Compare,
    nodes.Operand,
    nodes.CondExpr,
    nodes.Filter,
    nodes.Getitem,
)
_ALLOWED_FILTERS = {"default", "lower", "upper", "trim"}


class PrintTemplateError(ValueError):
    pass


@dataclass(frozen=True)
class PrintTicketContext:
    ticket: Ticket
    active_tasks: list[TicketTask]
    fields: list[dict]
    values: dict
    schema: dict
    permissions: dict[str, str]


class _ExampleFormValues(dict):
    def __missing__(self, key):
        return "示例值"


def _field_table(rows):
    visible_rows = ((label, "—" if value in (None, "") else value) for label, value in rows)
    content = format_html_join("", '<tr><th scope="row">{}</th><td>{}</td></tr>', visible_rows)
    return format_html('<table class="itsm-print-fields"><tbody>{}</tbody></table>', content) if content else ""


def _render_document(values, form_rows):
    system_rows = ((label, values[key]) for key, (label, _, _) in SYSTEM_FIELDS.items() if key != "title")
    document = format_html("<h1>{}</h1>{}", values["title"], _field_table(system_rows))
    form_table = _field_table(form_rows)
    return format_html("{}<h2>表单字段</h2>{}", document, form_table) if form_table else document


def render_print_example():
    return _render_document(_SYSTEM_EXAMPLES, _FORM_EXAMPLES)


def render_print_body(body, values):
    if not isinstance(body, str) or not body.strip() or len(body) > 32000:
        raise PrintTemplateError("模板内容需为 1 至 32000 个字符")
    try:
        parsed = _ENVIRONMENT.parse(body)
        form_names = set()
        for node in parsed.find_all(nodes.Getitem):
            if not (
                isinstance(node.node, nodes.Name)
                and node.node.name == "form"
                and isinstance(node.arg, nodes.Const)
                and isinstance(node.arg.value, str)
            ):
                raise PrintTemplateError(f"第 {node.lineno} 行请用表单字段的固定标识取值")
            form_names.add(id(node.node))
        for node in parsed.find_all(nodes.Node):
            if not isinstance(node, _ALLOWED_NODES):
                raise PrintTemplateError(f"第 {node.lineno} 行含有不支持的模板表达式")
            if isinstance(node, nodes.Name) and (node.name not in values or (node.name == "form" and id(node) not in form_names)):
                raise PrintTemplateError(f"第 {node.lineno} 行的变量 {node.name} 不可用")
            if isinstance(node, nodes.Filter) and node.name not in _ALLOWED_FILTERS:
                raise PrintTemplateError(f"第 {node.lineno} 行的过滤器 {node.name} 不可用")
        return _ENVIRONMENT.from_string(parsed).render(values)
    except TemplateSyntaxError as exc:
        raise PrintTemplateError(f"第 {exc.lineno} 行的模板语法有误") from exc
    except (TemplateError, RecursionError, TypeError) as exc:
        raise PrintTemplateError("打印模板含有不支持的表达式或参数") from exc


def _field_key(field):
    key = field.get("key")
    return key if isinstance(key, str) and key and not key.startswith("_") else ""


def _field_label(field):
    return field.get("label") or field["key"]


def _print_fields(fields, visible):
    for field in fields:
        if not _field_key(field) or not visible(field):
            continue
        kind = field.get("type")
        if kind in _LAYOUT_FIELDS:
            yield from _print_fields(field.get("children") or [], visible)
        elif kind in FORM_FIELDS:
            yield field


def _condition_text(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return ",".join(_condition_text(item) for item in value)
    if isinstance(value, dict):
        return "[object Object]"
    return str(value) if value is not None else ""


def _visible_in_form(condition, values):
    for item in (condition or {}).get("items") or []:
        actual = values.get(item.get("field"))
        operator = item.get("op")
        if operator in {"=", "!="}:
            equal = _condition_text(actual) == _condition_text(item.get("value"))
            if equal != (operator == "="):
                return False
        if operator in {"is_empty", "not_empty"}:
            empty = actual is None or actual == ""
            if empty != (operator == "is_empty"):
                return False
    return True


def _display_value(field, value, original_fields, visible):
    if value is None:
        return ""
    kind = field["type"]
    if kind == "signature":
        return "已签名" if value else ""
    columns = None
    if kind in TABLE_FIELDS:
        columns = [column for column in configured_table_columns(original_fields[field["key"]]) if _field_key(column) and visible(column)]
    labels = option_labels(resolve_options(field)) if kind in OPTION_TYPES else None
    return format_form_value(value, kind, columns=columns, labels=labels)


def _stored_form_rows(context):
    rules = {rule["field"]: rule.get("when") for rule in context.schema.get("rules") or [] if rule.get("type") == "visible"}
    original_fields = {field["key"]: field for field in walk(context.schema.get("fields") or []) if _field_key(field)}
    stored = context.ticket.form_data or {}

    def visible(field):
        key = field["key"]
        return (
            field.get("state") != "hidden"
            and context.permissions.get(key, context.permissions.get("*")) != "hidden"
            and match_when(field.get("visibleWhen"), stored)
            and _visible_in_form(field.get("visibleWhen"), context.values)
            and match_when(rules.get(key), stored)
        )

    rows = {}
    for field in _print_fields(context.fields, visible):
        key = field["key"]
        if key != "title":
            rows[key] = (_field_label(field), _display_value(field, context.values.get(key), original_fields, visible))
    return rows.values()


def render_ticket_print(context):
    values = {key: read(context) for key, (_, _, read) in SYSTEM_FIELDS.items()}
    return _render_document(values, _stored_form_rows(context))


def normalize_print_template(values, *, creating=False):
    if creating or "name" in values:
        name = values.get("name")
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > 128:
            raise PrintTemplateError("模板名称需为 1 至 128 个字符")
        values["name"] = name.strip()
    if creating or "body" in values:
        render_print_body(values.get("body"), {**_SYSTEM_EXAMPLES, "form": _ExampleFormValues(), "form_fields": _field_table(_FORM_EXAMPLES)})
    return values
