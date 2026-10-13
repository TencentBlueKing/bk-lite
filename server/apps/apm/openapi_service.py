"""APM 只读目录查询。组织集合只接受网关注入。"""

from django.db.models import Q

from apps.apm.models import (
    ApmApplication,
    ApmService,
    ApmServiceInstance,
)


def team_ids(team):
    ids = []
    for item in team or []:
        try:
            value = int(item)
        except (TypeError, ValueError):
            continue
        if value > 0:
            ids.append(value)
    return ids


def page_result(queryset, page, page_size, serialize):
    total = queryset.count()
    start = (page - 1) * page_size
    return {
        "count": total,
        "page": page,
        "page_size": page_size,
        "items": [serialize(row) for row in queryset[start : start + page_size]],
    }


def list_applications(*, team, page, page_size, keyword):
    ids = team_ids(team)
    if not ids:
        return page_result(ApmApplication.objects.none(), page, page_size, _application_item)
    queryset = (
        ApmApplication.objects.filter(is_builtin=False, organization_links__organization__in=ids)
        .distinct()
        .order_by("application_id", "id")
    )
    if keyword:
        queryset = queryset.filter(Q(name__icontains=keyword) | Q(application_id__icontains=keyword))
    return page_result(queryset, page, page_size, _application_item)


def list_services(*, team, page, page_size, keyword, application_id=""):
    ids = team_ids(team)
    if not ids:
        return page_result(ApmService.objects.none(), page, page_size, _service_item)
    queryset = (
        ApmService.objects.filter(organization_links__organization__in=ids)
        .select_related("application")
        .distinct()
        .order_by("normalized_name", "id")
    )
    if application_id:
        queryset = queryset.filter(application__application_id=application_id)
    if keyword:
        queryset = queryset.filter(name__icontains=keyword)
    return page_result(queryset, page, page_size, _service_item)


def list_instances(*, team, page, page_size, keyword, application_id=""):
    ids = team_ids(team)
    if not ids:
        return page_result(ApmServiceInstance.objects.none(), page, page_size, _instance_item)
    queryset = (
        ApmServiceInstance.objects.filter(organization_links__organization__in=ids)
        .select_related("service__application")
        .distinct()
        .order_by("normalized_instance_id", "id")
    )
    if application_id:
        queryset = queryset.filter(service__application__application_id=application_id)
    if keyword:
        queryset = queryset.filter(instance_id__icontains=keyword)
    return page_result(queryset, page, page_size, _instance_item)


def _application_item(obj):
    return {
        "id": str(obj.id),
        "application_id": obj.application_id,
        "name": obj.name,
        "description": obj.description,
    }


def _service_item(obj):
    application = obj.application
    return {
        "id": str(obj.id),
        "name": obj.name,
        "namespace": obj.namespace,
        "application_id": application.application_id if application else "",
        "language": obj.language,
        "archived": obj.archived_at is not None,
    }


def _instance_item(obj):
    return {
        "id": str(obj.id),
        "instance_id": obj.instance_id,
        "service_id": str(obj.service_id),
        "environment": obj.environment,
        "version": obj.version,
    }
