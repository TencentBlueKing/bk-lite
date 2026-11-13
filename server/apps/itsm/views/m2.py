import base64
import json
import re
from io import BytesIO

from django.db import transaction
from django.db.models import Q
from django.views.decorators.csrf import csrf_exempt
from openpyxl import Workbook, load_workbook

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.web_utils import WebUtils
from apps.itsm.models import (
    DataTable,
    DataTableField,
    DataTableRow,
    FormViewTemplate,
    ServiceCalendar,
    SLAPolicy,
    StatusTransition,
    Ticket,
    TicketComment,
    TicketFollower,
    TicketRelation,
    TicketStatus,
    TicketTag,
    Workflow,
    WorkflowStage,
    WorkflowVariable,
    WorkflowVersion,
)
from apps.itsm.views.access import api_errors, domain_of, get_ticket, has_permission, method_permission, ticket_scope


def _body(request):
    if not request.body:
        return {}
    return json.loads(request.body.decode("utf-8"))


def _user(request):
    return getattr(getattr(request, "user", None), "username", "") or ""


@csrf_exempt
@api_errors
@HasPermission("portal-View")
@transaction.atomic
def portal_draft(request):
    from apps.itsm.models import ItsmSetting

    username = _user(request)
    setting, _created = ItsmSetting.objects.select_for_update().get_or_create(
        domain=domain_of(request),
        key="portal_drafts",
        defaults={"value": {}, "created_by": username, "updated_by": username},
    )
    drafts = dict(setting.value or {})
    mine = dict(drafts.get(username) or {})
    if request.method == "GET":
        return WebUtils.response_success({"items": mine})
    payload = _body(request)
    service_id = str(payload.get("service_id") or "")
    if not service_id:
        return WebUtils.response_error("缺少服务")
    if payload.get("clear"):
        mine.pop(service_id, None)
    else:
        values = payload.get("form_data", {"title": str(payload.get("title") or "")})
        if not isinstance(values, dict):
            raise ValueError("草稿必须是表单对象")
        mine[service_id] = values
    drafts[username] = mine
    setting.value = drafts
    setting.updated_by = username
    setting.save(update_fields=["value", "updated_by", "updated_at"])
    return WebUtils.response_success({"service_id": service_id, "form_data": mine.get(service_id)})


@api_errors
@HasPermission("ticket-View")
def todo_summary(request):
    username = _user(request)
    visible = ticket_scope(request)
    pending = visible.filter(tasks__status="pending", tasks__assignee=username).distinct().count()
    finished = visible.filter(status__key="finished").count()
    breached = visible.filter(sla_records__breached=True).distinct().count()
    return WebUtils.response_success({"username": username, "pending": pending, "finished": finished, "sla_breached": breached})


@csrf_exempt
@api_errors
@HasPermission("workflow-Edit")
def statuses(request):
    if request.method == "DELETE":
        item = TicketStatus.objects.filter(id=request.GET.get("id")).first()
        if item is None:
            return WebUtils.response_error("状态不存在")
        if item.kind == TicketStatus.Kind.BUILTIN:
            return WebUtils.response_error("内置状态不能删除")
        item.delete()
        return WebUtils.response_success({"id": item.id})
    if request.method == "GET":
        items = [
            {"id": item.id, "key": item.key, "name": item.name, "color": item.color, "description": item.description, "kind": item.kind}
            for item in TicketStatus.objects.order_by("order", "id")
        ]
        return WebUtils.response_success({"items": items})
    payload = _body(request)
    if payload.get("id"):
        item = TicketStatus.objects.get(id=payload["id"])
        if payload.get("name"):
            item.name = payload["name"]
        if payload.get("color"):
            item.color = payload["color"]
        if "description" in payload:
            item.description = payload["description"]
        item.updated_by = _user(request)
        item.save()
        return WebUtils.response_success({"id": item.id})
    item = TicketStatus.objects.create(
        key=payload["key"],
        name=payload["name"],
        color=payload.get("color") or "#1677ff",
        description=payload.get("description") or "",
        created_by=_user(request),
        updated_by=_user(request),
    )
    return WebUtils.response_success({"id": item.id})


