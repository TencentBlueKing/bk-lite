import json

from django.conf import settings
from django.core.paginator import Paginator
from django.views.decorators.csrf import csrf_exempt

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.web_utils import WebUtils
from apps.itsm.flowable.client import FlowableClient
from apps.itsm.models import Ticket, TicketLog, TicketTask, WorkflowVersion
from apps.itsm.services.ticket.service import TicketService


def _body(request):
    if not request.body:
        return {}
    return json.loads(request.body.decode("utf-8"))


def _service():
    if not settings.FLOWABLE_PASSWORD:
        return TicketService(None)
    return TicketService(FlowableClient(settings.FLOWABLE_URL, settings.FLOWABLE_USER, settings.FLOWABLE_PASSWORD))


def _user(request):
    return getattr(getattr(request, "user", None), "username", "") or "admin"


@csrf_exempt
@HasPermission("ticket-View")
def tickets(request):
    if request.method == "GET":
        page = Paginator(Ticket.objects.select_related("status").order_by("-id"), int(request.GET.get("page_size") or 20))
        current = page.get_page(int(request.GET.get("page") or 1))
        items = [
            {"id": item.id, "sn": item.sn, "title": item.title, "status": item.status.key if item.status_id else "", "creator": item.creator}
            for item in current
        ]
        return WebUtils.response_success({"count": current.paginator.count, "items": items})
    payload = _body(request)
    version = WorkflowVersion.objects.select_related("workflow").get(id=payload["workflow_version_id"])
    ticket = _service().create(version, payload.get("form_data") or {}, _user(request), bool(payload.get("is_test")))
    return WebUtils.response_success({"id": ticket.id, "sn": ticket.sn, "status": ticket.status.key if ticket.status_id else ""})


@csrf_exempt
@HasPermission("ticket-Operate")
def operate_ticket(request, ticket_id):
    payload = _body(request)
    ticket = Ticket.objects.get(id=ticket_id)
    task = TicketTask.objects.get(id=payload["task_id"], ticket=ticket)
    updated = _service().operate(ticket, task, payload["action"], payload, _user(request))
    return WebUtils.response_success({"id": updated.id, "status": updated.status.key if updated.status_id else ""})


@HasPermission("ticket-View")
def ticket_logs(request, ticket_id):
    logs = TicketLog.objects.filter(ticket_id=ticket_id).order_by("id")
    return WebUtils.response_success({"items": [{"action": item.action, "operator": item.operator, "message": item.message} for item in logs]})
