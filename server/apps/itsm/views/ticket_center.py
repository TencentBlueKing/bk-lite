"""当前用户的列表列配置与动态筛选分组。"""
import json

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.web_utils import WebUtils
from apps.itsm.models import TicketSavedView, UserPreference
from apps.itsm.services.ticket.listing import DEFAULT_COLUMNS, validate_columns, validate_filters
from apps.itsm.views.access import api_errors, domain_of


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
        filters = validate_filters(payload.get("filters", {}))
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
    from apps.itsm.views.access import ticket_scope

    if request.method != "GET":
        return WebUtils.response_error("不支持的请求方法", status_code=405)
    keyword = (request.GET.get("q") or "").strip()[:64]
    tags = TicketTag.objects.filter(domain=domain_of(request), tickets__in=ticket_scope(request)).distinct()
    if keyword:
        tags = tags.filter(name__icontains=keyword)
    return WebUtils.response_success({"items": list(tags.order_by("name").values("name", "color")[:50])})
