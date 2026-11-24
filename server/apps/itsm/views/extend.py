import json
from datetime import timedelta
from functools import wraps

from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Exists, OuterRef, Prefetch, Q
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
from jinja2 import TemplateError
from jinja2.sandbox import SandboxedEnvironment

from apps.core.decorators.api_permission import HasPermission
from apps.core.logger import itsm_logger as logger
from apps.core.utils.web_utils import WebUtils
from apps.itsm.models import TicketRelation, TicketTask, VipUser
from apps.itsm.models.extend import (
    AiSetting,
    Announcement,
    AutoExecution,
    BizObject,
    BizRecord,
    ChangeWindow,
    ChatMessage,
    ChatSession,
    DecisionTable,
    DutyShift,
    EmailRule,
    Handover,
    PrintTemplate,
    ReportCard,
    ScheduledRun,
    ScheduledTask,
    SearchField,
    SpecialOperationRule,
    SurveyTemplate,
    TicketProxy,
    TicketSavedView,
    Trigger,
    UserPreference,
)
from apps.itsm.services.ticket.actions import node_actions, node_required_opinions
from apps.itsm.services.ticket.handover import ACTIVE_STATUSES, handover_user, prepare_handover, run_handover
from apps.itsm.services.ticket.service import _find_node
from apps.itsm.services.ticket.survey import SurveyValidationError, normalize_survey_template
from apps.itsm.services.trigger_config import TriggerConfigError, normalize_trigger
from apps.itsm.views.access import api_errors, domain_of, get_ticket, has_permission, ticket_scope
from apps.itsm.views.knowledge import knowledge_resources
from apps.itsm.views.tickets import _service, _user

KINDS = {
    "views": (TicketSavedView, ["name", "filters", "columns"]),
    "proxies": (TicketProxy, ["principal", "agent", "is_enabled"]),
    "decisions": (DecisionTable, ["name", "workflow_id", "rules"]),
    "triggers": (Trigger, ["name", "event", "action", "config", "is_enabled"]),
    "schedules": (ScheduledTask, ["name", "cron", "action", "is_enabled"]),
    "announcements": (Announcement, ["title", "content", "is_enabled"]),
    "changes": (ChangeWindow, ["name", "start_at", "end_at"]),
    "duties": (DutyShift, ["name", "members"]),
    "surveys": (SurveyTemplate, ["name", "questions"]),
    "prints": (PrintTemplate, ["name", "body"]),
    "handovers": (Handover, ["from_user", "to_user", "ticket_ids"]),
    "special_rules": (SpecialOperationRule, ["action", "users"]),
    "reports": (ReportCard, ["kind"]),
    "vips": (VipUser, ["username", "is_enabled"]),
    "ai": (AiSetting, ["name", "kind", "prompt"]),
    "chats": (ChatSession, ["visitor", "agent", "status"]),
    "biz_objects": (BizObject, ["name", "key", "status", "schema"]),
    "emails": (EmailRule, ["name", "mailbox", "service_id", "is_enabled"]),
    "search_fields": (SearchField, ["key", "label"]),
    "preferences": (UserPreference, ["notify_events"]),
}


RESOURCE_MENUS = {
    "views": "ticket_center_setting",
    "proxies": "setting",
    "decisions": "rule",
    "triggers": "rule",
    "schedules": "rule",
    "announcements": "setting",
    "changes": "change",
    "knowledge": "knowledge",
    "duties": "duty",
    "surveys": "survey",
    "prints": "print",
    "handovers": "handover",
    "special_rules": "setting",
    "reports": "ticket_center_setting",
    "vips": "setting",
    "ai": "ai",
    "chats": "chat",
    "biz_objects": "biz_object",
    "emails": "setting",
    "search_fields": "ticket_center_setting",
    "preferences": "ticket_center_setting",
}
PERSONAL_RESOURCES = {"views", "reports", "preferences"}


