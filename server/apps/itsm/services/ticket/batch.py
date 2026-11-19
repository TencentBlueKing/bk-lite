"""批量处理使用所选工单可用操作的交集。"""
from django.db.models import Prefetch

from apps.itsm.models import TicketTask
from apps.itsm.models.extend import TicketProxy
from apps.itsm.services.ticket.actions import node_actions, node_required_opinions, side_action_enabled, side_required_opinions
from apps.itsm.services.ticket.service import _find_node
from apps.itsm.views.access import domain_of, has_permission, ticket_scope

SOCIAL = {"follow", "unfollow"}
PROCESS = {"submit", "approve", "reject", "claim", "urge", "suspend", "resume"}


def validate_ids(ids):
    if not isinstance(ids, list) or not 1 <= len(ids) <= 50 or any(type(pk) is not int or pk <= 0 for pk in ids):
        raise ValueError("请选择1至50张工单")
    return list(dict.fromkeys(ids))


def selection(request, ids):
    rows = list(
        ticket_scope(request)
        .filter(pk__in=ids)
        .select_related("status", "workflow_version")
        .prefetch_related(Prefetch("tasks", queryset=TicketTask.objects.filter(status__in=["pending", "claimed"])))
    )
    username = request.user.username
    privileged = bool(getattr(request.user, "is_superuser", False))
    actors = {username, *TicketProxy.objects.filter(domain=domain_of(request), agent=username, is_enabled=True).values_list("principal", flat=True)}
    common = SOCIAL | PROCESS
    opinions = set()
    signatures = set()
    for ticket in rows:
        tasks = [task for task in ticket.tasks.all() if task.status in {"pending", "claimed"}]
        signatures.add((ticket.workflow_version_id, tuple(sorted({task.node_id for task in tasks}))))
        allowed = set(SOCIAL)
        state = ticket.status.key if ticket.status_id else ""
        if has_permission(request, "ticket-Operate") and state not in {"finished", "terminated", "cancelled"}:
            design = ticket.workflow_version.design if ticket.workflow_version_id else {}
            own = [task for task in tasks if privileged or task.assignee in actors]
            if state != "suspended" and len(own) == 1:
                node = _find_node(design, node_id=own[0].node_id)
                available = set(node_actions(node, own[0])) & PROCESS
                allowed.update(available)
                opinions.update(node_required_opinions(node, available))
            side = set()
            if privileged or ticket.creator in actors:
                side.add("urge")
            if privileged or own:
                side.add("resume" if state == "suspended" else "suspend")
            available_side = {action for action in side if side_action_enabled(design, tasks, action)}
            allowed.update(available_side)
            opinions.update(side_required_opinions(design, tasks, available_side))
        common.intersection_update(allowed)
    mixed = len(signatures) > 1
    if mixed:
        common.intersection_update(SOCIAL)
    missing = len(rows) != len(ids)
    reason = "所选工单包含不同流程版本或节点，请按相同节点重新勾选；仅可批量关注或取消关注。" if mixed else ""
    if missing:
        common.clear()
        reason = "部分工单已不存在或无查看权限，请刷新列表重新选择。"
    elif not rows:
        common.clear()
    elif common == SOCIAL and not reason:
        reason = "所选工单没有共同的可用处理操作，仅可批量关注或取消关注。"
    return {
        "actions": sorted(common),
        "reason": reason,
        "mixed_nodes": mixed,
        "required_opinion_actions": sorted(common & opinions),
    }, rows
