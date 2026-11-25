import json
from hashlib import sha256
from uuid import uuid4

from django.conf import settings
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.web_utils import WebUtils
from apps.itsm.flowable.client import FlowableClient, FlowableError
from apps.itsm.models import Ticket, TicketSurvey, TicketTask, WorkflowVersion
from apps.itsm.serializers.ticket import TicketListSerializer
from apps.itsm.services.external_jobs import reconcile_execution, request_retry, result_field, retry_available, review_available
from apps.itsm.services.form.fetch import walk
from apps.itsm.services.form.table_columns import TABLE_FIELDS, configured_table_columns, hidden_column, visible_table_rows
from apps.itsm.services.ticket.actions import node_action_display, node_actions, node_required_opinions, side_action_enabled, side_required_opinions
from apps.itsm.services.ticket.form_filters import InvalidFormFilter
from apps.itsm.services.ticket.history import node_progress, ticket_history
from apps.itsm.services.ticket.listing import COLUMNS, FILTER_KEYS, filtered_tickets, project_columns, validate_filters
from apps.itsm.services.ticket.returns import return_targets
from apps.itsm.services.ticket.service import TicketService, _find_node, applicant_can_submit, workflow_schema
from apps.itsm.services.ticket.survey import SURVEY_READY, SurveyValidationError, survey_data, survey_snapshot, survey_submission
from apps.itsm.views.access import api_errors, domain_of, get_ticket, has_permission, json_object, ticket_scope
from apps.itsm.views.users import search_users


def _body(request):
    if not request.body:
        return {}
    return json.loads(request.body.decode("utf-8"))


def _http_creation_key(value):
    if value is None:
        return f"http:{uuid4().hex}"
    if not isinstance(value, str) or not value.strip() or len(value) > 128:
        raise ValueError({"creation_key": ["申请标识应为 1 至 128 个字符"]})
    return f"http:{sha256(value.encode('utf-8')).hexdigest()}"


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
        params = {key: request.GET[key] for key in FILTER_KEYS | {"form_filters"} if key in request.GET}
        fields = set(request.GET["fields"].split(",")) if "fields" in request.GET else None
        if fields is not None and (not fields or fields - set(COLUMNS)):
            raise ValueError("不支持的展示列")
        try:
            queryset = filtered_tickets(request, ticket_scope(request), validate_filters(params))
        except InvalidFormFilter as exc:
            return WebUtils.response_error(str(exc))
        queryset = project_columns(queryset, fields if fields is not None else set(COLUMNS))
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
        return WebUtils.response_success(
            {
                "count": current.paginator.count,
                "items": items,
                "can_operate": has_permission(request, "ticket-Operate"),
                "can_export": has_permission(request, "ticket-Export"),
                "can_apply": has_permission(request, "portal-View") and has_permission(request, "ticket-Add"),
            }
        )
    payload = _body(request)
    if not has_permission(request, "ticket-Add"):
        raise PermissionError()
    version = WorkflowVersion.objects.select_related("workflow").get(
        id=payload["workflow_version_id"], workflow__domain=domain_of(request), is_published=True
    )
    service_id = payload.get("service_id")
    from apps.itsm.services.service_access import check_service_request

    service = check_service_request(request, version, service_id)
    ticket = _service(request).create(
        version,
        payload.get("form_data") or {},
        _user(request),
        bool(payload.get("is_test")),
        service=service,
        creation_key=_http_creation_key(payload.get("creation_key")),
    )
    return WebUtils.response_success({"id": ticket.id, "sn": ticket.sn, "status": ticket.status.key if ticket.status_id else ""})


