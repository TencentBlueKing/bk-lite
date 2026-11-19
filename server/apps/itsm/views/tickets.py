import json

from django.conf import settings
from django.contrib.postgres.search import SearchQuery, SearchVector
from django.core.paginator import Paginator
from django.db import connection
from django.db.models import Exists, F, OuterRef, Prefetch, Q
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.web_utils import WebUtils
from apps.itsm.flowable.client import FlowableClient
from apps.itsm.models import TicketSLARecord, TicketSurvey, TicketTask, WorkflowVersion
from apps.itsm.models.extend import VipUser
from apps.itsm.serializers.ticket import TicketListSerializer
from apps.itsm.services.external_jobs import request_retry, retry_available
from apps.itsm.services.ticket.actions import node_actions, side_action_enabled
from apps.itsm.services.ticket.history import node_progress, ticket_history
from apps.itsm.services.ticket.listing import COLUMNS, date_bound, personal_group, validate_filters
from apps.itsm.services.ticket.service import TicketService, _find_node, workflow_schema
from apps.itsm.views.access import api_errors, domain_of, get_ticket, has_permission, ticket_scope


def _body(request):
    if not request.body:
        return {}
    return json.loads(request.body.decode("utf-8"))


def _service(request=None):
    from apps.itsm.services.integrations import request_identity

    identity = request_identity(request) if request is not None else None
    if not settings.FLOWABLE_PASSWORD:
        return TicketService(None, identity=identity)
    return TicketService(FlowableClient(settings.FLOWABLE_URL, settings.FLOWABLE_USER, settings.FLOWABLE_PASSWORD), identity=identity)


def _user(request):
    return getattr(getattr(request, "user", None), "username", "") or ""


@csrf_exempt
@api_errors
@HasPermission("ticket-View")
def tickets(request):
    if request.method == "GET":
        filters = validate_filters(
            {
                key: request.GET[key]
                for key in request.GET
                if key in {"q", "creator", "priority", "tag", "status", "tab", "ordering", "created_after", "created_before", "workflow_id"}
            }
        )
        fields = set(request.GET["fields"].split(",")) if "fields" in request.GET else None
        if fields is not None and (not fields or fields - set(COLUMNS)):
            raise ValueError("不支持的展示列")
        wanted = fields if fields is not None else set(COLUMNS)
        queryset = ticket_scope(request).select_related("status").defer("form_data")
        if "workflow" in wanted:
            queryset = queryset.select_related("workflow")
        if wanted.intersection({"node", "assignees"}):
            queryset = queryset.prefetch_related(Prefetch("tasks", queryset=TicketTask.objects.filter(status__in=["pending", "claimed"])))
        if "sla" in wanted:
            queryset = queryset.prefetch_related(
                Prefetch("sla_records", queryset=TicketSLARecord.objects.filter(finished_at__isnull=True).order_by("id"))
            )
        if "priority" in wanted:
            queryset = queryset.annotate(_priority=F("form_data__priority"))
        ordering = filters.get("ordering")
        if ordering:
            mapped = ordering.replace("status", "status__key")
            queryset = queryset.order_by(mapped, "-id")
        else:
            queryset = queryset.annotate(
                _vip=Exists(VipUser.objects.filter(domain=domain_of(request), username=OuterRef("creator"), is_enabled=True))
            )
            queryset = queryset.order_by("-_vip", "-id")
        status_key = filters.get("status", "")
        if status_key:
            queryset = queryset.filter(status__key__in=status_key.split(","))
        creator = (request.GET.get("creator") or "").strip()
        if creator:
            queryset = queryset.filter(creator=creator)
        workflow_id = (request.GET.get("workflow_id") or "").strip()
        if workflow_id:
            queryset = queryset.filter(workflow_id=workflow_id)
        tag = (request.GET.get("tag") or "").strip()
        if tag:
            queryset = queryset.filter(tags__name=tag).distinct()
        priority = (request.GET.get("priority") or "").strip()
        if priority:
            queryset = queryset.filter(form_data__priority=priority)
        created_after = (request.GET.get("created_after") or "").strip()
        if created_after:
            queryset = queryset.filter(created_at__gte=date_bound(created_after))
        created_before = (request.GET.get("created_before") or "").strip()
        if created_before:
            queryset = queryset.filter(created_at__lt=date_bound(created_before, end=True))
        keyword = (request.GET.get("q") or "").strip()
        if keyword:
            text = Q(title__icontains=keyword) | Q(sn__icontains=keyword)
            if connection.vendor == "postgresql":
                queryset = queryset.annotate(_search=SearchVector("title", "sn", config="simple")).filter(
                    text | Q(_search=SearchQuery(keyword, config="simple"))
                )
            else:
                queryset = queryset.filter(text)
        queryset = personal_group(queryset, filters.get("tab", "all"), _user(request))
        if request.GET.get("relation_for"):
            from apps.itsm.views.m2 import visible_relations

            source = get_ticket(request, int(request.GET["relation_for"]))
            pairs = visible_relations(request, source).values_list("ticket_id", "related_id")
            excluded = {source.pk}
            for left, right in pairs:
                excluded.update([left, right])
            queryset = queryset.exclude(pk__in=excluded)
        page = Paginator(queryset, max(1, min(100, int(request.GET.get("page_size") or 20))))
        current = page.get_page(int(request.GET.get("page") or 1))
        items = [TicketListSerializer(item, context={"fields": fields}).data for item in current]
        return WebUtils.response_success({"count": current.paginator.count, "items": items, "can_operate": has_permission(request, "ticket-Operate")})
    payload = _body(request)
    if not has_permission(request, "ticket-Add"):
        raise PermissionError()
    version = WorkflowVersion.objects.select_related("workflow").get(
        id=payload["workflow_version_id"], workflow__domain=domain_of(request), is_published=True
    )
    service_id = payload.get("service_id")
    from apps.itsm.services.service_access import check_service_request

    check_service_request(request, version, service_id)
    ticket = _service(request).create(version, payload.get("form_data") or {}, _user(request), bool(payload.get("is_test")))
    if service_id:
        ticket.service_id = service_id
        ticket.save(update_fields=["service", "updated_at"])
    return WebUtils.response_success({"id": ticket.id, "sn": ticket.sn, "status": ticket.status.key if ticket.status_id else ""})


