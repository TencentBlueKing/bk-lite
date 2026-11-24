"""工单导出列、查询投影与表单字段呈现。"""

from dataclasses import dataclass
from operator import attrgetter
from typing import Callable

from django.db.models import DateTimeField, OuterRef, Prefetch, Subquery
from django.utils import timezone
from django.utils.html import strip_tags

from apps.itsm.models import SLAPolicy, TicketLog, TicketSLARecord, TicketTag, TicketTask
from apps.itsm.services.form.options import resolve_options
from apps.itsm.services.ticket.form_filters import TABLE_FIELDS, InvalidFormFilter, is_number, version_fields, workflow_versions


def excel_time(value):
    if value is None or timezone.is_naive(value):
        return value
    return timezone.localtime(value).replace(tzinfo=None)


def joined(values):
    return "、".join(dict.fromkeys(str(value) for value in values if value not in ("", None))) or None


def tasks(ticket, active):
    return (task for task in ticket.export_tasks if (task.status in {"pending", "claimed"}) == active)


def sla_value(ticket, target, value):
    record = next((item for item in ticket.export_sla if item.target == target), None)
    if record is None:
        return None
    if value == "due":
        return excel_time(record.due_at)
    if record.breached:
        return "超时"
    if record.finished_at:
        return "达标"
    return "已挂起" if record.paused_at else "计时中"


@dataclass(frozen=True)
class ExportColumn:
    label: str
    category: str
    read: Callable
    source: str = ""


GROUPS = {"basic": "工单信息", "flow": "流程与处理", "time": "时间", "sla": "SLA 与评价"}
COLUMNS = {
    "sn": ExportColumn("单号", "basic", attrgetter("sn"), "sn"),
    "title": ExportColumn("标题", "basic", attrgetter("title"), "title"),
    "creator": ExportColumn("提单人", "basic", attrgetter("creator"), "creator"),
    "status": ExportColumn("状态", "basic", lambda t: t.status.name if t.status_id else None, "status__name"),
    "service": ExportColumn("服务", "basic", lambda t: t.service.name if t.service_id else None, "service__name"),
    "service_catalog": ExportColumn(
        "服务目录", "basic", lambda t: t.service.catalog.name if t.service_id and t.service.catalog_id else None, "service__catalog__name"
    ),
    "tags": ExportColumn("标签", "basic", lambda t: joined(tag.name for tag in t.export_tags)),
    "id": ExportColumn("工单 ID", "basic", lambda t: str(t.pk)),
    "workflow": ExportColumn("流程名称", "flow", lambda t: t.workflow.name, "workflow__name"),
    "workflow_type": ExportColumn(
        "流程类型", "flow", lambda t: t.workflow.workflow_type.name if t.workflow.workflow_type_id else None, "workflow__workflow_type__name"
    ),
    "workflow_version": ExportColumn(
        "流程版本", "flow", lambda t: t.workflow_version.version_no if t.workflow_version_id else None, "workflow_version__version_no"
    ),
    "node": ExportColumn("当前节点", "flow", lambda t: joined(task.node_name or task.node_id for task in tasks(t, True))),
    "assignees": ExportColumn("当前处理人", "flow", lambda t: joined(task.assignee for task in tasks(t, True))),
    "processed_by": ExportColumn("已处理人", "flow", lambda t: joined(task.assignee for task in tasks(t, False))),
    "created_at": ExportColumn("创建时间", "time", lambda t: excel_time(t.created_at), "created_at"),
    "submitted_at": ExportColumn("首次提交时间", "time", lambda t: excel_time(t.export_submitted_at)),
    "updated_at": ExportColumn("更新时间", "time", lambda t: excel_time(t.updated_at), "updated_at"),
    "finished_at": ExportColumn("结束时间", "time", lambda t: excel_time(t.finished_at), "finished_at"),
    "response_due": ExportColumn("响应截止时间", "sla", lambda t: sla_value(t, SLAPolicy.Target.RESPONSE, "due")),
    "response_sla": ExportColumn("响应 SLA", "sla", lambda t: sla_value(t, SLAPolicy.Target.RESPONSE, "status")),
    "resolve_due": ExportColumn("解决截止时间", "sla", lambda t: sla_value(t, SLAPolicy.Target.RESOLVE, "due")),
    "resolve_sla": ExportColumn("解决 SLA", "sla", lambda t: sla_value(t, SLAPolicy.Target.RESOLVE, "status")),
    "survey_score": ExportColumn("满意度", "sla", lambda t: t.survey.score if hasattr(t, "survey") else None, "survey__score"),
}
LEGACY_COLUMNS = ["sn", "title", "creator", "status"]
DEFAULT_COLUMNS = [*LEGACY_COLUMNS, "service", "workflow", "node", "assignees", "created_at", "updated_at", "finished_at"]
OPTION_TYPES = {"radio", "select", "checkbox", "multiselect", "cascade", "multiCascade"}
LIST_FIELDS = OPTION_TYPES | {"dateRange", "user", "multiUser", "group", "userGroup", "multiUserGroup", "organization"}
SCALAR_FIELDS = {"input", "textarea", "richtext", "date", "datetime", "time", "number", "calculate", "signature"}
FORM_FIELDS = SCALAR_FIELDS | LIST_FIELDS | TABLE_FIELDS | {"attachment"}