@csrf_exempt
@require_POST
@api_errors
@HasPermission("ticket-View")
def operate_ticket(request, ticket_id):
    payload = _body(request)
    applicant_only = not has_permission(request, "ticket-Operate")
    if applicant_only and (payload.get("action") != "submit" or not has_permission(request, "ticket-Add")):
        raise PermissionError()
    ticket = get_ticket(request, ticket_id)
    if payload.get("action") == "reopen" and ticket.process_instance_id and not isinstance(payload.get("reopen_from"), str):
        return WebUtils.response_error("请刷新工单详情后重新打开当前轮次", status_code=409)
    task = TicketTask.objects.get(id=payload["task_id"], ticket=ticket) if payload.get("task_id") else None
    updated = _service(request).operate(
        ticket,
        task,
        payload["action"],
        payload,
        _user(request),
        privileged=bool(getattr(request.user, "is_superuser", False)),
        applicant_submit_only=applicant_only,
    )
    return WebUtils.response_success({"id": updated.id, "status": updated.status.key if updated.status_id else ""})


@csrf_exempt
@require_POST
@api_errors
@HasPermission("ticket-Operate")
def operation_recovery(request, ticket_id):
    from apps.itsm.services.ticket.actions import NodeActionValidationError
    from apps.itsm.services.ticket.manual_recovery import abandon, active_operations, advance

    if not has_permission(request, "ticket-View"):
        raise PermissionError()
    ticket = get_ticket(request, ticket_id)
    body = _body(request)
    if not isinstance(body, dict) or body.get("decision") not in {None, "abandon"}:
        raise ValueError("无效的核对请求")
    cancel = body.get("decision") == "abandon"
    if cancel and not getattr(request.user, "is_superuser", False):
        raise PermissionError()
    operation = active_operations(ticket).first()
    if cancel and operation is None:
        return WebUtils.response_error("核对记录已变更，请刷新", status_code=409)
    if operation is None:
        return WebUtils.response_success({"id": ticket.pk, "status": "done"})
    if operation.operator != _user(request) and not getattr(request.user, "is_superuser", False):
        raise PermissionError()
    service = _service(request)
    if not service.client:
        return WebUtils.response_error("流程引擎暂不可用", status_code=503)
    try:
        if cancel:
            abandon(service, ticket, body, _user(request))
        else:
            advance(service, operation)
    except NodeActionValidationError as exc:
        return WebUtils.response_error(str(exc), status_code=409)
    except FlowableError:
        return WebUtils.response_error("尚未取得引擎回执，已保留原操作", status_code=409)
    return WebUtils.response_success({"id": ticket.pk, "status": "done"})


@require_GET
@api_errors
@HasPermission("ticket-Operate")
def transfer_candidates(request, ticket_id, task_id):
    if not has_permission(request, "ticket-View"):
        raise PermissionError()
    ticket = get_ticket(request, ticket_id)
    task = ticket.tasks.get(pk=task_id)
    users = TicketService().transfer_candidates(ticket, task, _user(request), privileged=bool(getattr(request.user, "is_superuser", False)))
    return WebUtils.response_success(search_users(request, users))


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


@csrf_exempt
@require_POST
@api_errors
@HasPermission("ticket-Operate")
def reconcile_auto_node(request, ticket_id, execution_id):
    if not has_permission(request, "ticket-View") or not has_permission(request, "workflow-Edit"):
        raise PermissionError()
    if not reconcile_execution(get_ticket(request, ticket_id), execution_id, _user(request), json_object(request)):
        return WebUtils.response_error(error_message="执行状态已变化，请刷新后核对", status_code=409)
    return WebUtils.response_success({"id": execution_id})