@csrf_exempt
@api_errors
@HasPermission("ticket-Operate")
def operate_ticket(request, ticket_id):
    payload = _body(request)
    ticket = get_ticket(request, ticket_id)
    task = TicketTask.objects.get(id=payload["task_id"], ticket=ticket) if payload.get("task_id") else None
    updated = _service(request).operate(
        ticket, task, payload["action"], payload, _user(request), privileged=bool(getattr(request.user, "is_superuser", False))
    )
    return WebUtils.response_success({"id": updated.id, "status": updated.status.key if updated.status_id else ""})


@csrf_exempt
@require_POST
@api_errors
@HasPermission("ticket-Operate")
def retry_auto_node(request, ticket_id, execution_id):
    if not has_permission(request, "ticket-View") or not has_permission(request, "workflow-Edit"):
        raise PermissionError()
    if not request_retry(get_ticket(request, ticket_id), execution_id, _user(request)):
        return WebUtils.response_error(error_message="当前执行无法重试，请刷新并核对执行结果", status_code=409)
    return WebUtils.response_success({"id": execution_id})


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


def _ticket_detail(ticket, username="", privileged=False, can_operate=True, can_retry=False):
    from apps.itsm.models.extend import TicketProxy

    principals = set(TicketProxy.objects.filter(domain=ticket.domain, agent=username, is_enabled=True).values_list("principal", flat=True)) | {
        username
    }
    tasks = list(ticket.tasks.all())
    from apps.itsm.services.ticket.history import current_round_start

    design = ticket.workflow_version.design if ticket.workflow_version_id else {}
    round_start = current_round_start(ticket, tasks, design)
    round_tasks = [task for task in tasks if not round_start or task.created_at >= round_start]
    done_ids = {task.node_id for task in round_tasks if task.status == TicketTask.TaskStatus.DONE}
    done_ids.update(
        item.detail.get("node_id")
        for item in ticket.auto_executions.all()
        if item.status == "done" and (not round_start or item.created_at >= round_start)
    )
    pending = [task for task in tasks if task.status in {TicketTask.TaskStatus.PENDING, TicketTask.TaskStatus.CLAIMED}]
    pending_ids = {task.node_id for task in pending}
    status_key = ticket.status.key if ticket.status_id else ""
    design = ticket.workflow_version.design if ticket.workflow_version_id else {}
    form = ticket.workflow.form if ticket.workflow_id and ticket.workflow.form_id else None
    schema = workflow_schema(ticket.workflow_version) if ticket.workflow_version_id else {}
    from apps.itsm.services.form.fetch import public_schema

    schema = public_schema(schema, (ticket.form_data or {}).get("_field_labels"))
    fields = schema.get("fields") if isinstance(schema, dict) else None
    if not fields:
        fields = [{"key": key, "label": key, "type": "input"} for key in (ticket.form_data or {})]
    fields = _apply_view_template(form, fields, status_key)
    own_task = next((task for task in pending if privileged or task.assignee in principals), None)
    permissions = (
        _find_node(design, node_id=own_task.node_id).get("field_perm", {})
        if own_task
        else _find_node(design, node_type="submit").get("field_perm", {})
    )
    visible_keys = set()

    def visible_fields(items, inherited_hidden=False):
        result = []
        for field in items:
            hidden = inherited_hidden or field.get("state") == "hidden" or permissions.get(field.get("key"), permissions.get("*")) == "hidden"
            if hidden:
                continue
            visible_keys.add(field.get("key"))
            copied = dict(field)
            if copied.get("children"):
                copied["children"] = visible_fields(copied["children"])
            result.append(copied)
        return result

    fields = visible_fields(fields)

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
    for rule in SpecialOperationRule.objects.filter(domain=ticket.domain):
        users = rule.users or []
        if not users or username in users:
            extra_actions.append(rule.action)
    terminal = status_key in {"finished", "terminated", "cancelled"}
    creator = privileged or ticket.creator in principals
    handler = privileged or own_task is not None
    allowed_actions = []
    if terminal:
        if creator:
            allowed_actions.append("reopen")
    else:
        if creator:
            allowed_actions.extend(["withdraw", "urge"])
        if handler:
            allowed_actions.extend(["resume" if status_key == "suspended" else "suspend", "close", "terminate"])
            if status_key == "new":
                allowed_actions.append("respond")
    allowed_actions = [action for action in allowed_actions if side_action_enabled(design, tasks, action)]
    history = ticket_history(ticket, tasks, design)
    active_executions = {
        execution.id: execution
        for execution in ticket.auto_executions.all()
        if execution.detail.get("process_id") == ticket.process_instance_id and (not round_start or execution.created_at >= round_start)
    }
    for row in history:
        execution = active_executions.get(row.get("execution_id"))
        if execution:
            row["can_retry"] = can_retry and retry_available(ticket, execution)
    failed_ids = {row["node_id"] for row in history if row.get("execution_id") in active_executions and row["state"] == "failed"}
    pending_ids.update(row["node_id"] for row in history if row.get("execution_id") in active_executions and row["state"] == "current")
    progress_history = history
    if round_start:
        from django.utils.dateparse import parse_datetime

        progress_history = [row for row in history if row["started_at"] and parse_datetime(row["started_at"]) >= round_start]
    return {
        "history": history,
        "allowed_actions": allowed_actions if can_operate else [],
        "can_survey": can_operate and ticket.creator == username and status_key == "finished",
        "id": ticket.id,
        "sn": ticket.sn,
        "created_at": ticket.created_at.isoformat(),
        "workflow_name": ticket.workflow.name if ticket.workflow_id else "",
        "title": ticket.title,
        "status": status_key,
        "creator": ticket.creator,
        "form_data": {key: value for key, value in (ticket.form_data or {}).items() if key in visible_keys},
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
                "node_type": _find_node(design, node_id=task.node_id).get("type", ""),
                "field_perm": _find_node(design, node_id=task.node_id).get("field_perm", {}),
                "can_operate": can_operate and not terminal and status_key != "suspended" and (privileged or task.assignee in principals),
                "allowed_actions": node_actions(_find_node(design, node_id=task.node_id), task)
                if can_operate and not terminal and status_key != "suspended" and (privileged or task.assignee in principals)
                else [],
            }
            for task in pending
        ],
        "nodes": [
            node_progress(
                {
                    "id": node.get("id") or "",
                    "name": node.get("name") or {"start": "开始", "end": "结束"}.get(node.get("type")) or node.get("id") or "",
                    "type": node.get("type") or "",
                    "state": "failed" if node.get("id") in failed_ids else _node_state(node, done_ids, pending_ids, status_key),
                    "assignees": [task.assignee for task in pending if task.node_id == (node.get("id") or "") and task.assignee],
                },
                progress_history,
            )
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
                "warning_at": item.warning_at.isoformat() if item.warning_at else "",
                "finished_at": item.finished_at.isoformat() if item.finished_at else "",
                "breached": item.breached,
                "paused": bool(item.paused_at),
                "notices": [
                    {
                        "id": notice.id,
                        "kind": notice.kind,
                        "status": notice.status,
                        "triggered_at": notice.triggered_at.isoformat(),
                        "recipients": notice.recipients,
                        "message": notice.message,
                    }
                    for notice in item.notices.all()
                ],
            }
            for item in ticket.sla_records.all()
        ],
    }


