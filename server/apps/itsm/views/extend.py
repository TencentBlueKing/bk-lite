import base64
import json
from functools import wraps
from io import BytesIO

import requests
from django.db.models import Exists, OuterRef
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from jinja2 import TemplateError
from jinja2.sandbox import SandboxedEnvironment
from openpyxl import Workbook

from apps.core.decorators.api_permission import HasPermission
from apps.core.logger import itsm_logger as logger
from apps.core.utils.ssrf_validator import SSRFError, SSRFValidator
from apps.core.utils.web_utils import WebUtils
from apps.itsm.models import DataTable, TicketRelation, TicketTask, VipUser
from apps.itsm.models.extend import (
    AiSetting,
    Announcement,
    AutoExecution,
    BizObject,
    BizRecord,
    ChangeWindow,
    ChatMessage,
    ChatSession,
    DataSource,
    DecisionTable,
    DutyShift,
    EmailRule,
    Handover,
    KnowledgeArticle,
    PrintTemplate,
    ReportCard,
    ScheduledTask,
    SearchField,
    SpecialOperationRule,
    SurveyTemplate,
    TicketExportTask,
    TicketProxy,
    TicketSavedView,
    TodoSync,
    Trigger,
    UserPreference,
)
from apps.itsm.views.access import api_errors, domain_of, get_ticket, has_permission, ticket_scope
from apps.itsm.views.tickets import _service, _user

