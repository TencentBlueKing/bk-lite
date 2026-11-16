"""服务发现与申请共用同一可见范围，避免绕过门户直接提单。"""
from apps.itsm.models import HandlerGroup, Service
from apps.itsm.views.access import domain_of


def visible_services(request):
    domain = domain_of(request)
    query = Service.objects.filter(domain=domain, is_enabled=True, workflow__is_enabled=True, workflow__current_version__is_published=True)
    if getattr(request.user, "is_superuser", False):
        return query
    username = request.user.username
    groups = {str(g.id) for g in HandlerGroup.objects.filter(domain=domain) if username in (g.members or []) or username in (g.leaders or [])}
    allowed = [
        item.id
        for item in query.only("id", "visibility", "visible_users", "visible_groups")
        if item.visibility == "all" or username in item.visible_users or groups.intersection(map(str, item.visible_groups))
    ]
    return query.filter(id__in=allowed)


def check_service_request(request, version, service_id=None):
    if not version.workflow.is_enabled:
        raise PermissionError()
    visible = visible_services(request).filter(workflow_id=version.workflow_id)
    if service_id:
        return visible.get(id=service_id)
    if Service.objects.filter(domain=domain_of(request), workflow_id=version.workflow_id).exists() and not visible.exists():
        raise PermissionError()
    return None