@api_errors
@HasPermission("ticket-View")
def ticket_detail(request, ticket_id):
    ticket = (
        ticket_scope(request)
        .select_related("status", "workflow__form__current_version", "workflow_version", "survey")
        .prefetch_related("tasks", "logs", "sla_records__notices", "workflow__stages", "workflow__form__view_templates", "auto_executions")
        .get(id=ticket_id)
    )
    can_operate = has_permission(request, "ticket-Operate")
    return WebUtils.response_success(
        _ticket_detail(
            ticket,
            _user(request),
            bool(getattr(request.user, "is_superuser", False)),
            can_operate,
            can_operate and has_permission(request, "workflow-Edit"),
        )
    )


@csrf_exempt
@api_errors
@HasPermission("ticket-Operate")
def ticket_survey(request, ticket_id):
    ticket = get_ticket(request, ticket_id)
    if ticket.creator != _user(request):
        raise PermissionError()
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


@api_errors
@HasPermission("ticket-View")
def ticket_logs(request, ticket_id):
    ticket = get_ticket(request, ticket_id)
    logs = ticket.logs.all().order_by("id")
    return WebUtils.response_success({"items": [{"action": item.action, "operator": item.operator, "message": item.message} for item in logs]})


@api_errors
@HasPermission("ticket-Add")
def ticket_form(request, version_id):
    version = WorkflowVersion.objects.select_related("workflow__form__current_version").get(
        id=version_id, is_published=True, workflow__domain=domain_of(request)
    )
    from apps.itsm.services.service_access import check_service_request

    check_service_request(request, version, request.GET.get("service_id"))
    from apps.itsm.services.form.fetch import public_schema

    schema = public_schema(workflow_schema(version))
    if not schema.get("fields"):
        schema = {"version": 1, "fields": [{"key": "title", "type": "input", "label": "标题", "required": True}]}
    return WebUtils.response_success(
        {
            "schema": schema,
            "field_perm": _find_node(version.design, node_type="submit").get("field_perm", {}),
            "workflow_name": version.workflow.name,
            "creator": _user(request),
            "nodes": [
                {
                    "id": node["id"],
                    "name": node.get("name") or node["id"],
                    "type": node.get("type", ""),
                    "state": "current" if node.get("type") == "submit" else "waiting",
                }
                for node in (version.design or {}).get("nodes", [])
            ],
            "edges": [{"from": edge["from"], "to": edge["to"]} for edge in (version.design or {}).get("edges", [])],
        }
    )


@api_errors
@HasPermission("ticket-Add")
def ticket_workflows(request):
    from apps.itsm.models import Workflow
    from apps.itsm.services.service_access import visible_services

    allowed = visible_services(request).values("workflow_id")
    queryset = (
        Workflow.objects.filter(domain=domain_of(request), is_enabled=True, current_version__is_published=True)
        .filter(Q(services__isnull=True) | Q(id__in=allowed))
        .distinct()
        .order_by("-id")[:200]
    )
    return WebUtils.response_success(
        {
            "items": [
                {"id": item.id, "name": item.name, "key": item.key, "form_id": item.form_id, "current_version_id": item.current_version_id}
                for item in queryset
            ]
        }
    )