def resource_permission(view):
    @wraps(view)
    def wrapped(request, kind, *args, **kwargs):
        menu = RESOURCE_MENUS.get(kind)
        action = "View" if request.method == "GET" else "Delete" if request.method == "DELETE" else "Add" if request.method == "POST" else "Edit"
        if menu in {"setting", "ticket_center_setting"} and action != "View":
            action = "Edit"
        if not menu or not has_permission(request, f"{menu}-{action}"):
            raise PermissionError()
        return view(request, kind, *args, **kwargs)

    return wrapped


def resource_scope(request, kind, model):
    queryset = model.objects.filter(domain=domain_of(request))
    return queryset.filter(username=_user(request)) if kind in PERSONAL_RESOURCES else queryset


def _body(request):
    if not request.body:
        return {}
    return json.loads(request.body.decode("utf-8"))


def _public(item, fields):
    data = {"id": item.id}
    for field in fields:
        value = getattr(item, field)
        if hasattr(value, "isoformat"):
            value = value.isoformat()
        data[field] = value
    if isinstance(item, ScheduledTask):
        data["next_run_at"] = item.next_run_at.isoformat() if item.next_run_at else None
    if isinstance(item, Handover):
        data.update(created_at=item.created_at.isoformat(), results=item.results)
    return data


@transaction.atomic
def _save_schedule(request, values, item=None):
    from apps.itsm.services.schedules import register_schedule, schedule_config, target_workflow
    from apps.itsm.services.service_access import check_service_request

    username = _user(request)
    preserve_next = False
    if item is None:
        item = ScheduledTask(created_by=username, **values)
    else:
        item = ScheduledTask.objects.select_for_update().get(id=item.id, domain=domain_of(request))
        preserve_next = all(getattr(item, field) == value for field, value in values.items() if field in {"cron", "action", "is_enabled"})
        for field, value in values.items():
            setattr(item, field, value)
        if set(values) == {"is_enabled", "domain"} and item.is_enabled is False:
            item.next_run_at = None
            item.save(update_fields=["is_enabled", "next_run_at", "updated_at"])
            return WebUtils.response_success(_public(item, KINDS["schedules"][1]))
    try:
        config = schedule_config(item)
        if config["task"] == "create_ticket":
            if not has_permission(request, "ticket-Add"):
                raise PermissionError()
            check_service_request(request, target_workflow(item, config).current_version)
        if not isinstance(item.name, str) or not item.name.strip() or len(item.name) > 128:
            raise ValueError("任务名称需为 1 至 128 个字符")
        if type(item.is_enabled) is not bool or not isinstance(item.cron, str):
            raise ValueError("任务状态或周期格式错误")
        item.updated_by = username
        item.save()
        register_schedule(item, preserve_next=preserve_next and item.next_run_at is not None)
    except (ValueError, TypeError) as exc:
        transaction.set_rollback(True)
        return WebUtils.response_error(error_message=str(exc) if not isinstance(exc, (json.JSONDecodeError, TypeError)) else "定时任务配置格式错误")
    return WebUtils.response_success(_public(item, KINDS["schedules"][1]))


@require_GET
@api_errors
@HasPermission("rule-View")
def schedule_runs(request):
    queryset = ScheduledRun.objects.filter(domain=domain_of(request)).order_by("-due_at", "-id")
    if request.GET.get("schedule_id"):
        queryset = queryset.filter(schedule_id=int(request.GET["schedule_id"]))
    paginator = Paginator(queryset, 20)
    page = paginator.get_page(int(request.GET.get("page", "1")))
    rows = list(page)
    visible = set()
    if has_permission(request, "ticket-View"):
        visible = set(ticket_scope(request).filter(id__in=[row.ticket_id for row in rows if row.ticket_id]).values_list("id", flat=True))
    items = []
    for row in rows:
        data = _public(row, ["schedule_name", "due_at", "status", "message", "created_at", "finished_at"])
        if row.status == "running" and row.created_at < timezone.now() - timedelta(minutes=5):
            data.update(status="unconfirmed", message="超过执行等待时间，请核对结果")
        items.append({**data, "ticket_id": row.ticket_id if row.ticket_id in visible else None})
    return WebUtils.response_success({"items": items, "count": paginator.count})