@csrf_exempt
@require_POST
@api_errors
@HasPermission("ticket-Operate")
def recover_start(request, ticket_id):
    from apps.itsm.services.ticket.start_recovery import confirm_not_started, recover_attempt

    if not has_permission(request, "ticket-View") or not has_permission(request, "workflow-Edit"):
        raise PermissionError()
    ticket = get_ticket(request, ticket_id)
    payload = _body(request)
    if type(payload.get("id")) is not int:
        return WebUtils.response_error("请选择当前启动记录", status_code=400)
    try:
        if payload.get("action") == "confirmed_not_started":
            if not isinstance(payload.get("sent_at"), str) or not payload["sent_at"]:
                raise ValueError("请刷新后核对本次发送记录")
            confirm_not_started(_service(request), ticket, payload["id"], payload.get("reason"), _user(request), expected_sent_at=payload["sent_at"])
        elif payload.get("action") == "check":
            recover_attempt(_service(request), ticket, payload["id"])
        else:
            raise ValueError("请选择有效的核对操作")
    except FlowableError as exc:
        if exc.status == 409:
            return WebUtils.response_error("引擎历史暂未能唯一确认该轮实例，请稍后核对。", status_code=409)
        raise
    except ValueError as exc:
        return WebUtils.response_error(str(exc), status_code=409)
    return WebUtils.response_success({"id": ticket.pk})


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


def ticket_principals(ticket, username):
    from apps.itsm.models.extend import TicketProxy

    return set(TicketProxy.objects.filter(domain=ticket.domain, agent=username, is_enabled=True).values_list("principal", flat=True)) | {username}


def ticket_form_view(ticket, design, own_task, status_key, *, include_legacy_fields=True):
    from apps.itsm.services.form.fetch import public_schema

    form = ticket.workflow.form if ticket.workflow_id and ticket.workflow.form_id else None
    schema = workflow_schema(ticket.workflow_version) if ticket.workflow_version_id else {}
    values = ticket.form_data or {}
    schema = public_schema(schema, values.get("_field_labels"))
    fields = schema.get("fields") if isinstance(schema, dict) else None
    if not fields:
        fields = [{"key": key, "label": key, "type": "input"} for key in values] if include_legacy_fields else []
    fields = _apply_view_template(form, fields, status_key)
    permissions = (
        _find_node(design, node_id=own_task.node_id).get("field_perm", {})
        if own_task
        else _find_node(design, node_type="submit").get("field_perm", {})
    )
    visible_values = {}

    def visible_fields(items):
        result = []
        for field in items:
            if hidden_column(field, permissions):
                continue
            key = field.get("key")
            copied = dict(field)
            if field.get("type") in TABLE_FIELDS:
                columns = configured_table_columns(field)
                allowed = [column for column in columns if column.get("key") and not hidden_column(column, permissions)]
                if not allowed:
                    continue
                copied["children"] = allowed
                if key in values:
                    visible_values[key] = visible_table_rows(
                        values[key],
                        {column["key"] for column in allowed},
                        f"ticket:{ticket.pk}",
                        key,
                        preserve_hidden=any(hidden_column(column, permissions) for column in columns),
                    )
            else:
                if key in values:
                    visible_values[key] = values[key]
                if copied.get("children"):
                    copied["children"] = visible_fields(copied["children"])
            result.append(copied)
        return result

    fields = visible_fields(fields)
    return fields, visible_values, schema, permissions


def select_task(pending, principals, privileged, task_id=None):
    for task in pending:
        if (privileged or task.assignee in principals) and (task_id is None or str(task.id) == str(task_id)):
            return task
    if task_id is not None:
        raise PermissionError()
    return None


def editable_task(request, ticket, task_id):
    if not has_permission(request, "ticket-View"):
        raise PermissionError()
    if ticket.status_id and ticket.status.key in {"suspended", "finished", "terminated", "cancelled"}:
        raise PermissionError()
    pending = ticket.tasks.filter(status__in=[TicketTask.TaskStatus.PENDING, TicketTask.TaskStatus.CLAIMED])
    task = select_task(pending, ticket_principals(ticket, _user(request)), getattr(request.user, "is_superuser", False), task_id)
    if task is None or not (
        has_permission(request, "ticket-Operate") or (has_permission(request, "ticket-Add") and applicant_can_submit(ticket, task, _user(request)))
    ):
        raise PermissionError()
    return task


