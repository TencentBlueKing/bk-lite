from django.http import Http404
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.web_utils import WebUtils
from apps.itsm.flowable.client import FlowableError
from apps.itsm.models import TicketFollower, TicketRelation, TicketTask
from apps.itsm.models.extend import AutoExecution, TicketProxy
from apps.itsm.services.ticket.batch import selection, validate_ids
from apps.itsm.services.ticket.handover import ACTIVE_STATUSES
from apps.itsm.services.ticket.printing import PrintTicketContext, render_print_example, render_ticket_print
from apps.itsm.views.access import api_errors, domain_of, get_ticket, has_permission, json_object, ticket_scope
from apps.itsm.views.tickets import _service, _user, ticket_form_view, ticket_principals


@csrf_exempt
@api_errors
@HasPermission("ticket-View")
def batch_options(request):
    if request.method != "POST":
        return WebUtils.response_error("不支持的请求方法", status_code=405)
    options, _ = selection(request, validate_ids(json_object(request).get("ids")))
    return WebUtils.response_success(options)


@csrf_exempt
@api_errors
@HasPermission("ticket-View")
def batch_operate(request):
    if request.method != "POST":
        return WebUtils.response_error("不支持的请求方法", status_code=405)
    payload = json_object(request)
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
@require_POST
@api_errors
@HasPermission("ticket-Add")
def create_child(request, ticket_id):
    parent = ticket_scope(request).select_related("workflow_version").get(id=ticket_id)
    payload = json_object(request)
    child = _service(request).create(parent.workflow_version, payload.get("form_data") or {"title": parent.title}, _user(request), is_test=parent.is_test)
    TicketRelation.objects.create(
        ticket=parent,
        related=child,
        domain=parent.domain,
        relation_type="child",
        created_by=_user(request),
        updated_by=_user(request),
    )
    return WebUtils.response_success({"id": child.id, "sn": child.sn})


@csrf_exempt
@require_POST
@api_errors
@HasPermission("print-View")
def preview_print_template(request):
    return WebUtils.response_success({"html": render_print_example()})


@require_GET
@api_errors
@HasPermission("ticket-View")
def render_print(request, ticket_id):
    scoped = ticket_scope(request).select_related(
        "status", "service", "workflow__form__current_version", "workflow_version__workflow__form__current_version"
    )
    ticket = get_object_or_404(scoped.prefetch_related("tasks"), pk=ticket_id)
    active = [task for task in ticket.tasks.all() if task.status in ACTIVE_STATUSES]
    privileged = bool(getattr(request.user, "is_superuser", False))
    principals = set() if privileged or not active else ticket_principals(ticket, _user(request))
    own_task = next((task for task in active if privileged or task.assignee in principals), None)
    design = ticket.workflow_version.design if ticket.workflow_version_id else {}
    status_key = ticket.status.key if ticket.status_id else ""
    form = ticket_form_view(ticket, design, own_task, status_key, include_legacy_fields=False)
    return WebUtils.response_success({"html": render_ticket_print(PrintTicketContext(ticket, active, *form))})


@csrf_exempt
@api_errors
@HasPermission("ticket-Operate")
def run_auto(request, ticket_id):
    ticket = get_ticket(request, ticket_id)
    payload = json_object(request)
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
