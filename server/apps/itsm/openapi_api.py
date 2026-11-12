from apps.core.openapi.decorators import openapi_expose
from apps.itsm.models import FormModel, Ticket, TicketTask, Workflow
from apps.itsm.openapi_serializers import (
    IdListRequestSerializer,
    TicketCreateRequestSerializer,
    TicketListRequestSerializer,
    TicketOperateRequestSerializer,
)


def _team_id(team):
    teams = [item for item in (team or []) if isinstance(item, int) and not isinstance(item, bool)]
    if len(teams) != 1:
        return None
    return teams[0]


@openapi_expose(
    path="itsm/tickets",
    method="GET",
    schema=TicketListRequestSerializer,
    inject="team_list_with_user",
    permission="ticket-View",
    permission_app="itsm",
    summary="按组织查询工单",
)
def openapi_list_tickets(page=1, page_size=20, *, team=None, user_info=None):
    team_id = _team_id(team)
    if team_id is None:
        return {"result": False, "message": "调用方未绑定有效组织"}
    queryset = Ticket.objects.filter(team__contains=[team_id]).order_by("-id")
    start = (page - 1) * page_size
    items = [{"id": item.id, "sn": item.sn, "title": item.title} for item in queryset[start : start + page_size]]
    return {"result": True, "data": {"count": queryset.count(), "items": items}}


@openapi_expose(
    path="itsm/tickets",
    method="POST",
    schema=TicketCreateRequestSerializer,
    inject="team_list_with_user",
    permission="ticket-Add",
    permission_app="itsm",
    summary="按组织创建工单",
)
def openapi_create_ticket(workflow_key, title, *, team=None, user_info=None):
    team_id = _team_id(team)
    if team_id is None:
        return {"result": False, "message": "调用方未绑定有效组织"}
    workflow = Workflow.objects.filter(key=workflow_key, team__contains=[team_id]).select_related("current_version").first()
    if workflow is None or workflow.current_version_id is None:
        return {"result": False, "message": "流程不存在"}
    from apps.itsm.views.tickets import _service

    username = (user_info or {}).get("username") or "openapi"
    ticket = _service().create(workflow.current_version, {"title": title}, username)
    ticket.team = [team_id]
    ticket.save(update_fields=["team", "updated_at"])
    return {"result": True, "data": {"id": ticket.id, "sn": ticket.sn}}


@openapi_expose(
    path="itsm/tickets/operate",
    method="POST",
    schema=TicketOperateRequestSerializer,
    inject="team_list_with_user",
    permission="ticket-Operate",
    permission_app="itsm",
    summary="按组织处理工单",
)
def openapi_operate_ticket(ticket_id, action, task_id=None, *, team=None, user_info=None):
    team_id = _team_id(team)
    if team_id is None:
        return {"result": False, "message": "调用方未绑定有效组织"}
    ticket = Ticket.objects.filter(id=ticket_id, team__contains=[team_id]).first()
    if ticket is None:
        return {"result": False, "message": "工单不存在"}
    task = TicketTask.objects.filter(id=task_id, ticket=ticket).first() if task_id else None
    from apps.itsm.views.tickets import _service

    username = (user_info or {}).get("username") or "openapi"
    updated = _service().operate(ticket, task, action, {}, username)
    return {"result": True, "data": {"id": updated.id, "status": updated.status.key if updated.status_id else ""}}


@openapi_expose(
    path="itsm/workflows",
    method="GET",
    schema=IdListRequestSerializer,
    inject="team_list_with_user",
    permission="workflow-View",
    permission_app="itsm",
    summary="按组织查询流程",
)
def openapi_list_workflows(page=1, page_size=20, *, team=None, user_info=None):
    team_id = _team_id(team)
    if team_id is None:
        return {"result": False, "message": "调用方未绑定有效组织"}
    queryset = Workflow.objects.filter(team__contains=[team_id]).order_by("-id")
    start = (page - 1) * page_size
    items = [{"id": item.id, "key": item.key, "name": item.name} for item in queryset[start : start + page_size]]
    return {"result": True, "data": {"count": queryset.count(), "items": items}}


@openapi_expose(
    path="itsm/forms",
    method="GET",
    schema=IdListRequestSerializer,
    inject="team_list_with_user",
    permission="form-View",
    permission_app="itsm",
    summary="按组织查询表单",
)
def openapi_list_forms(page=1, page_size=20, *, team=None, user_info=None):
    team_id = _team_id(team)
    if team_id is None:
        return {"result": False, "message": "调用方未绑定有效组织"}
    queryset = FormModel.objects.filter(team__contains=[team_id]).order_by("-id")
    start = (page - 1) * page_size
    items = [{"id": item.id, "key": item.key, "name": item.name} for item in queryset[start : start + page_size]]
    return {"result": True, "data": {"count": queryset.count(), "items": items}}