def _list_resources(request, kind, model, fields):
    page_size = max(1, min(100, int(request.GET.get("page_size") or 100)))
    paginator = Paginator(resource_scope(request, kind, model).order_by("-id"), page_size)
    page = paginator.get_page(int(request.GET.get("page") or 1))
    items = [_public(item, fields) for item in page]
    data = {"items": items, "count": paginator.count}
    if kind in {"schedules", "triggers", "surveys"}:
        menu = RESOURCE_MENUS[kind]
        data.update(
            can_add=has_permission(request, f"{menu}-Add"),
            can_edit=has_permission(request, f"{menu}-Edit"),
            can_delete=has_permission(request, f"{menu}-Delete"),
        )
    if kind == "handovers":
        can_retry = has_permission(request, "handover-Add")
        data.update(can_add=can_retry and has_permission(request, "ticket-View"), can_retry=can_retry)
    return WebUtils.response_success(data)


@csrf_exempt
@api_errors
@resource_permission
def resources(request, kind):
    if kind == "knowledge":
        return knowledge_resources(request)
    spec = KINDS.get(kind)
    if spec is None:
        return WebUtils.response_error("未知资源")
    model, fields = spec
    if request.method == "GET":
        return _list_resources(request, kind, model, fields)
    if kind in {"surveys", "triggers"} and request.method != "POST":
        return WebUtils.response_error("不支持的请求方法", status_code=405)
    payload = _body(request)
    values = {field: payload.get(field) for field in fields if field in payload}
    values["domain"] = domain_of(request)
    if kind == "schedules":
        return _save_schedule(request, values)
    if kind == "triggers":
        return _save_trigger(request, values)
    if kind == "surveys":
        try:
            values = normalize_survey_template(values, creating=True)
        except SurveyValidationError as exc:
            return WebUtils.response_error(error_message=str(exc))
    if kind == "reports":
        values["username"] = _user(request)
    if kind == "preferences":
        item, _created = UserPreference.objects.update_or_create(
            domain=domain_of(request),
            username=_user(request),
            defaults={**values, "updated_by": _user(request)},
        )
        return WebUtils.response_success(_public(item, fields))
    if kind == "views":
        values["username"] = _user(request)
    if kind == "duties" and payload.get("check_in"):
        return _check_in_duty(request, model, fields, payload)
    if kind == "changes":
        from django.utils.dateparse import parse_datetime

        start = parse_datetime(str(values.get("start_at") or "")) if values.get("start_at") else None
        end = parse_datetime(str(values.get("end_at") or "")) if values.get("end_at") else None
        values["start_at"] = start
        values["end_at"] = end
        if start and end and ChangeWindow.objects.filter(domain=domain_of(request)).filter(start_at__lt=end, end_at__gt=start).exists():
            return WebUtils.response_error("变更窗口冲突")
    if kind == "vips" and not str(values.get("username") or "").strip():
        return WebUtils.response_error("请选择用户")
    if kind == "proxies" and (not str(values.get("principal") or "").strip() or not str(values.get("agent") or "").strip()):
        return WebUtils.response_error("请选择被代理人和代理人")
    if kind == "handovers":
        if request.method != "POST":
            return WebUtils.response_error("不支持的请求方法", status_code=405)
        item = Handover(**values, opinion=payload.get("opinion", ""), created_by=_user(request), updated_by=_user(request))
        _apply_handover(item)
        return WebUtils.response_success(_public(item, fields))
    try:
        item = model.objects.create(**values, created_by=_user(request), updated_by=_user(request))
    except Exception as exc:
        from django.db import IntegrityError

        if isinstance(exc, IntegrityError):
            return WebUtils.response_error("记录已存在")
        raise
    if kind == "decisions":
        from apps.itsm.services.dmn import deploy_table

        return WebUtils.response_success({**_public(item, fields), "dmn": deploy_table(item)})
    return WebUtils.response_success(_public(item, fields))