@csrf_exempt
@api_errors
@HasPermission("workflow-Edit")
def status_transitions(request):
    if request.method == "DELETE":
        deleted, _rows = StatusTransition.objects.filter(id=request.GET.get("id")).delete()
        if not deleted:
            return WebUtils.response_error("扭转不存在")
        return WebUtils.response_success({"id": request.GET.get("id")})
    if request.method == "GET":
        items = [
            {
                "id": item.id,
                "from_id": item.from_status_id,
                "to_id": item.to_status_id,
                "from_name": item.from_status.name,
                "to_name": item.to_status.name,
                "name": item.name,
            }
            for item in StatusTransition.objects.select_related("from_status", "to_status")
        ]
        return WebUtils.response_success({"items": items})
    payload = _body(request)
    item = StatusTransition.objects.create(
        from_status_id=payload["from_id"],
        to_status_id=payload["to_id"],
        name=payload.get("name") or "扭转",
        created_by=_user(request),
        updated_by=_user(request),
    )
    return WebUtils.response_success({"id": item.id})


@csrf_exempt
@api_errors
@HasPermission("workflow-Edit")
def stages(request):
    if request.method == "DELETE":
        deleted, _rows = WorkflowStage.objects.filter(domain=domain_of(request)).filter(id=request.GET.get("id")).delete()
        if not deleted:
            return WebUtils.response_error("阶段不存在")
        return WebUtils.response_success({"id": request.GET.get("id")})
    if request.method == "GET":
        workflow_id = request.GET.get("workflow_id")
        queryset = WorkflowStage.objects.filter(domain=domain_of(request)).all()
        if workflow_id:
            queryset = queryset.filter(workflow_id=workflow_id)
        items = [{"id": item.id, "workflow_id": item.workflow_id, "key": item.key, "name": item.name, "node_ids": item.node_ids} for item in queryset]
        return WebUtils.response_success({"items": items})
    payload = _body(request)
    item = WorkflowStage.objects.create(
        domain=domain_of(request),
        workflow_id=payload["workflow_id"],
        key=payload["key"],
        name=payload["name"],
        order=payload.get("order") or 0,
        node_ids=payload.get("node_ids") or [],
        created_by=_user(request),
        updated_by=_user(request),
    )
    return WebUtils.response_success({"id": item.id})


@csrf_exempt
@api_errors
@HasPermission("ticket-View")
@transaction.atomic
def comments(request, ticket_id):
    ticket = get_ticket(request, ticket_id)
    if request.method == "GET":
        items = [
            {
                "id": item.id,
                "content": item.content,
                "operator": item.created_by,
                "parent_id": item.parent_id,
                "created_at": item.created_at.isoformat(),
                "attachment_ids": [file.id for file in item.attachments.all()],
            }
            for item in ticket.comments.prefetch_related("attachments").order_by("id")
        ]
        return WebUtils.response_success({"items": items})
    if request.method != "POST":
        return WebUtils.response_error("不支持的方法", status_code=405)
    payload = _body(request)
    content = str(payload.get("content") or "").strip()
    ids = payload.get("attachment_ids") or []
    if not isinstance(ids, list) or len(ids) > 20 or len(content) > 10000 or (not content and not ids):
        raise ValueError("评论内容或附件无效")
    parent = ticket.comments.get(id=payload["parent_id"]) if payload.get("parent_id") else None
    files = list(ticket.attachments.select_for_update().filter(id__in=ids, created_by=_user(request), comment__isnull=True))
    if len(files) != len(set(ids)):
        raise PermissionError()
    item = TicketComment.objects.create(ticket=ticket, parent=parent, content=content, created_by=_user(request), updated_by=_user(request))
    ticket.attachments.filter(id__in=[file.id for file in files]).update(comment=item)
    return WebUtils.response_success({"id": item.id})


def attachment_data(item, username):
    return {
        "id": item.id,
        "name": item.name,
        "size": item.size,
        "operator": item.created_by,
        "created_at": item.created_at.isoformat(),
        "comment_id": item.comment_id,
        "can_delete": item.created_by == username,
    }