KINDS = {
    "views": (TicketSavedView, ["name", "filters", "columns"]),
    "proxies": (TicketProxy, ["principal", "agent", "is_enabled"]),
    "decisions": (DecisionTable, ["name", "workflow_id", "rules"]),
    "triggers": (Trigger, ["name", "event", "action", "config", "is_enabled"]),
    "schedules": (ScheduledTask, ["name", "cron", "action", "is_enabled"]),
    "sources": (DataSource, ["name", "kind", "config"]),
    "announcements": (Announcement, ["title", "content", "is_enabled"]),
    "changes": (ChangeWindow, ["name", "start_at", "end_at"]),
    "knowledge": (KnowledgeArticle, ["title", "content", "status"]),
    "duties": (DutyShift, ["name", "members"]),
    "surveys": (SurveyTemplate, ["name", "questions"]),
    "prints": (PrintTemplate, ["name", "body"]),
    "handovers": (Handover, ["from_user", "to_user", "ticket_ids"]),
    "todo_syncs": (TodoSync, ["name", "url"]),
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
    "sources": "data",
    "announcements": "setting",
    "changes": "change",
    "knowledge": "knowledge",
    "duties": "duty",
    "surveys": "survey",
    "prints": "print",
    "handovers": "handover",
    "todo_syncs": "setting",
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
    return data


@csrf_exempt
@api_errors
@resource_permission
def resources(request, kind):
    spec = KINDS.get(kind)
    if spec is None:
        return WebUtils.response_error("未知资源")
    model, fields = spec
    if request.method == "GET":
        items = [_public(item, fields) for item in resource_scope(request, kind, model).order_by("-id")[:100]]
        return WebUtils.response_success({"items": items})
    payload = _body(request)
    values = {field: payload.get(field) for field in fields if field in payload}
    values["domain"] = domain_of(request)
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
        shift = resource_scope(request, kind, model).filter(name=payload.get("name")).first()
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
    try:
        item = model.objects.create(**values, created_by=_user(request), updated_by=_user(request))
    except Exception as exc:
        from django.db import IntegrityError

        if isinstance(exc, IntegrityError):
            return WebUtils.response_error("记录已存在")
        raise
    if kind == "handovers":
        _apply_handover(item)
    if kind == "schedules":
        from apps.itsm.services.schedules import register_schedule

        register_schedule(item)
    if kind == "decisions":
        from apps.itsm.services.dmn import deploy_table

        return WebUtils.response_success({**_public(item, fields), "dmn": deploy_table(item)})
    if kind == "knowledge" and item.status == "published":
        from apps.itsm.services.knowledge_sync import sync_article

        return WebUtils.response_success({**_public(item, fields), "sync": sync_article(item)})
    return WebUtils.response_success(_public(item, fields))


@csrf_exempt
@api_errors
@resource_permission
def resource_item(request, kind, item_id):
    spec = KINDS.get(kind)
    if spec is None:
        return WebUtils.response_error("未知资源")
    model, fields = spec
    item = resource_scope(request, kind, model).filter(id=item_id).first()
    if item is None:
        return WebUtils.response_error("记录不存在")
    if request.method == "DELETE":
        item.delete()
        return WebUtils.response_success({"id": item_id})
    if request.method not in {"PUT", "PATCH"}:
        return WebUtils.response_error("不支持的方法")
    payload = _body(request)
    values = {field: payload.get(field) for field in fields if field in payload}
    values["domain"] = domain_of(request)
    for field, value in values.items():
        setattr(item, field, value)
    item.updated_by = _user(request)
    item.save()
    if kind == "schedules":
        from apps.itsm.services.schedules import register_schedule

        register_schedule(item)
    return WebUtils.response_success(_public(item, fields))


def _apply_handover(item: Handover) -> None:
    ticket_ids = item.ticket_ids or []
    service = _service()
    tasks = TicketTask.objects.filter(
        ticket__domain=item.domain, ticket_id__in=ticket_ids, assignee=item.from_user, status__in=["pending", "claimed"]
    ).select_related("ticket")
    for task in tasks:
        service.operate(task.ticket, task, "transfer", {"target": item.to_user}, item.created_by or item.from_user, privileged=True)


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
@HasPermission("ticket-Export")
def export_tickets(request):
    payload = _body(request)
    queryset = ticket_scope(request).order_by("-id")
    ids = payload.get("ids") or []
    if ids:
        queryset = queryset.filter(id__in=ids)
    rows = list(queryset[:500])
    book = Workbook()
    sheet = book.active
    sheet.append(["sn", "title", "creator", "status"])
    for ticket in rows:
        sheet.append([ticket.sn, ticket.title, ticket.creator, ticket.status.key if ticket.status_id else ""])
    buffer = BytesIO()
    book.save(buffer)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    task = TicketExportTask.objects.create(
        username=_user(request),
        filename=f"tickets-{timezone.now().strftime('%Y%m%d%H%M%S')}.xlsx",
        content_base64=encoded,
        ticket_count=len(rows),
        created_by=_user(request),
        updated_by=_user(request),
    )
    return WebUtils.response_success({"id": task.id, "filename": task.filename, "count": task.ticket_count, "content_base64": encoded})


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
@HasPermission("data-View")
def test_data_source(request, source_id):
    source = DataSource.objects.filter(domain=domain_of(request)).get(id=source_id)
    if source.kind == "sql":
        table_key = str((source.config or {}).get("table_key") or "")
        if not table_key or (source.config or {}).get("sql"):
            return WebUtils.response_error("不执行任意 SQL，只允许按数据表标识读取")
        table = DataTable.objects.filter(domain=domain_of(request)).filter(key=table_key).first()
        if table is None:
            return WebUtils.response_error("数据表不存在")
        rows = [{"id": row.id, "data": row.data} for row in table.rows.all()[:20]]
        return WebUtils.response_success({"items": rows})
    if source.kind != "http":
        return WebUtils.response_error("只允许测试 http 或受控数据表")
    url = str((source.config or {}).get("url") or "")
    try:
        SSRFValidator().validate_url(url)
        response = requests.get(url, timeout=3, allow_redirects=False)
    except (SSRFError, requests.RequestException) as exc:
        logger.warning("数据源测试失败 source_id=%s error_type=%s", source.id, type(exc).__name__)
        return WebUtils.response_error(type(exc).__name__)
    return WebUtils.response_success({"status_code": response.status_code})


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
