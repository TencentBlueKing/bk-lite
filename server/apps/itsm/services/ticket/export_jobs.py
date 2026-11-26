"""后台工单导出的生成、状态及文件权限。"""

import base64
from datetime import timedelta
from io import BytesIO
from types import SimpleNamespace

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from kombu.exceptions import OperationalError
from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE

from apps.core.logger import itsm_logger as logger
from apps.itsm.models import TicketExportTask, UserPreference
from apps.itsm.services.integrations import live_identity
from apps.itsm.services.ticket import export_fields
from apps.itsm.services.ticket.form_filters import InvalidFormFilter, form_field
from apps.itsm.services.ticket.listing import filtered_tickets, validate_filters
from apps.itsm.views.access import domain_of, has_permission, ticket_scope

MAX_ASYNC_ROWS = 5000
MAX_FORM_COLUMNS = 30
MAX_FILE_BYTES = 8 * 1024**2
MAX_TEXT_CHARS = 6_000_000
FILE_TTL = timedelta(days=7)


def prepare_export(request, payload, row_limit):
    if not isinstance(payload, dict):
        raise InvalidFormFilter("无效的导出请求")
    filters = validate_filters(payload.get("filters", {}))
    keys = payload.get("form_columns", [])
    if not isinstance(keys, list) or len(keys) > MAX_FORM_COLUMNS or any(not isinstance(key, str) for key in keys):
        raise InvalidFormFilter(f"最多导出 {MAX_FORM_COLUMNS} 个表单字段")
    selection = {"filters": filters, "form_columns": list(dict.fromkeys(keys))}
    columns = export_fields.selected_columns(payload.get("columns", export_fields.LEGACY_COLUMNS))
    if "columns" in payload:
        selection["columns"] = columns
    workflow_id = filters.get("workflow_id")
    if payload.get("form_workflow_id"):
        chosen_workflow = validate_filters({"workflow_id": payload["form_workflow_id"]}).get("workflow_id")
        if workflow_id and chosen_workflow != workflow_id:
            raise InvalidFormFilter("请选择当前筛选流程的表单字段")
        workflow_id = chosen_workflow
        selection["form_workflow_id"] = workflow_id
    scoped = ticket_scope(request)
    queryset = filtered_tickets(request, scoped, filters)
    catalog = export_fields.form_export_catalog(request, scoped, workflow_id) if workflow_id and keys else {}
    fields = [form_field(catalog, key) for key in selection["form_columns"]]
    if "columns" in payload:
        export_fields.set_option_labels(fields)
    if "ids" in payload:
        ids = payload["ids"]
        if not isinstance(ids, list) or not 1 <= len(ids) <= row_limit or any(type(pk) is not int or not 0 < pk < 2**63 for pk in ids):
            raise InvalidFormFilter("请选择有效的工单后再导出")
        selection["ids"] = list(dict.fromkeys(ids))
        queryset = queryset.filter(pk__in=selection["ids"])
    return selection, export_fields.project_export(queryset, columns, fields), fields


def _write_row(sheet, values):
    cells = []
    for value in values:
        if isinstance(value, str):
            cell = WriteOnlyCell(sheet, value=ILLEGAL_CHARACTERS_RE.sub("", value[:32767]))
            cell.data_type = "s"  # openpyxl 会将以等号开头的文本识别为公式。
            value = cell
        cells.append(value)
    sheet.append(cells)


def workbook(queryset, fields, row_limit, columns=None):
    system_columns = [export_fields.COLUMNS[key] for key in columns or export_fields.LEGACY_COLUMNS]
    book = Workbook(write_only=True)
    sheet = book.create_sheet("工单")
    buffer = BytesIO()
    rows = {}
    field_versions = {field["key"]: set() for field in fields}
    total_text = 0
    _write_row(sheet, [*(column.label for column in system_columns), *(field["label"] for field in fields)])
    try:
        for ticket in queryset[: row_limit + 1].iterator(chunk_size=50):
            if len(rows) >= row_limit:
                raise InvalidFormFilter(f"一次最多导出 {row_limit} 张工单，请缩小筛选范围")
            values = [column.read(ticket) for column in system_columns]
            for field in fields:
                value = export_fields.read_form_value(ticket, field)
                if value is not None:
                    field_versions[field["key"]].add(ticket.workflow_version_id)
                values.append(value)
            total_text += sum(min(len(value), 32767) for value in values if isinstance(value, str))
            if total_text > MAX_TEXT_CHARS:
                raise InvalidFormFilter("导出数据超过文件容量，请缩小范围或减少表单字段")
            _write_row(sheet, values)
            rows[str(ticket.pk)] = ticket.workflow_version_id
    finally:
        # write-only 工作表的临时文件由保存过程清理，包括放弃部分结果的情况。
        book.save(buffer)
    if buffer.tell() > MAX_FILE_BYTES:
        raise InvalidFormFilter("导出文件超过 8 MB，请缩小筛选范围")
    manifest = {field["key"]: export_fields.field_manifest(field, field_versions[field["key"]]) for field in fields}
    return base64.b64encode(buffer.getvalue()).decode("ascii"), {"rows": rows, "fields": manifest}


def owned_exports(request):
    return TicketExportTask.objects.filter(is_async=True, username=request.user.username, domain=domain_of(request))