def system_groups():
    return [
        {
            "key": group,
            "label": label,
            "columns": [{"key": key, "label": column.label} for key, column in COLUMNS.items() if column.category == group],
        }
        for group, label in GROUPS.items()
    ]


def selected_columns(raw):
    if not isinstance(raw, list) or len(raw) > len(COLUMNS) or any(not isinstance(key, str) or key not in COLUMNS for key in raw):
        raise InvalidFormFilter("所选工单列不可用，请重新选择")
    return list(dict.fromkeys(["sn", *raw]))


def project_export(queryset, columns, fields):
    sources = [COLUMNS[key].source for key in columns if COLUMNS[key].source]
    related = sorted({path.rsplit("__", 1)[0] for path in sources if "__" in path})
    if related:
        queryset = queryset.select_related(*related)
    queryset = queryset.only("workflow_version_id", *sources, *(["form_data"] if fields else []))
    if {"node", "assignees", "processed_by"}.intersection(columns):
        statuses = ["pending", "claimed"] if {"node", "assignees"}.intersection(columns) else []
        if "processed_by" in columns:
            statuses.append("done")
        queryset = queryset.prefetch_related(
            Prefetch(
                "tasks",
                queryset=TicketTask.objects.filter(status__in=statuses)
                .only("ticket_id", "node_id", "node_name", "assignee", "status")
                .order_by("id"),
                to_attr="export_tasks",
            )
        )
    if "tags" in columns:
        queryset = queryset.prefetch_related(Prefetch("tags", queryset=TicketTag.objects.only("name").order_by("name", "id"), to_attr="export_tags"))
    if {"response_due", "response_sla", "resolve_due", "resolve_sla"}.intersection(columns):
        records = TicketSLARecord.objects.only("ticket_id", "target", "due_at", "breached", "paused_at", "finished_at")
        queryset = queryset.prefetch_related(Prefetch("sla_records", queryset=records, to_attr="export_sla"))
    if "submitted_at" in columns:
        logs = TicketLog.objects.filter(ticket_id=OuterRef("pk"), action="submit").order_by("created_at", "id")
        queryset = queryset.annotate(export_submitted_at=Subquery(logs.values("created_at")[:1], output_field=DateTimeField()))
    return queryset


def option_labels(options):
    labels = {}
    for item in options:
        value = item.get("value")
        if isinstance(value, str) or is_number(value):
            labels[value] = str(item.get("label", value))
        labels.update(option_labels(item.get("children") or []))
    return labels


def form_export_catalog(request, scoped, workflow_id):
    catalog = {}
    for version in workflow_versions(request, scoped, workflow_id):
        for field in version_fields(version["design"] or {}, export=True):
            key, kind = field["key"], field.get("type")
            if key == "title" or kind not in FORM_FIELDS or (kind in TABLE_FIELDS and not field["export_columns"]):
                continue
            item = catalog.setdefault(key, {"key": key, "label": field.get("label") or key, "type": kind, "schemas": {}})
            if item["type"] == kind:
                item["schemas"][version["id"]] = field
    return catalog


def _simple_label(value, choices):
    if isinstance(value, str) or is_number(value):
        return choices.get(value, value)
    return None


def _table_value(value, columns):
    if not isinstance(value, list):
        return None
    rows = []
    for row in value[:100]:
        if not isinstance(row, dict):
            continue
        cells = []
        for column in columns:
            raw = _simple_label(row.get(column["key"]), {})
            if raw not in (None, ""):
                cells.append(f"{column.get('label') or column['key']}：{raw}")
        if cells:
            rows.append("；".join(cells))
    return "\n".join(rows) or None


def read_form_value(ticket, field):
    schema = field["schemas"].get(ticket.workflow_version_id)
    if schema is None:
        return None
    return format_form_value(
        ticket.form_data.get(field["key"]),
        field["type"],
        columns=schema.get("export_columns"),
        labels=schema.get("export_labels"),
    )


def format_form_value(value, kind, *, columns=None, labels=None):
    if kind in TABLE_FIELDS:
        return _table_value(value, columns or ())
    if kind == "attachment":
        if not isinstance(value, list):
            return None
        return joined(path.split("/")[-1] for path in value if isinstance(path, str) and "://" not in path)
    if kind == "richtext" and isinstance(value, str):
        return strip_tags(value) or None
    labels = labels or {}
    if kind in LIST_FIELDS and isinstance(value, list):
        safe_values = (part for entry in value for part in (entry if isinstance(entry, list) else [entry]))
        return joined(_simple_label(part, labels) for part in safe_values)
    return _simple_label(value, labels)


def field_manifest(field, versions):
    schemas = field["schemas"]
    return {
        "type": field["type"],
        "versions": sorted(versions),
        "table_columns": {
            str(version): [column["key"] for column in schemas[version]["export_columns"]]
            for version in versions
            if "export_columns" in schemas[version]
        },
    }


def set_option_labels(fields):
    for field in fields:
        if field["type"] in OPTION_TYPES:
            for schema in field["schemas"].values():
                schema["export_labels"] = option_labels(resolve_options(schema))
