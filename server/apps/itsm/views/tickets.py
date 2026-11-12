import json

from django.conf import settings
from django.contrib.postgres.search import SearchQuery, SearchVector
from django.core.paginator import Paginator
from django.db import connection
from django.db.models import Exists, OuterRef, Q
from django.views.decorators.csrf import csrf_exempt

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.web_utils import WebUtils
from apps.itsm.flowable.client import FlowableClient
from apps.itsm.models import Ticket, TicketLog, TicketSurvey, TicketTask, WorkflowVersion
from apps.itsm.models.extend import VipUser
from apps.itsm.serializers.ticket import TicketListSerializer
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
        queryset = Ticket.objects.visible_to(_user(request)).select_related("status").prefetch_related("tasks", "sla_records")
        queryset = queryset.annotate(_vip=Exists(VipUser.objects.filter(username=OuterRef("creator"), is_enabled=True))).order_by("-_vip", "-id")
        status_key = (request.GET.get("status") or "").strip()
        if status_key:
            queryset = queryset.filter(status__key=status_key)
        creator = (request.GET.get("creator") or "").strip()
        if creator:
            queryset = queryset.filter(creator=creator)
        workflow_id = (request.GET.get("workflow_id") or "").strip()
        if workflow_id:
            queryset = queryset.filter(workflow_id=workflow_id)
        tag = (request.GET.get("tag") or "").strip()
        if tag:
            queryset = queryset.filter(tags__name=tag)
        priority = (request.GET.get("priority") or "").strip()
        if priority:
            queryset = queryset.filter(form_data__priority=priority)
        created_after = (request.GET.get("created_after") or "").strip()
        if created_after:
            queryset = queryset.filter(created_at__gte=created_after)
        created_before = (request.GET.get("created_before") or "").strip()
        if created_before:
            queryset = queryset.filter(created_at__lte=created_before)
        keyword = (request.GET.get("q") or "").strip()
        if keyword:
            text = Q(title__icontains=keyword) | Q(sn__icontains=keyword)
            if connection.vendor == "postgresql":
                queryset = queryset.annotate(_search=SearchVector("title", "sn", config="simple")).filter(
                    text | Q(_search=SearchQuery(keyword, config="simple"))
                )
            else:
                queryset = queryset.filter(text)
        page = Paginator(queryset, int(request.GET.get("page_size") or 20))
        current = page.get_page(int(request.GET.get("page") or 1))
        items = [TicketListSerializer(TicketListSerializer.from_ticket(item)).data for item in current]
        return WebUtils.response_success({"count": current.paginator.count, "items": items})
    payload = _body(request)
    version = WorkflowVersion.objects.select_related("workflow").get(id=payload["workflow_version_id"])
    ticket = _service().create(version, payload.get("form_data") or {}, _user(request), bool(payload.get("is_test")))
    service_id = payload.get("service_id")
    if service_id:
        ticket.service_id = service_id
        ticket.save(update_fields=["service", "updated_at"])
    return WebUtils.response_success({"id": ticket.id, "sn": ticket.sn, "status": ticket.status.key if ticket.status_id else ""})


@csrf_exempt
@HasPermission("ticket-Operate")
def operate_ticket(request, ticket_id):
    payload = _body(request)
    ticket = Ticket.objects.get(id=ticket_id)
    task = TicketTask.objects.get(id=payload["task_id"], ticket=ticket) if payload.get("task_id") else None
    updated = _service().operate(ticket, task, payload["action"], payload, _user(request))
    return WebUtils.response_success({"id": updated.id, "status": updated.status.key if updated.status_id else ""})


def _node_state(node, done_ids, pending_ids, status_key):
    node_id = node.get("id") or ""
    node_type = node.get("type") or ""
    if node_id in pending_ids:
        return "current"
    if node_id in done_ids or node_type == "start" or (node_type == "end" and status_key == "finished"):
        return "done"
    return "waiting"


def _apply_view_template(form, fields, status_key):
    if form is None or not fields:
        return fields
    chosen = None
    for item in form.view_templates.filter(is_enabled=True).order_by("id"):
        rules = item.match_rules or {}
        if rules.get("status") and rules.get("status") != status_key:
            continue
        chosen = item
        break
    order = (chosen.layout or {}).get("fields") if chosen else None
    if not isinstance(order, list) or not order:
        return fields
    by_key = {field.get("key"): field for field in fields}
    ordered = [by_key[key] for key in order if key in by_key]
    seen = {field.get("key") for field in ordered}
    return ordered + [field for field in fields if field.get("key") not in seen]


