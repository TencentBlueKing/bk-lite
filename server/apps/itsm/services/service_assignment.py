from apps.itsm.models import HandlerGroup, Service, WorkflowVersion
from apps.itsm.services.notify.recipients import active_users
from apps.itsm.services.ticket.actions import NodeActionValidationError


def requires_handler_group(design):
    return any((node.get("assignee") or {}).get("source") == "service_group" for node in (design or {}).get("nodes", []))


def has_legacy_preset_handlers(version):
    if version.domain != "domain.com" or version.version_no != 1 or version.created_by != "system":
        return False
    if version.workflow.key not in {"itsm_request", "itsm_incident", "itsm_problem"}:
        return False
    assignees = {node["id"]: node.get("assignee") for node in version.design.get("nodes", [])}
    return assignees.get("approve") == {"source": "users", "value": ["alice", "bob"]} and assignees.get("handle") == {
        "source": "users",
        "value": ["handler"],
    }


LEGACY_PRESET_MESSAGE = "旧预置流程仍引用示例账号。请在新草稿中为分派和处理节点选择服务处理组并发布，然后配置服务。"


def _member_names(group):
    if not isinstance(group.members, list):
        return []
    return list(dict.fromkeys(member for member in group.members if isinstance(member, str) and member))


def eligible_handler_groups(domain, *, group_ids=None):
    groups = HandlerGroup.objects.filter(domain=domain)
    if group_ids is not None:
        groups = groups.filter(pk__in=group_ids)
    groups = list(groups.only("id", "name", "members").order_by("name", "id"))
    members = {name for group in groups for name in _member_names(group)}
    active = set(active_users(domain).filter(username__in=members).values_list("username", flat=True))
    return [{"id": group.pk, "name": group.name} for group in groups if active.intersection(_member_names(group))]


def handler_group_members(group_id, domain):
    group = HandlerGroup.objects.filter(pk=group_id, domain=domain).only("members").first()
    names = _member_names(group) if group is not None else []
    active = set(active_users(domain).filter(username__in=names).values_list("username", flat=True))
    return [name for name in names if name in active]


def service_assignees(version, service_id, *, starting=False):
    query = Service.objects.filter(pk=service_id, domain=version.domain, workflow_id=version.workflow_id)
    if starting:
        query = query.select_for_update().filter(is_enabled=True)
    group_id = query.values_list("handler_group_id", flat=True).first()
    members = handler_group_members(group_id, version.domain) if group_id else []
    if not members:
        raise NodeActionValidationError("请配置本域包含有效成员的服务处理组")
    return members


def activate_service_version(workflow, version):
    workflow.current_version = version
    workflow.save(update_fields=["current_version", "updated_at"])
    if has_legacy_preset_handlers(version):
        workflow.services.filter(is_enabled=True).update(is_enabled=False)
    elif requires_handler_group(version.design):
        services = workflow.services.filter(is_enabled=True)
        bound_groups = services.values_list("handler_group_id", flat=True)
        valid = eligible_handler_groups(workflow.domain, group_ids=bound_groups)
        services.exclude(handler_group_id__in=[group["id"] for group in valid]).update(is_enabled=False)


def has_open_group_tickets(service):
    versions = service.tickets.exclude(status__key__in=["finished", "terminated", "cancelled"]).values("workflow_version_id")
    nodes = WorkflowVersion.objects.filter(pk__in=versions).values_list("design__nodes", flat=True)
    return any(requires_handler_group({"nodes": value or []}) for value in nodes)
