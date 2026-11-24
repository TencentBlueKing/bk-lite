"""服务发现与申请共用同一可见范围，避免绕过门户直接提单。"""
from django.db import connection
from django.db.models import Q

from apps.itsm.models import HandlerGroup, Service
from apps.itsm.views.access import domain_of


def visible_services(request, *, service_id=None, workflow_id=None, hot_only=False, keyword="", catalog_ids=None):
    domain = domain_of(request)
    query = Service.objects.filter(domain=domain, is_enabled=True, workflow__is_enabled=True, workflow__current_version__is_published=True)
    if service_id is not None:
        query = query.filter(pk=service_id)
    if workflow_id is not None:
        query = query.filter(workflow_id=workflow_id)
    if hot_only:
        query = query.filter(is_hot=True)
    if catalog_ids is not None:
        query = query.filter(catalog_id__in=catalog_ids) if catalog_ids else query.filter(catalog_id__isnull=True)
    if keyword:
        query = query.filter(Q(name__icontains=keyword) | Q(description__icontains=keyword) | Q(workflow__name__icontains=keyword))
    if getattr(request.user, "is_superuser", False):
        return query
    username = request.user.username
    if service_id is None and workflow_id is None and connection.features.supports_json_field_contains:
        memberships = HandlerGroup.objects.filter(domain=domain).filter(Q(members__contains=[username]) | Q(leaders__contains=[username]))
        permission = Q(visibility="all") | Q(visible_users__contains=[username])
        for pk in memberships.values_list("pk", flat=True):
            permission |= Q(visible_groups__contains=[pk]) | Q(visible_groups__contains=[str(pk)])
        return query.filter(permission)
    candidates = query.values_list("id", "visibility", "visible_users", "visible_groups")
    allowed = []
    grouped = {}
    for pk, visibility, users, groups in candidates.iterator(chunk_size=500):
        if visibility == "all" or username in (users or []):
            allowed.append(pk)
        elif groups:
            grouped[pk] = {str(value) for value in groups if str(value).isascii() and str(value).isdecimal() and len(str(value)) <= 19 and int(value) < 2**63}
    if grouped:
        group_ids = set().union(*grouped.values())
        memberships = HandlerGroup.objects.filter(domain=domain, pk__in=group_ids).values_list("id", "members", "leaders")
        mine = {str(pk) for pk, members, leaders in memberships if username in (members or []) or username in (leaders or [])}
        allowed.extend(pk for pk, groups in grouped.items() if mine & groups)
    return query.filter(pk__in=allowed)


def check_service_request(request, version, service_id=None):
    if not version.workflow.is_enabled:
        raise PermissionError()
    visible = visible_services(request, workflow_id=version.workflow_id, service_id=service_id)
    if service_id:
        return visible.get(id=service_id)
    if Service.objects.filter(domain=domain_of(request), workflow_id=version.workflow_id).exists() and not visible.exists():
        raise PermissionError()
    return None