@csrf_exempt
@api_errors
@resource_permission
def resource_item(request, kind, item_id):
    if kind == "knowledge":
        return knowledge_resources(request, item_id=item_id)
    spec = KINDS.get(kind)
    if spec is None:
        return WebUtils.response_error("未知资源")
    model, fields = spec
    item = resource_scope(request, kind, model).filter(id=item_id).first()
    if item is None:
        return WebUtils.response_error("记录不存在")
    if kind == "handovers" and item.results:
        return WebUtils.response_error("交接执行记录不允许修改或删除", status_code=405)
    if request.method == "DELETE":
        item.delete()
        return WebUtils.response_success({"id": item_id})
    if request.method not in {"PUT", "PATCH"}:
        return WebUtils.response_error("不支持的方法")
    payload = _body(request)
    values = {field: payload.get(field) for field in fields if field in payload}
    values["domain"] = domain_of(request)
    if kind == "schedules":
        return _save_schedule(request, values, item)
    if kind == "triggers":
        return _save_trigger(request, values, item)
    if kind == "surveys":
        try:
            values = normalize_survey_template(values)
        except SurveyValidationError as exc:
            return WebUtils.response_error(error_message=str(exc))
    for field, value in values.items():
        setattr(item, field, value)
    item.updated_by = _user(request)
    item.save()
    return WebUtils.response_success(_public(item, fields))


@transaction.atomic
def _save_trigger(request, values, item=None):
    username = _user(request)
    domain = values["domain"]
    if item is not None:
        item = Trigger.objects.select_for_update().get(pk=item.pk, domain=domain)
    deactivating = item is not None and set(values) == {"is_enabled", "domain"} and values["is_enabled"] is False
    if not deactivating:
        try:
            values = normalize_trigger(values, domain=domain, current=item, user=request.user)
        except TriggerConfigError as exc:
            return WebUtils.response_error(error_message=str(exc))
    if item is None:
        item = Trigger.objects.create(**values, created_by=username, updated_by=username)
    else:
        for field, value in values.items():
            setattr(item, field, value)
        item.updated_by = username
        item.save(update_fields=[*values, "updated_by", "updated_at"])
    return WebUtils.response_success(_public(item, KINDS["triggers"][1]))


def _check_in_duty(request, model, fields, payload):
    shift = resource_scope(request, "duties", model).filter(name=payload.get("name")).first()
    if shift is None:
        return WebUtils.response_error("值班记录不存在")
    members = list(shift.members or [])
    username = _user(request)
    if username not in members:
        members.append(username)
    shift.members = members
    shift.updated_by = username
    shift.save(update_fields=["members", "updated_by", "updated_at"])
    return WebUtils.response_success(_public(shift, fields))


def _apply_handover(item: Handover) -> None:
    service = _service()
    prepare_handover(item, service)
    run_handover(item, service, item.created_by or item.from_user)


@require_GET
@api_errors
@HasPermission("handover-Add")
def handover_candidates(request):
    if not has_permission(request, "ticket-View"):
        raise PermissionError()
    source = handover_user(request.GET.get("from_user"))
    tasks = TicketTask.objects.filter(assignee=source, status__in=ACTIVE_STATUSES)
    tickets = (
        ticket_scope(request)
        .filter(Exists(tasks.filter(ticket_id=OuterRef("pk"))))
        .exclude(status__key__in=["suspended", "finished", "terminated", "cancelled"])
    )
    keyword = (request.GET.get("q") or "").strip()
    if keyword:
        tickets = tickets.filter(Q(sn__icontains=keyword) | Q(title__icontains=keyword))
    tickets = (
        tickets.select_related("workflow_version")
        .only("id", "sn", "title", "workflow_version__design")
        .prefetch_related(Prefetch("tasks", queryset=tasks.only("ticket_id", "node_id", "status"), to_attr="handover_tasks"))
    )
    paginator = Paginator(tickets.order_by("-id"), 20)
    page = paginator.get_page(request.GET.get("page"))
    items = []
    for ticket in page:
        design = ticket.workflow_version.design if ticket.workflow_version_id else {}
        required = False
        for task in ticket.handover_tasks:
            node = _find_node(design, node_id=task.node_id)
            if "transfer" in node_required_opinions(node, node_actions(node, task)):
                required = True
                break
        items.append({"id": ticket.id, "sn": ticket.sn, "title": ticket.title, "requires_opinion": required})
    return WebUtils.response_success({"items": items, "count": paginator.count})