@csrf_exempt
@api_errors
@HasPermission("ticket-View")
def attachments(request, ticket_id):
    from apps.itsm.services.attachment import register_upload

    ticket = get_ticket(request, ticket_id)
    if request.method == "GET":
        return WebUtils.response_success({"items": [attachment_data(item, _user(request)) for item in ticket.attachments.order_by("id")]})
    if request.method != "POST":
        return WebUtils.response_error("不支持的方法", status_code=405)
    item = register_upload(ticket, _user(request), _body(request))
    return WebUtils.response_success(attachment_data(item, _user(request)))


@csrf_exempt
@api_errors
@HasPermission("ticket-View")
def attachment_item(request, ticket_id, attachment_id):
    from apps.itsm.services.attachment import BUCKET, download_url, storage_client

    ticket = get_ticket(request, ticket_id)
    item = ticket.attachments.get(id=attachment_id)
    if request.method == "GET":
        return WebUtils.response_success({"url": download_url(item)})
    if request.method != "DELETE":
        return WebUtils.response_error("不支持的方法", status_code=405)
    if item.created_by != _user(request):
        raise PermissionError()
    storage_client().remove_object(BUCKET, item.object_name)
    item.delete()
    return WebUtils.response_success({"deleted": True})


@csrf_exempt
@api_errors
@HasPermission("ticket-View")
@transaction.atomic
def followers(request, ticket_id):
    ticket = get_ticket(request, ticket_id)
    if request.method == "GET":
        names = list(ticket.followers.values_list("username", flat=True))
        return WebUtils.response_success({"items": names, "following": _user(request) in names})
    if request.method != "POST":
        return WebUtils.response_error("不支持的方法", status_code=405)
    following = _body(request).get("following")
    if not isinstance(following, bool):
        return WebUtils.response_error("请指定关注状态", status_code=400)
    Ticket.objects.select_for_update().get(pk=ticket.pk)
    username = _user(request)
    if following:
        TicketFollower.objects.get_or_create(ticket=ticket, username=username, defaults={"domain": ticket.domain, "created_by": username})
    else:
        ticket.followers.filter(username=username).delete()
    return WebUtils.response_success({"following": following})


