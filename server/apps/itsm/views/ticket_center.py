"""当前用户的列表列配置与动态筛选分组。"""
import json

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.web_utils import WebUtils
from apps.itsm.models import TicketSavedView, UserPreference, Workflow
from apps.itsm.services.ticket.form_filters import InvalidFormFilter, field_catalog
from apps.itsm.services.ticket.listing import DEFAULT_COLUMNS, filtered_tickets, validate_columns, validate_filters
from apps.itsm.views.access import api_errors, domain_of, ticket_scope


@csrf_exempt
@api_errors
@HasPermission("ticket-View")
def center_settings(request):
    scope = {"domain": domain_of(request), "username": request.user.username}
    views = TicketSavedView.objects.filter(**scope).order_by("id")
    if request.method == "GET":
        pref = UserPreference.objects.filter(**scope).first()
        return WebUtils.response_success(
            {
                "columns": (pref.ticket_columns or DEFAULT_COLUMNS) if pref else DEFAULT_COLUMNS,
                "default_columns": DEFAULT_COLUMNS,
                "views": list(views.values("id", "name", "filters")),
            }
        )
    payload = json.loads(request.body)
    if request.method == "PUT":
        columns = validate_columns(payload["columns"])
        UserPreference.objects.update_or_create(**scope, defaults={"ticket_columns": columns, "updated_by": request.user.username})
        return WebUtils.response_success({"columns": columns})
    if request.method == "POST":
        name = payload.get("name")
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 40:
            raise ValueError("分组名称须为1至40字")
        try:
            filters = validate_filters(payload.get("filters", {}))
            if filters.get("form_filters"):
                filtered_tickets(request, ticket_scope(request), filters)
        except InvalidFormFilter as exc:
            return WebUtils.response_error(str(exc))
        with transaction.atomic():
            pref, _ = UserPreference.objects.get_or_create(**scope)
            UserPreference.objects.select_for_update().get(pk=pref.pk)
            if views.count() >= 20 or views.filter(name=name.strip()).exists():
                return WebUtils.response_error("分组已存在或已达到20个上限")
            item = TicketSavedView.objects.create(**scope, name=name.strip(), filters=filters, created_by=request.user.username)
        return WebUtils.response_success({"id": item.id, "name": item.name, "filters": filters})
    if request.method == "DELETE":
        get_object_or_404(views, pk=payload["id"]).delete()
        return WebUtils.response_success({})
    return WebUtils.response_error("不支持的请求方法", status_code=405)


@api_errors
@HasPermission("ticket-View")
def filter_tags(request):
    from apps.itsm.models import TicketTag

    if request.method != "GET":
        return WebUtils.response_error("不支持的请求方法", status_code=405)
    keyword = (request.GET.get("q") or "").strip()[:64]
    tags = TicketTag.objects.filter(domain=domain_of(request), tickets__in=ticket_scope(request)).distinct()
    if keyword:
        tags = tags.filter(name__icontains=keyword)
    return WebUtils.response_success({"items": list(tags.order_by("name").values("name", "color")[:50])})


@require_GET
@api_errors
@HasPermission("ticket-View")
def filter_fields(request):
    scoped_tickets = ticket_scope(request)
    workflows = Workflow.objects.filter(domain=domain_of(request), pk__in=scoped_tickets.order_by().values("workflow_id"))
    params = validate_filters({key: request.GET[key] for key in ("workflow_id", "q") if key in request.GET})
    if workflow_id := params.get("workflow_id"):
        workflow = get_object_or_404(workflows, pk=workflow_id)
        catalog = field_catalog(request, scoped_tickets, workflow_id)
        return WebUtils.response_success(
            {
                "workflow": {"id": workflow.id, "name": workflow.name},
                "fields": [{key: value for key, value in field.items() if key != "version_ids"} for field in catalog.values()],
            }
        )
    if keyword := params.get("q"):
        workflows = workflows.filter(name__icontains=keyword)
    return WebUtils.response_success({"workflows": list(workflows.order_by("name", "id").values("id", "name")[:50])})