@csrf_exempt
@require_POST
@api_errors
@HasPermission("handover-Add")
def retry_handover(request, handover_id):
    item = Handover.objects.get(pk=handover_id, domain=domain_of(request))
    run_handover(item, _service(), _user(request))
    return WebUtils.response_success(_public(item, KINDS["handovers"][1]))


@csrf_exempt
@api_errors
@HasPermission("ticket-View")
def batch_options(request):
    from apps.itsm.services.ticket.batch import selection, validate_ids

    if request.method != "POST":
        return WebUtils.response_error("不支持的请求方法", status_code=405)
    options, _ = selection(request, validate_ids(_body(request).get("ids")))
    return WebUtils.response_success(options)


@csrf_exempt
@api_errors
@HasPermission("ticket-View")
def batch_operate(request):
    from django.http import Http404

    from apps.itsm.flowable.client import FlowableError
    from apps.itsm.models import TicketFollower

    if request.method != "POST":
        return WebUtils.response_error("不支持的请求方法", status_code=405)
    payload = _body(request)
    ids = payload.get("ids")
    action = payload.get("action")
    if not isinstance(ids, list) or not 1 <= len(ids) <= 50 or any(type(pk) is not int or pk <= 0 for pk in ids):
        raise ValueError("请选择1至50张工单")
    if action not in {"submit", "approve", "reject", "claim", "urge", "suspend", "resume", "follow", "unfollow"}:
        raise ValueError("不支持的批量操作")
    if action not in {"follow", "unfollow"} and not has_permission(request, "ticket-Operate"):
        raise PermissionError()
    opinion = payload.get("opinion", "")
    if not isinstance(opinion, str) or len(opinion) > 1000:
        raise ValueError("意见过长")
    from apps.itsm.services.ticket.batch import selection

    options, _ = selection(request, list(dict.fromkeys(ids)))
    if action not in {"follow", "unfollow"} and options["mixed_nodes"]:
        return WebUtils.response_success({"items": [{"id": pk, "ok": False, "error": options["reason"]} for pk in dict.fromkeys(ids)]})
    if action in options["required_opinion_actions"] and not opinion.strip():
        return WebUtils.response_success({"items": [{"id": pk, "ok": False, "error": "请填写处理意见"} for pk in dict.fromkeys(ids)]})
    username = _user(request)
    privileged = bool(getattr(request.user, "is_superuser", False))
    principals = {
        username,
        *TicketProxy.objects.filter(domain=domain_of(request), agent=username, is_enabled=True).values_list("principal", flat=True),
    }
    results = []
    for pk in dict.fromkeys(ids):
        try:
            ticket = get_ticket(request, pk)
            if action == "follow":
                TicketFollower.objects.get_or_create(ticket=ticket, username=username, defaults={"domain": ticket.domain, "created_by": username})
            elif action == "unfollow":
                ticket.followers.filter(username=username).delete()
            else:
                task = None
                if action in {"submit", "approve", "reject", "claim"}:
                    tasks = ticket.tasks.filter(status__in=["pending", "claimed"])
                    if not privileged:
                        tasks = tasks.filter(assignee__in=principals)
                    candidates = list(tasks[:2])
                    if len(candidates) != 1:
                        raise ValueError("待办任务不唯一或无处理权限，请进入详情确认")
                    task = candidates[0]
                _service().operate(ticket, task, action, {"opinion": opinion}, username, privileged=privileged)
            results.append({"id": pk, "ok": True})
        except Http404:
            results.append({"id": pk, "ok": False, "error": "工单不存在或无查看权限"})
        except PermissionError:
            results.append({"id": pk, "ok": False, "error": "无操作权限或当前节点不支持此操作"})
        except (ValueError, TicketTask.DoesNotExist) as exc:
            detail = "必填字段未完成，请进入详情补齐" if exc.args and isinstance(exc.args[0], dict) else str(exc)
            results.append({"id": pk, "ok": False, "error": detail or "任务已变化，请刷新"})
        except FlowableError:
            results.append({"id": pk, "ok": False, "error": "流程引擎暂不可用，请刷新核对后再操作"})
    return WebUtils.response_success({"items": results})