@csrf_exempt
@api_errors
@method_permission("ticket-View", "ticket-Operate")
@transaction.atomic
def ticket_tags(request, ticket_id):
    ticket = get_ticket(request, ticket_id)
    if request.method == "GET":
        return WebUtils.response_success(
            {
                "items": [{"id": item.id, "name": item.name, "color": item.color} for item in ticket.tags.all()],
                "can_manage": has_permission(request, "ticket-Operate"),
            }
        )
    payload = _body(request)
    if request.method == "DELETE":
        tag = ticket.tags.get(pk=payload.get("id"))
        ticket.tags.remove(tag)
        return WebUtils.response_success({"deleted": True})
    if request.method != "POST":
        return WebUtils.response_error("不支持的方法", status_code=405)
    name = payload.get("name")
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 64:
        return WebUtils.response_error("标签名称需为 1–64 个字符", status_code=400)
    color = payload.get("color") or "#1677ff"
    if not isinstance(color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        raise ValueError("标签颜色须为六位十六进制颜色")
    tag, _created = TicketTag.objects.get_or_create(
        domain=domain_of(request),
        name=name.strip(),
        defaults={"created_by": _user(request), "updated_by": _user(request), "color": color.lower()},
    )
    ticket.tags.add(tag)
    return WebUtils.response_success({"id": tag.id, "name": tag.name, "color": tag.color})


def visible_relations(request, ticket):
    visible = ticket_scope(request).values("pk")
    return TicketRelation.objects.filter(Q(ticket=ticket, related_id__in=visible) | Q(related=ticket, ticket_id__in=visible))


@csrf_exempt
@api_errors
@method_permission("ticket-View", "ticket-Operate")
@transaction.atomic
def relations(request, ticket_id):
    ticket = get_ticket(request, ticket_id)
    if request.method == "GET":
        items = []
        seen = set()
        for item in visible_relations(request, ticket).select_related("ticket", "related"):
            other = item.related if item.ticket_id == ticket.id else item.ticket
            key = (other.id, item.relation_type)
            if key in seen:
                continue
            seen.add(key)
            items.append(
                {
                    "id": item.id,
                    "related_id": other.id,
                    "related_sn": other.sn,
                    "related_title": other.title,
                    "relation_type": item.relation_type,
                    "can_remove": item.relation_type == "related" and has_permission(request, "ticket-Operate"),
                }
            )
        return WebUtils.response_success({"items": items, "can_manage": has_permission(request, "ticket-Operate")})
    payload = _body(request)
    if request.method == "DELETE":
        item = visible_relations(request, ticket).get(pk=payload.get("id"))
        if item.relation_type != "related":
            return WebUtils.response_error("业务关联需通过对应流程管理，不能在此解除", status_code=400)
        list(Ticket.objects.filter(pk__in=[item.ticket_id, item.related_id]).order_by("pk").select_for_update())
        TicketRelation.objects.filter(
            Q(ticket_id=item.ticket_id, related_id=item.related_id) | Q(ticket_id=item.related_id, related_id=item.ticket_id),
            relation_type="related",
        ).delete()
        return WebUtils.response_success({"deleted": True})
    if request.method != "POST":
        return WebUtils.response_error("不支持的方法", status_code=405)
    related_id = payload.get("related_id")
    if isinstance(related_id, bool) or not isinstance(related_id, int) or related_id <= 0:
        return WebUtils.response_error("请选择有效工单", status_code=400)
    related = get_ticket(request, related_id)
    if related.pk == ticket.pk:
        return WebUtils.response_error("不能关联当前工单自身", status_code=400)
    if payload.get("relation_type", "related") != "related":
        return WebUtils.response_error("此入口仅支持普通关联", status_code=400)
    # 固定顺序锁定两端，避免反向并发请求建立重复关系。
    list(Ticket.objects.filter(pk__in=[ticket.pk, related.pk]).order_by("pk").select_for_update())
    if TicketRelation.objects.filter(Q(ticket=ticket, related=related) | Q(ticket=related, related=ticket)).exists():
        return WebUtils.response_error("这两张工单已经关联", status_code=400)
    item = TicketRelation.objects.create(
        ticket=ticket, related=related, relation_type="related", domain=ticket.domain, created_by=_user(request), updated_by=_user(request)
    )
    return WebUtils.response_success({"id": item.id})


@csrf_exempt
@api_errors
@HasPermission("workflow-Edit")
def workflow_variables(request):
    if request.method == "GET":
        workflow_id = request.GET.get("workflow_id")
        queryset = WorkflowVariable.objects.filter(domain=domain_of(request)).all()
        if workflow_id:
            queryset = queryset.filter(workflow_id=workflow_id)
        return WebUtils.response_success({"items": [{"id": item.id, "key": item.key, "name": item.name} for item in queryset]})
    payload = _body(request)
    workflow = Workflow.objects.filter(domain=domain_of(request)).get(id=payload["workflow_id"])
    if payload.get("from_form") and workflow.form_id and workflow.form.current_version_id:
        created = []
        for field in workflow.form.current_version.schema.get("fields") or []:
            item, was_created = WorkflowVariable.objects.get_or_create(
                workflow=workflow,
                key=field.get("key"),
                defaults={
                    "name": field.get("label") or field.get("key"),
                    "source": "form",
                    "created_by": _user(request),
                    "updated_by": _user(request),
                },
            )
            if was_created:
                created.append(item.id)
        return WebUtils.response_success({"ids": created})
    item = WorkflowVariable.objects.create(
        domain=domain_of(request),
        workflow=workflow,
        key=payload["key"],
        name=payload.get("name") or payload["key"],
        source=payload.get("source") or "custom",
        created_by=_user(request),
        updated_by=_user(request),
    )
    return WebUtils.response_success({"id": item.id})


@csrf_exempt
@api_errors
@HasPermission("workflow-Publish")
def enable_version(request, workflow_id, version_id):
    workflow = Workflow.objects.filter(domain=domain_of(request)).get(id=workflow_id)
    version = WorkflowVersion.objects.get(id=version_id, workflow=workflow, is_published=True)
    workflow.current_version = version
    workflow.save(update_fields=["current_version", "updated_at"])
    from django.utils import timezone

    from apps.itsm.models import ItsmSetting

    setting, _created = ItsmSetting.objects.get_or_create(
        domain=domain_of(request),
        key="version_log",
        defaults={"value": [], "created_by": _user(request), "updated_by": _user(request)},
    )
    logs = list(setting.value or [])
    logs.append({"workflow_id": workflow.id, "version_id": version.id, "by": _user(request), "at": timezone.now().isoformat()})
    setting.value = logs[-50:]
    setting.updated_by = _user(request)
    setting.save(update_fields=["value", "updated_by", "updated_at"])
    return WebUtils.response_success({"version_id": version.id})


@csrf_exempt
@api_errors
@HasPermission("workflow-Edit")
def test_start(request, workflow_id):
    from django.conf import settings

    from apps.itsm.flowable.client import FlowableClient
    from apps.itsm.services.ticket.service import TicketService

    workflow = Workflow.objects.filter(domain=domain_of(request)).get(id=workflow_id)
    version = workflow.current_version
    client = FlowableClient(settings.FLOWABLE_URL, settings.FLOWABLE_USER, settings.FLOWABLE_PASSWORD) if settings.FLOWABLE_PASSWORD else None
    ticket = TicketService(client).create(version, _body(request).get("form_data") or {"title": "测试单"}, _user(request), is_test=True)
    return WebUtils.response_success({"id": ticket.id, "sn": ticket.sn, "is_test": True})


@csrf_exempt
@api_errors
@HasPermission("workflow-Edit")
def cleanup_test_tickets(request):
    deleted, _details = Ticket.objects.filter(domain=domain_of(request)).filter(is_test=True).delete()
    return WebUtils.response_success({"deleted": deleted})


@csrf_exempt
@api_errors
@method_permission("workflow-View", "workflow-Edit")
def sla_settings(request):
    if request.method == "POST":
        payload = _body(request)
        if payload.get("kind") == "calendar":
            if payload.get("id"):
                item = ServiceCalendar.objects.filter(domain=domain_of(request)).get(id=payload["id"])
                item.name = payload.get("name") or item.name
                item.work_days = payload.get("work_days") or item.work_days
                item.work_start = payload.get("work_start") or item.work_start
                item.work_end = payload.get("work_end") or item.work_end
                item.updated_by = _user(request)
                item.save()
                return WebUtils.response_success({"id": item.id})
            item = ServiceCalendar.objects.create(
                domain=domain_of(request),
                name=payload["name"],
                work_days=payload.get("work_days") or [1, 2, 3, 4, 5],
                work_start=payload.get("work_start") or "09:00",
                work_end=payload.get("work_end") or "18:00",
                created_by=_user(request),
                updated_by=_user(request),
            )
            return WebUtils.response_success({"id": item.id})
        if payload.get("kind") == "policy" and not payload.get("policy_id"):
            policy = SLAPolicy.objects.create(
                domain=domain_of(request),
                name=payload["name"],
                target=payload.get("target") or "response",
                minutes=int(payload.get("minutes") or 60),
                calendar_id=payload["calendar_id"],
                category=payload.get("category") or "sla",
                workflow_id=payload.get("workflow_id"),
                created_by=_user(request),
                updated_by=_user(request),
            )
            return WebUtils.response_success({"id": policy.id})
        policy = SLAPolicy.objects.filter(domain=domain_of(request)).get(id=payload["policy_id"])
        if "is_enabled" in payload:
            policy.is_enabled = bool(payload["is_enabled"])
        category = payload.get("category")
        if category in {"sla", "slo", "ola", "uc"}:
            policy.category = category
        if "minutes" in payload:
            policy.minutes = int(payload["minutes"])
        if payload.get("name"):
            policy.name = payload["name"]
        policy.updated_by = _user(request)
        policy.save()
        from apps.itsm.models.extend import SLAPolicyLog

        SLAPolicyLog.objects.create(
            policy=policy,
            message=f"category={policy.category} enabled={policy.is_enabled}",
            created_by=_user(request),
            updated_by=_user(request),
        )
        return WebUtils.response_success({"id": policy.id, "category": policy.category, "is_enabled": policy.is_enabled})
    calendars = [
        {"id": item.id, "name": item.name, "work_days": item.work_days, "work_start": item.work_start, "work_end": item.work_end}
        for item in ServiceCalendar.objects.filter(domain=domain_of(request)).all()
    ]
    policies = [
        {
            "id": item.id,
            "name": item.name,
            "workflow_id": item.workflow_id,
            "target": item.target,
            "minutes": item.minutes,
            "category": item.category,
            "is_enabled": item.is_enabled,
        }
        for item in SLAPolicy.objects.filter(domain=domain_of(request)).all()
    ]
    return WebUtils.response_success({"calendars": calendars, "policies": policies})


@csrf_exempt
@api_errors
@HasPermission("form-Edit")
def view_templates(request):
    if request.method == "GET":
        form_id = request.GET.get("form_id")
        queryset = FormViewTemplate.objects.filter(domain=domain_of(request)).all()
        if form_id:
            queryset = queryset.filter(form_id=form_id)
        items = [
            {"id": item.id, "form_id": item.form_id, "name": item.name, "layout": item.layout, "match_rules": item.match_rules} for item in queryset
        ]
        return WebUtils.response_success({"items": items})
    payload = _body(request)
    item = FormViewTemplate.objects.create(
        domain=domain_of(request),
        form_id=payload["form_id"],
        name=payload["name"],
        layout=payload.get("layout") or {},
        match_rules=payload.get("match_rules") or {},
        created_by=_user(request),
        updated_by=_user(request),
    )
    return WebUtils.response_success({"id": item.id})


@csrf_exempt
@api_errors
@method_permission("data-View", "data-Add")
def data_tables(request):
    if request.method == "GET":
        items = [{"id": item.id, "name": item.name, "key": item.key} for item in DataTable.objects.filter(domain=domain_of(request)).all()]
        return WebUtils.response_success({"items": items})
    payload = _body(request)
    item = DataTable.objects.create(
        domain=domain_of(request), name=payload["name"], key=payload["key"], created_by=_user(request), updated_by=_user(request)
    )
    for field in payload.get("fields") or []:
        DataTableField.objects.create(
            table=item, key=field["key"], field_type=field.get("type") or "string", created_by=_user(request), updated_by=_user(request)
        )
    return WebUtils.response_success({"id": item.id})


@csrf_exempt
@api_errors
@HasPermission("data-Edit")
def data_table_rows(request, table_id):
    table = DataTable.objects.filter(domain=domain_of(request)).get(id=table_id)
    if request.method == "GET":
        return WebUtils.response_success({"items": [{"id": row.id, "data": row.data} for row in table.rows.all()]})
    row = DataTableRow.objects.create(table=table, data=_body(request).get("data") or {}, created_by=_user(request), updated_by=_user(request))
    return WebUtils.response_success({"id": row.id})


def _table_keys(table):
    return [field.key for field in table.fields.order_by("id")]


@api_errors
@HasPermission("data-View")
def data_table_export(request, table_id):
    table = DataTable.objects.filter(domain=domain_of(request)).prefetch_related("fields", "rows").get(id=table_id)
    keys = _table_keys(table)
    book = Workbook()
    sheet = book.active
    sheet.title = "data"
    sheet.append(keys)
    for row in table.rows.all():
        sheet.append([row.data.get(key, "") for key in keys])
    buffer = BytesIO()
    book.save(buffer)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return WebUtils.response_success({"filename": f"{table.key}.xlsx", "content_base64": encoded})


@csrf_exempt
@api_errors
@HasPermission("data-Edit")
def data_table_import(request, table_id):
    table = DataTable.objects.filter(domain=domain_of(request)).prefetch_related("fields").get(id=table_id)
    payload = _body(request)
    raw = base64.b64decode(payload.get("content_base64") or "")
    book = load_workbook(BytesIO(raw), read_only=True, data_only=True)
    sheet = book.active
    rows = list(sheet.iter_rows(values_only=True))
    if not rows:
        return WebUtils.response_success({"created": 0})
    header = [str(cell) for cell in rows[0] if cell]
    keys = _table_keys(table) or header
    created = []
    for values in rows[1:]:
        data = {}
        for index, key in enumerate(keys):
            value = values[index] if index < len(values) else None
            if value is not None:
                data[key] = value
        if not data:
            continue
        row = DataTableRow.objects.create(table=table, data=data, created_by=_user(request), updated_by=_user(request))
        created.append(row.id)
    return WebUtils.response_success({"created": len(created), "ids": created})


@csrf_exempt
@api_errors
@HasPermission("data-Edit")
def data_table_row_delete(request, table_id):
    DataTable.objects.get(id=table_id, domain=domain_of(request))
    ids = _body(request).get("ids") or []
    deleted, _details = DataTableRow.objects.filter(table_id=table_id, id__in=ids).delete()
    return WebUtils.response_success({"deleted": deleted})


@api_errors
@HasPermission("workflow-View")
def workflow_export(request, workflow_id):
    workflow = Workflow.objects.filter(domain=domain_of(request)).get(id=workflow_id)
    version = workflow.current_version or workflow.versions.order_by("-version_no").first()
    return WebUtils.response_success(
        {
            "key": workflow.key,
            "name": workflow.name,
            "version_no": version.version_no if version else 0,
            "design": version.design if version else {},
        }
    )


@csrf_exempt
@api_errors
@HasPermission("workflow-Edit")
def workflow_import(request, workflow_id):
    workflow = Workflow.objects.filter(domain=domain_of(request)).get(id=workflow_id)
    design = _body(request).get("design") or {}
    version_no = (workflow.versions.order_by("-version_no").values_list("version_no", flat=True).first() or 0) + 1
    version = WorkflowVersion.objects.create(
        workflow=workflow,
        version_no=version_no,
        design=design,
        created_by=_user(request),
        updated_by=_user(request),
    )
    return WebUtils.response_success({"id": version.id, "version_no": version.version_no})


@csrf_exempt
@api_errors
@HasPermission("workflow-View")
def workflow_variable_test(request):
    payload = _body(request)
    variable = WorkflowVariable.objects.filter(domain=domain_of(request)).get(workflow_id=payload["workflow_id"], key=payload["key"])
    form_data = payload.get("form_data") if isinstance(payload.get("form_data"), dict) else {}
    sample = payload.get("sample") if isinstance(payload.get("sample"), dict) else {}
    if variable.source == WorkflowVariable.Source.FORM:
        value = form_data.get(variable.key)
    elif variable.key == "initiator":
        value = sample.get("initiator") or _user(request)
    else:
        default = variable.default if isinstance(variable.default, dict) else {}
        value = default.get("value")
    return WebUtils.response_success({"key": variable.key, "source": variable.source, "value": value})


@api_errors
@HasPermission("workflow-View")
def workflow_versions(request, workflow_id):
    from django.db.models import Count

    workflow = Workflow.objects.filter(domain=domain_of(request)).get(id=workflow_id)
    usage = {
        row["workflow_version_id"]: row["n"]
        for row in Ticket.objects.filter(domain=domain_of(request)).filter(workflow=workflow).values("workflow_version_id").annotate(n=Count("id"))
    }
    items = [
        {
            "id": item.id,
            "version_no": item.version_no,
            "is_published": item.is_published,
            "is_current": item.id == workflow.current_version_id,
            "ticket_count": usage.get(item.id, 0),
        }
        for item in workflow.versions.order_by("-version_no")
    ]
    return WebUtils.response_success({"items": items})
