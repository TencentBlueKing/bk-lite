"""监控只读目录查询。组织集合只接受网关注入，不读请求里的组织字段。"""

from django.db.models import Q

from apps.monitor.filters.monitor_policy import exclude_policy_group_rules
from apps.monitor.models import MonitorInstance, MonitorObject, MonitorPolicy, PolicyOrganization


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
    rows = list(queryset[start : start + page_size])
    return {
        "count": total,
        "page": page,
        "page_size": page_size,
        "items": [serialize(row) for row in rows],
    }


def list_objects(*, team, page, page_size, keyword):
    if not team_ids(team):
        return page_result(MonitorObject.objects.none(), page, page_size, _object_item)
    queryset = MonitorObject.objects.filter(is_visible=True).order_by("order", "id")
    if keyword:
        queryset = queryset.filter(Q(name__icontains=keyword) | Q(display_name__icontains=keyword))
    return page_result(queryset, page, page_size, _object_item)


def list_instances(*, team, page, page_size, keyword, monitor_object_id=None):
    ids = team_ids(team)
    if not ids:
        return page_result(MonitorInstance.objects.none(), page, page_size, _instance_item)
    queryset = (
        MonitorInstance.objects.filter(is_deleted=False, monitorinstanceorganization__organization__in=ids)
        .distinct()
        .order_by("id")
    )
    if monitor_object_id:
        queryset = queryset.filter(monitor_object_id=monitor_object_id)
    if keyword:
        queryset = queryset.filter(Q(name__icontains=keyword) | Q(ip__icontains=keyword))
    return page_result(queryset, page, page_size, _instance_item)


def list_policies(*, team, page, page_size, keyword, monitor_object_id=None):
    ids = team_ids(team)
    if not ids:
        return page_result(MonitorPolicy.objects.none(), page, page_size, _policy_item)
    owned = PolicyOrganization.objects.filter(organization__in=ids).values("policy_id")
    queryset = exclude_policy_group_rules(MonitorPolicy.objects.filter(id__in=owned)).order_by("id")
    if monitor_object_id:
        queryset = queryset.filter(monitor_object_id=monitor_object_id)
    if keyword:
        queryset = queryset.filter(name__icontains=keyword)
    return page_result(queryset, page, page_size, _policy_item)


def _object_item(obj):
    return {
        "id": obj.id,
        "name": obj.name,
        "display_name": obj.display_name,
        "type": obj.type_id,
        "level": obj.level,
        "parent_id": obj.parent_id,
        "description": obj.description,
    }


def _instance_item(obj):
    return {
        "id": obj.id,
        "name": obj.name,
        "monitor_object_id": obj.monitor_object_id,
        "ip": obj.ip,
        "is_active": obj.is_active,
        "node_id": obj.node_id,
        "cmdb_id": obj.cmdb_id,
        "cloud_region_id": obj.cloud_region_id,
    }


def _policy_item(obj):
    return {
        "id": obj.id,
        "name": obj.name,
        "monitor_object_id": obj.monitor_object_id,
        "alert_name": obj.alert_name,
        "enable": obj.enable,
        "collect_type": obj.collect_type,
    }
