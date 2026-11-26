"""工单导出及发起人自己的后台任务。"""

import base64
from io import BytesIO

from django.core.paginator import Paginator
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.web_utils import WebUtils
from apps.itsm.models import TicketExportTask, Workflow
from apps.itsm.services.ticket import export_fields as field_config
from apps.itsm.services.ticket import export_jobs
from apps.itsm.services.ticket.form_filters import InvalidFormFilter
from apps.itsm.services.ticket.listing import validate_filters
from apps.itsm.views.access import api_errors, domain_of, ticket_scope
from apps.itsm.views.tickets import _body

MAX_ROWS = 500


@csrf_exempt
@require_POST
@api_errors
@HasPermission("ticket-View")
@HasPermission("ticket-Export")
def export_tickets(request):
    try:
        selection, queryset, fields = export_jobs.prepare_export(request, _body(request), MAX_ROWS)
        encoded, manifest = export_jobs.workbook(queryset, fields, MAX_ROWS, selection.get("columns"))
    except InvalidFormFilter as exc:
        return WebUtils.response_error(str(exc))
    username = request.user.username
    task = TicketExportTask.objects.create(
        domain=domain_of(request),
        username=username,
        filename=f"tickets-{timezone.now().strftime('%Y%m%d%H%M%S')}.xlsx",
        content_base64=encoded,
        ticket_count=len(manifest["rows"]),
        created_by=username,
        updated_by=username,
    )
    return WebUtils.response_success({"id": task.id, "filename": task.filename, "count": task.ticket_count, "content_base64": encoded})


def _item(task):
    return {
        "id": task.pk,
        "status": task.status,
        "count": task.ticket_count,
        "filename": task.filename,
        "error": task.error,
        "created_at": task.created_at.isoformat(),
        "finished_at": task.finished_at.isoformat() if task.finished_at else None,
        "downloadable": export_jobs.file_is_current(task),
    }


def _submit(request, payload):
    try:
        task = export_jobs.submit(request, payload)
    except InvalidFormFilter as exc:
        return WebUtils.response_error(str(exc))
    return WebUtils.response_success(_item(task))


@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_errors
@HasPermission("ticket-View")
@HasPermission("ticket-Export")
def export_tasks(request):
    if request.method == "POST":
        return _submit(request, _body(request))
    queryset = export_jobs.owned_exports(request)
    export_jobs.expire_exports(queryset)
    size = max(1, min(100, int(request.GET.get("page_size") or 20)))
    page = Paginator(queryset.defer("content_base64", "request_payload", "result_manifest").order_by("-id"), size).get_page(
        request.GET.get("page") or 1
    )
    return WebUtils.response_success({"count": page.paginator.count, "items": [_item(task) for task in page]})


@csrf_exempt
@require_POST
@api_errors
@HasPermission("ticket-View")
@HasPermission("ticket-Export")
def retry_export(request, task_id):
    task = get_object_or_404(export_jobs.owned_exports(request).defer("content_base64", "result_manifest"), pk=task_id)
    if task.status != "failed":
        return WebUtils.response_error("只有失败的导出任务可以重试", status_code=409)
    return _submit(request, task.request_payload)


@require_GET
@api_errors
@HasPermission("ticket-View")
@HasPermission("ticket-Export")
def download_export(request, task_id):
    task = get_object_or_404(export_jobs.owned_exports(request).defer("content_base64"), pk=task_id)
    if not export_jobs.file_is_current(task):
        return WebUtils.response_error("导出文件尚未生成或已过期", status_code=409)
    export_jobs.check_file_permissions(request, task)
    content = task.content_base64
    if not content:
        return WebUtils.response_error("导出文件已过期", status_code=409)
    response = FileResponse(
        BytesIO(base64.b64decode(content)),
        as_attachment=True,
        filename=task.filename,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Cache-Control"] = "private, no-store"
    return response


@require_GET
@api_errors
@HasPermission("ticket-View")
@HasPermission("ticket-Export")
def export_fields(request):
    scoped = ticket_scope(request)
    workflows = Workflow.objects.filter(domain=domain_of(request), pk__in=scoped.order_by().values("workflow_id"))
    params = validate_filters({key: request.GET[key] for key in ("workflow_id", "q") if key in request.GET})
    if workflow_id := params.get("workflow_id"):
        workflow = get_object_or_404(workflows, pk=workflow_id)
        return WebUtils.response_success(
            {
                "groups": field_config.system_groups(),
                "default_columns": field_config.DEFAULT_COLUMNS,
                "workflow": {"id": workflow.id, "name": workflow.name},
                "fields": [
                    {key: item[key] for key in ("key", "label", "type")}
                    for item in field_config.form_export_catalog(request, scoped, workflow_id).values()
                ],
            }
        )
    if keyword := params.get("q"):
        workflows = workflows.filter(name__icontains=keyword)
    return WebUtils.response_success(
        {
            "groups": field_config.system_groups(),
            "default_columns": field_config.DEFAULT_COLUMNS,
            "workflows": list(workflows.order_by("name", "id").values("id", "name")[:50]),
        }
    )