def expire_exports(queryset):
    now = timezone.now()
    for status, timeout in (("pending", timedelta(minutes=30)), ("running", timedelta(minutes=10))):
        queryset.filter(status=status, updated_at__lt=now - timeout).update(status="failed", error="导出等待超时，请重试", updated_at=now, finished_at=now)
    queryset.filter(status="done", finished_at__lte=now - FILE_TTL).exclude(content_base64="").update(content_base64="", result_manifest={})


def purge_expired_files(batch_size=500):
    cutoff = timezone.now() - FILE_TTL
    expired = TicketExportTask.objects.filter(
        Q(finished_at__lte=cutoff) | Q(is_async=False, finished_at__isnull=True, created_at__lte=cutoff),
        status="done",
    ).exclude(content_base64="")
    ids = list(expired.order_by("pk").values_list("pk", flat=True)[:batch_size])
    return expired.filter(pk__in=ids).update(content_base64="", result_manifest={})


def _fail(task_id, message, status):
    now = timezone.now()
    TicketExportTask.objects.filter(pk=task_id, status=status).update(status="failed", error=message, updated_at=now, finished_at=now)


def enqueue(task_id):
    from apps.itsm.tasks import generate_ticket_export

    try:
        generate_ticket_export.apply_async(args=[task_id], retry=False)
    except OperationalError:
        logger.warning("ITSM 工单导出入队失败，任务 %s", task_id)
        _fail(task_id, "暂时无法入队，请稍后重试", "pending")


def submit(request, payload):
    selection, _, _ = prepare_export(request, payload, MAX_ASYNC_ROWS)
    selection["see_all"] = bool(getattr(request.user, "is_superuser", False))
    owner = {"domain": domain_of(request), "username": request.user.username}
    with transaction.atomic():
        lock, _ = UserPreference.objects.get_or_create(**owner)
        UserPreference.objects.select_for_update().get(pk=lock.pk)
        tasks = owned_exports(request)
        expire_exports(tasks)
        if tasks.filter(status__in=["pending", "running"]).count() >= 3:
            raise InvalidFormFilter("最多同时提交 3 个导出任务，请稍后重试")
        task = TicketExportTask.objects.create(
            **owner,
            is_async=True,
            status="pending",
            request_payload=selection,
            created_by=request.user.username,
            updated_by=request.user.username,
        )
        transaction.on_commit(lambda: enqueue(task.pk))
    return task


def generate(task_id):
    tasks = TicketExportTask.objects.filter(pk=task_id, is_async=True)
    if not tasks.filter(status="pending").update(status="running", updated_at=timezone.now()):
        return
    task = tasks.defer("content_base64", "result_manifest").get()
    try:
        identity = live_identity(task, actor=task.username, permission="ticket-Export")
        user = SimpleNamespace(
            username=identity.user,
            domain=identity.domain,
            is_superuser=identity.is_superuser,
            permission=identity.permission,
        )
        request = SimpleNamespace(user=user)
        if not has_permission(request, "ticket-View"):
            raise PermissionError
        user.is_superuser = user.is_superuser and task.request_payload["see_all"]
        selection, queryset, fields = prepare_export(request, task.request_payload, MAX_ASYNC_ROWS)
        encoded, manifest = workbook(queryset, fields, MAX_ASYNC_ROWS, selection.get("columns"))
        count = len(manifest["rows"])
        if not count:
            raise InvalidFormFilter("当前条件没有可导出的工单")
        now = timezone.now()
        tasks.filter(status="running").update(
            status="done",
            filename=f"tickets-{timezone.localtime(now):%Y%m%d%H%M%S}-{task.pk}.xlsx",
            content_base64=encoded,
            ticket_count=count,
            result_manifest=manifest,
            finished_at=now,
            updated_at=now,
        )
    except PermissionError:
        _fail(task_id, "发起人的工单查看或导出权限已变化", "running")
    except InvalidFormFilter as exc:
        _fail(task_id, str(exc), "running")
    except Exception:
        logger.exception("ITSM 工单导出生成失败，任务 %s", task_id)
        _fail(task_id, "生成 Excel 失败，请重试", "running")


def file_is_current(task):
    return task.status == "done" and task.finished_at is not None and task.finished_at > timezone.now() - FILE_TTL


def check_file_permissions(request, task):
    scoped = ticket_scope(request)
    manifest = task.result_manifest
    rows = manifest["rows"]
    ids = list(map(int, rows))
    for start in range(0, len(ids), 500):
        batch = ids[start : start + 500]
        current = scoped.filter(pk__in=batch).values_list("id", "workflow_version_id")
        if {str(pk): version for pk, version in current} != {str(pk): rows[str(pk)] for pk in batch}:
            raise PermissionError
    if manifest["fields"]:
        workflow_id = task.request_payload.get("form_workflow_id") or task.request_payload["filters"]["workflow_id"]
        catalog = export_fields.form_export_catalog(request, scoped, workflow_id)
        for key, previous in manifest["fields"].items():
            if not previous["versions"]:
                continue
            current = catalog.get(key)
            if not current or current["type"] != previous["type"] or set(previous["versions"]) - current["schemas"].keys():
                raise PermissionError
            for version, columns in previous.get("table_columns", {}).items():
                available = current["schemas"][int(version)].get("export_columns", [])
                if set(columns) - {column["key"] for column in available}:
                    raise PermissionError
