import json
from datetime import timedelta
from functools import wraps

from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Exists, OuterRef, Prefetch, Q
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from apps.core.decorators.api_permission import HasPermission
from apps.core.logger import itsm_logger as logger
from apps.core.utils.web_utils import WebUtils
from apps.itsm.models import TicketTask, VipUser
from apps.itsm.models.extend import (
    AiSetting,
    Announcement,
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
from apps.itsm.services.ticket.printing import PrintTemplateError, normalize_print_template
from apps.itsm.services.ticket.service import _find_node
from apps.itsm.services.ticket.survey import SurveyValidationError, normalize_survey_template
from apps.itsm.services.trigger_config import TriggerConfigError, normalize_trigger
from apps.itsm.services.work_schedules import WorkScheduleError, mutate_change_window, save_duty_shift
from apps.itsm.views.access import api_errors, domain_of, has_permission, json_object, ticket_scope
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
    "duties": (DutyShift, ["name", "day", "members"]),
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
    if kind in {"schedules", "triggers", "changes", "duties", "surveys", "prints"}:
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
    if kind in {"changes", "duties"}:
        return _write_work_schedule(request, kind, fields)
    if kind in {"surveys", "prints", "triggers"} and request.method != "POST":
        return WebUtils.response_error("不支持的请求方法", status_code=405)
    payload = json_object(request)
    values = {field: payload.get(field) for field in fields if field in payload}
    values["domain"] = domain_of(request)
    if kind == "schedules":
        return _save_schedule(request, values)
    if kind == "triggers":
        return _save_trigger(request, values)
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
    if kind in {"prints", "surveys"}:
        normalize = normalize_print_template if kind == "prints" else normalize_survey_template
        try:
            values = normalize(values, creating=True)
        except (PrintTemplateError, SurveyValidationError) as exc:
            return WebUtils.response_error(error_message=str(exc))
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
    if kind in {"changes", "duties"}:
        return _write_work_schedule(request, kind, fields, item_id=item_id)
    item = resource_scope(request, kind, model).filter(id=item_id).first()
    if item is None:
        return WebUtils.response_error("记录不存在", status_code=404) if kind == "prints" else WebUtils.response_error("记录不存在")
    if kind == "handovers" and item.results:
        return WebUtils.response_error("交接执行记录不允许修改或删除", status_code=405)
    if request.method == "DELETE":
        item.delete()
        return WebUtils.response_success({"id": item_id})
    if request.method not in {"PUT", "PATCH"}:
        return WebUtils.response_error("不支持的方法")
    payload = json_object(request)
    values = {field: payload.get(field) for field in fields if field in payload}
    values["domain"] = domain_of(request)
    if kind == "schedules":
        return _save_schedule(request, values, item)
    if kind == "triggers":
        return _save_trigger(request, values, item)
    if kind in {"prints", "surveys"}:
        normalize = normalize_print_template if kind == "prints" else normalize_survey_template
        try:
            values = normalize(values)
        except (PrintTemplateError, SurveyValidationError) as exc:
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


def _write_work_schedule(request, kind, fields, *, item_id=None):
    allowed = {"POST"} if item_id is None else {"PUT", "PATCH", "DELETE"}
    if request.method not in allowed:
        return WebUtils.response_error("不支持的请求方法", status_code=405)
    domain, username = domain_of(request), _user(request)
    if request.method == "DELETE":
        if kind == "changes":
            mutate_change_window(domain, username, {}, item_id=item_id, delete=True)
        else:
            DutyShift.objects.get(domain=domain, id=item_id).delete()
        return WebUtils.response_success({"id": item_id})
    payload = json_object(request)
    if kind == "duties" and "check_in" in payload:
        return WebUtils.response_error("值班排班不接受签到请求")
    values = {field: payload[field] for field in fields if field in payload}
    save = mutate_change_window if kind == "changes" else save_duty_shift
    try:
        item = save(domain, username, values, item_id=item_id)
    except WorkScheduleError as exc:
        return WebUtils.response_error(error_message=str(exc))
    return WebUtils.response_success(_public(item, fields))


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
@HasPermission("workflow-Edit")
def execute_decision(request, decision_id):
    table = DecisionTable.objects.filter(domain=domain_of(request)).get(id=decision_id)
    form_data = json_object(request).get("form_data") or {}
    matched = {}
    for rule in table.rules or []:
        when = rule.get("when") or {}
        if str(form_data.get(when.get("field"))) == str(when.get("value")):
            matched = rule.get("then") or {}
            break
    return WebUtils.response_success({"matched": matched})


@csrf_exempt
@api_errors
@HasPermission("ticket-View")
def cmdb_search(request):
    payload = json_object(request)
    try:
        from apps.rpc.cmdb import CMDB

        data = CMDB(is_local_client=True).search_instances(**payload)
    except Exception as exc:
        logger.warning("CMDB 查询失败 error_type=%s", type(exc).__name__)
        return WebUtils.response_error(type(exc).__name__)
    return WebUtils.response_success({"items": data})


def _body(request):
    if not request.body:
        return {}
    return json.loads(request.body.decode("utf-8"))


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