@csrf_exempt
@api_errors
@HasPermission("workflow-Edit")
def execute_decision(request, decision_id):
    table = DecisionTable.objects.filter(domain=domain_of(request)).get(id=decision_id)
    form_data = _body(request).get("form_data") or {}
    matched = {}
    for rule in table.rules or []:
        when = rule.get("when") or {}
        if str(form_data.get(when.get("field"))) == str(when.get("value")):
            matched = rule.get("then") or {}
            break
    return WebUtils.response_success({"matched": matched})


@csrf_exempt
@api_errors
@HasPermission("ticket-Add")
def create_child(request, ticket_id):
    parent = ticket_scope(request).select_related("workflow_version").get(id=ticket_id)
    payload = _body(request)
    child = _service().create(parent.workflow_version, payload.get("form_data") or {"title": parent.title}, _user(request))
    TicketRelation.objects.create(
        ticket=parent,
        related=child,
        relation_type="child",
        created_by=_user(request),
        updated_by=_user(request),
    )
    return WebUtils.response_success({"id": child.id, "sn": child.sn})


@csrf_exempt
@api_errors
@HasPermission("ticket-View")
def render_print(request, ticket_id):
    ticket = get_ticket(request, ticket_id)
    template = PrintTemplate.objects.filter(domain=domain_of(request)).order_by("-id").first()
    body = template.body if template else "{{ title }}"
    try:
        rendered = SandboxedEnvironment(autoescape=True).from_string(body).render(title=ticket.title, sn=ticket.sn, creator=ticket.creator)
    except TemplateError as exc:
        raise ValueError("打印模板不合法") from exc
    return WebUtils.response_success({"html": rendered})


@csrf_exempt
@api_errors
@HasPermission("ticket-Operate")
def run_auto(request, ticket_id):
    ticket = get_ticket(request, ticket_id)
    payload = _body(request)
    if not has_permission(request, "workflow-Edit"):
        raise PermissionError()
    kind = payload.get("kind") or "table"
    config = payload.get("config") or {}
    from apps.itsm.services.auto_runner import run_auto_action

    status, detail = run_auto_action(ticket, kind, config, _user(request))
    item = AutoExecution.objects.create(
        ticket=ticket,
        kind=kind,
        status=status,
        detail=detail,
        created_by=_user(request),
        updated_by=_user(request),
    )
    return WebUtils.response_success({"id": item.id, "status": item.status})


@csrf_exempt
@api_errors
@HasPermission("ticket-View")
def cmdb_search(request):
    payload = _body(request)
    try:
        from apps.rpc.cmdb import CMDB

        data = CMDB(is_local_client=True).search_instances(**payload)
    except Exception as exc:
        logger.warning("CMDB 查询失败 error_type=%s", type(exc).__name__)
        return WebUtils.response_error(type(exc).__name__)
    return WebUtils.response_success({"items": data})


@csrf_exempt
@api_errors
@HasPermission("chat-Add")
def chat_messages(request, session_id):
    session = ChatSession.objects.filter(domain=domain_of(request)).get(id=session_id)
    if request.method == "GET":
        items = [{"id": item.id, "sender": item.sender, "content": item.content} for item in session.messages.order_by("id")]
        return WebUtils.response_success({"items": items})
    payload = _body(request)
    item = ChatMessage.objects.create(
        session=session,
        sender=_user(request),
        content=payload.get("content") or "",
        created_by=_user(request),
        updated_by=_user(request),
    )
    return WebUtils.response_success({"id": item.id})


@csrf_exempt
@api_errors
@HasPermission("biz_object-Add")
def biz_records(request, object_id):
    obj = BizObject.objects.filter(domain=domain_of(request)).get(id=object_id)
    if request.method == "GET":
        return WebUtils.response_success({"items": [{"id": item.id, "data": item.data} for item in obj.records.all()]})
    item = BizRecord.objects.create(obj=obj, data=_body(request).get("data") or {}, created_by=_user(request), updated_by=_user(request))
    return WebUtils.response_success({"id": item.id})


def visible_order(queryset):
    return queryset.annotate(_vip=Exists(VipUser.objects.filter(username=OuterRef("creator"), is_enabled=True))).order_by("-_vip", "-id")