def _ticket_detail(ticket, username="", privileged=False, can_operate=True, can_retry=False, task_id=None, can_apply=False):
    from apps.itsm.services.ticket.history import current_round_start
    from apps.itsm.services.ticket.manual_recovery import active_operations, can_abandon
    from apps.itsm.services.ticket.start_recovery import start_recovery_info

    operation = active_operations(ticket).first()
    recovery = None
    if operation:
        recovery = {
            "action": operation.action,
            "status": operation.status,
            "can_check": can_operate and (privileged or username == operation.operator),
            "can_abandon": bool(privileged and can_operate and can_abandon(operation)),
        }
        if privileged and can_operate:
            recovery.update(token=str(operation.token), sent_at=operation.payload.get("sent_at"))

    principals = ticket_principals(ticket, username)
    tasks = sorted(ticket.tasks.all(), key=lambda task: task.pk)
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
    own_task = select_task(pending, principals, privileged, task_id)
    if task_id is not None and (
        status_key in {"suspended", "finished", "terminated", "cancelled"}
        or not (can_operate or (can_apply and applicant_can_submit(ticket, own_task, username)))
    ):
        raise PermissionError()
    start = start_recovery_info(ticket, can_retry)
    engine_pending = bool(operation or start or ticket.creation_state != "complete")
    can_operate = can_operate and not engine_pending
    fields, values, schema, _ = ticket_form_view(ticket, design, own_task, status_key)
    visible_keys = {field["key"] for field in walk(fields)}
    form_rules = [
        rule for rule in (schema or {}).get("rules", []) if rule.get("type") in {"required", "visible"} and rule.get("field") in visible_keys
    ]

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
    allowed_actions = [action for action in allowed_actions if can_operate and side_action_enabled(design, tasks, action)]
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
            if can_retry and review_available(ticket, execution):
                row["review_token"] = execution.updated_at.isoformat()
                row["result_field"] = result_field(ticket, execution)
                row["job_id"] = execution.detail.get("job_id")
    failed_ids = {row["node_id"] for row in history if row.get("execution_id") in active_executions and row["state"] == "failed"}
    pending_ids.update(row["node_id"] for row in history if row.get("execution_id") in active_executions and row["state"] == "current")
    progress_history = history
    if round_start:
        from django.utils.dateparse import parse_datetime

        progress_history = [row for row in history if row["started_at"] and parse_datetime(row["started_at"]) >= round_start]

    task_rows = []
    for task in pending:
        node = _find_node(design, node_id=task.node_id)
        editable = can_operate and not terminal and status_key != "suspended" and (privileged or task.assignee in principals)
        available = node_actions(node, task) if editable else []
        if (
            not editable
            and can_apply
            and not engine_pending
            and not terminal
            and status_key != "suspended"
            and applicant_can_submit(ticket, task, username)
        ):
            editable, available = True, ["submit"]
        targets = return_targets(ticket, task, tasks, design, round_start) if "return" in available else []
        if "return" in available and not targets:
            available.remove("return")
        task_rows.append(
            {
                "id": task.id,
                "node_id": task.node_id,
                "node_name": task.node_name,
                "assignee": task.assignee,
                "status": task.status,
                "node_type": node.get("type", ""),
                "field_perm": node.get("field_perm", {}),
                "can_operate": editable,
                "allowed_actions": available,
                "action_display": node_action_display(node, [*available, *allowed_actions]) if editable else [],
                "required_opinion_actions": node_required_opinions(node, available),
                "return_targets": targets,
            }
        )

    action_task = own_task or (pending[0] if pending else None)
    action_node = _find_node(design, node_id=action_task.node_id) if action_task else {}
    survey = getattr(ticket, "survey", None)
    return {
        "history": history,
        "reopen_from": ticket.process_instance_id if "reopen" in allowed_actions else None,
        "start_recovery": start if can_retry else None,
        "engine_pending": engine_pending,
        "manual_recovery": recovery,
        "allowed_actions": allowed_actions,
        "action_display": node_action_display(action_node, allowed_actions),
        "required_opinion_actions": side_required_opinions(design, tasks, allowed_actions) if can_operate else [],
        "can_survey": can_operate and ticket.creator == username and status_key == "finished" and survey is None,
        "id": ticket.id,
        "sn": ticket.sn,
        "created_at": ticket.created_at.isoformat(),
        "workflow_name": ticket.workflow.name if ticket.workflow_id else "",
        "title": ticket.title,
        "status": status_key,
        "creator": ticket.creator,
        "form_data": values,
        "fields": fields,
        "form_rules": form_rules,
        "stages": stages,
        "extra_actions": [] if engine_pending else extra_actions,
        "tasks": task_rows,
        "selected_task_id": own_task.id if own_task else None,
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
        "survey": survey_data(survey) if survey is not None else None,
        "survey_template": survey_snapshot(ticket, ticket.logs.all()) if status_key == "finished" else None,
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
    detail = _ticket_detail(
        ticket, _user(request), bool(getattr(request.user, "is_superuser", False)), can_operate,
        can_operate and has_permission(request, "workflow-Edit"), task_id=request.GET.get("task_id"),
        can_apply=has_permission(request, "ticket-Add"),
    )
    _mark_executing_nodes(request, ticket, detail)
    return WebUtils.response_success(detail)


def _mark_executing_nodes(request, ticket, detail):
    if detail["status"] in {"finished", "cancelled", "terminated", "suspended"}:
        return
    nodes = {node["id"]: node for node in detail["nodes"]}
    executing = set()
    for row in detail["history"]:
        node = nodes.get(row["node_id"])
        if row.get("action") == "auto" and row["state"] == "current" and node and node["state"] == "current" and "can_retry" in row:
            row["executing"] = True
            executing.add(node["id"])
    # 自动任务尚未入库、或父流程正等待子流程时，从该实例读取实际活动位置。
    if ticket.process_instance_id and not any(n["state"] in {"current", "failed"} for n in nodes.values()):
        client = _service(request).client
        if client:
            try:
                activity_ids = client.active_activity_ids(ticket.process_instance_id)
            except FlowableError:
                activity_ids = set()
            for node_id in sorted(activity_ids & nodes.keys()):
                node = nodes[node_id]
                executing.add(node_id)
                detail["history"].append({
                    "id": f"runtime-{node_id}", "node_id": node_id, "name": node["name"], "action": "runtime",
                    "action_label": "执行中", "state": "current", "executing": True, "operator": "",
                    "started_at": "", "finished_at": "", "message": "",
                })
    for node_id in executing:
        nodes[node_id].update(state="current", outcome="current", executing=True)


@csrf_exempt
@require_POST
@api_errors
@HasPermission("ticket-Operate")
@transaction.atomic
def ticket_survey(request, ticket_id):
    ticket = get_ticket(request, ticket_id)
    if not has_permission(request, "ticket-View") or ticket.creator != _user(request):
        raise PermissionError()
    ticket = Ticket.objects.select_for_update().get(id=ticket.id)
    if not ticket.status_id or ticket.status.key != "finished":
        return WebUtils.response_error("工单未完成")
    try:
        submission = survey_submission(_body(request), survey_snapshot(ticket, ticket.logs.filter(action=SURVEY_READY)))
    except SurveyValidationError as exc:
        return WebUtils.response_error(str(exc))
    survey, created = TicketSurvey.objects.get_or_create(
        ticket=ticket,
        defaults={**submission, "domain": ticket.domain, "updated_by": _user(request), "created_by": _user(request)},
    )
    result = survey_data(survey)
    if not created and submission != result:
        return WebUtils.response_error("满意度已提交", status_code=409)
    return WebUtils.response_success(result)


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