def _ticket_detail(ticket, username=""):
    tasks = list(ticket.tasks.all())
    done_ids = {task.node_id for task in tasks if task.status == TicketTask.TaskStatus.DONE}
    pending = [task for task in tasks if task.status in {TicketTask.TaskStatus.PENDING, TicketTask.TaskStatus.CLAIMED}]
    pending_ids = {task.node_id for task in pending}
    status_key = ticket.status.key if ticket.status_id else ""
    design = ticket.workflow_version.design if ticket.workflow_version_id else {}
    form = ticket.workflow.form if ticket.workflow_id and ticket.workflow.form_id else None
    schema = form.current_version.schema if form and form.current_version_id else {}
    fields = schema.get("fields") if isinstance(schema, dict) else None
    if not fields:
        fields = [{"key": key, "label": key, "type": "input"} for key in (ticket.form_data or {})]
    fields = _apply_view_template(form, fields, status_key)
    stages = []
    if ticket.workflow_id:
        for stage in ticket.workflow.stages.order_by("order", "id"):
            node_ids = stage.node_ids or []
            if any(node_id in pending_ids for node_id in node_ids):
                state = "current"
            elif node_ids and set(node_ids).issubset(done_ids):
                state = "done"
            else:
                state = "waiting"
            stages.append({"key": stage.key, "name": stage.name, "state": state})
    from apps.itsm.models.extend import SpecialOperationRule

    extra_actions = []
    for rule in SpecialOperationRule.objects.all():
        users = rule.users or []
        if not users or username in users:
            extra_actions.append(rule.action)
    return {
        "id": ticket.id,
        "sn": ticket.sn,
        "title": ticket.title,
        "status": status_key,
        "creator": ticket.creator,
        "form_data": ticket.form_data or {},
        "fields": fields,
        "stages": stages,
        "extra_actions": extra_actions,
        "tasks": [
            {
                "id": task.id,
                "node_id": task.node_id,
                "node_name": task.node_name,
                "assignee": task.assignee,
                "status": task.status,
            }
            for task in pending
        ],
        "nodes": [
            {
                "id": node.get("id") or "",
                "name": node.get("name") or node.get("id") or "",
                "type": node.get("type") or "",
                "state": _node_state(node, done_ids, pending_ids, status_key),
                "assignees": [task.assignee for task in pending if task.node_id == (node.get("id") or "") and task.assignee],
            }
            for node in (design.get("nodes") or [])
        ],
        "edges": [
            {"from": edge.get("from") or "", "to": edge.get("to") or "", "default": bool(edge.get("default"))} for edge in (design.get("edges") or [])
        ],
        "logs": [{"action": item.action, "operator": item.operator, "message": item.message} for item in ticket.logs.all()],
        "survey": {"score": ticket.survey.score, "comment": ticket.survey.comment} if hasattr(ticket, "survey") else None,
        "sla": [
            {
                "target": item.target,
                "due_at": item.due_at.isoformat(),
                "finished_at": item.finished_at.isoformat() if item.finished_at else "",
                "breached": item.breached,
                "paused": bool(item.paused_at),
            }
            for item in ticket.sla_records.all()
        ],
    }


@HasPermission("ticket-View")
def ticket_detail(request, ticket_id):
    ticket = (
        Ticket.objects.select_related("status", "workflow__form__current_version", "workflow_version", "survey")
        .prefetch_related("tasks", "logs", "sla_records", "workflow__stages", "workflow__form__view_templates")
        .get(id=ticket_id)
    )
    return WebUtils.response_success(_ticket_detail(ticket, _user(request)))


@csrf_exempt
@HasPermission("ticket-Operate")
def ticket_survey(request, ticket_id):
    ticket = Ticket.objects.select_related("status").get(id=ticket_id)
    if not ticket.status_id or ticket.status.key != "finished":
        return WebUtils.response_error("工单未完成")
    payload = _body(request)
    score = int(payload.get("score") or 0)
    if score < 1 or score > 5:
        return WebUtils.response_error("评分应为 1 到 5")
    survey, _created = TicketSurvey.objects.update_or_create(
        ticket=ticket,
        defaults={"score": score, "comment": str(payload.get("comment") or ""), "updated_by": _user(request), "created_by": _user(request)},
    )
    return WebUtils.response_success({"score": survey.score, "comment": survey.comment})


@HasPermission("ticket-View")
def ticket_logs(request, ticket_id):
    logs = TicketLog.objects.filter(ticket_id=ticket_id).order_by("id")
    return WebUtils.response_success({"items": [{"action": item.action, "operator": item.operator, "message": item.message} for item in logs]})
